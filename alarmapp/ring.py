from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import caster
import emfit


LOGGER = logging.getLogger(__name__)


def guess_audio_mime(url: str) -> str:
    low = url.lower().split("?")[0]
    if low.endswith(".wav"):
        return "audio/wav"
    if low.endswith((".ogg", ".oga")):
        return "audio/ogg"
    if low.endswith((".m4a", ".aac")):
        return "audio/aac"
    if low.endswith(".flac"):
        return "audio/flac"
    return "audio/mpeg"


current_session: "RingSession | None" = None
_session_lock = asyncio.Lock()


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


class RingSession:
    def __init__(
        self,
        alarm_id: int,
        sound_url: str,
        device_name: str,
        settings_dict: dict[str, Any],
    ):
        self.alarm_id = alarm_id
        self.sound_url = sound_url
        self.device_name = device_name
        self.settings = settings_dict.copy()
        self.state = "RINGING"
        self.ended_reason: str | None = None
        self.session_start = datetime.now()
        self.grace_start: datetime | None = None
        self.out_start: datetime | None = None
        self.continuous_out_sec = 0.0
        self._continuous_none_sec = 0.0
        self._snooze_requested = False
        self._hard_stop = False
        self._task: asyncio.Task[Any] | None = None
        self._caster = caster.CastSession(device_name)
        self._volume_ack_ticks = 0
        self._settle_tick = False
        self._seen_playing = False

        # The ring loop ticks fast (for snappy volume-ACK); emfit is read from
        # the cache kept fresh by the background poller, so a fast tick does not
        # hammer the slow sensor endpoint.
        self.tick_sec = max(0.01, _as_float(self.settings.get("tick_sec"), 1.0))
        self.volume_ack_ticks_required = max(1, int(_as_float(self.settings.get("volume_ack_ticks_required"), 2)))
        self.poll_sec = max(0.01, _as_float(self.settings.get("poll_sec"), 5.0))
        self.ring_volume = max(0.0, min(1.0, _as_float(self.settings.get("ring_volume"), 1.0)))
        self.volume_ack_epsilon = max(0.0, _as_float(self.settings.get("volume_ack_epsilon"), 0.05))
        self.awake_confirm_sec = max(0.01, _as_float(self.settings.get("awake_confirm_sec"), 180.0))
        self.grace_sec = max(0.01, _as_float(self.settings.get("grace_sec"), 120.0))
        self.none_continue_sec = max(0.01, _as_float(self.settings.get("none_continue_sec"), 60.0))
        self.max_session_sec = max(0.01, _as_float(self.settings.get("max_session_sec"), 1800.0))
        self.volume_ack_enabled = _as_bool(self.settings.get("volume_ack_enabled"), True)
        self.wake_check = _as_bool(self.settings.get("wake_check"), True)
        self.emfit_enabled = _as_bool(self.settings.get("emfit_enabled"), True) and self.wake_check

    def request_snooze(self) -> None:
        """Web button: silence and keep monitoring. For wake-check sessions this
        is NOT a full dismiss — it re-rings if still/again in bed; only a
        sustained out-of-bed (woke) or the safety timeout ends it."""
        self._snooze_requested = True

    def manual_stop(self) -> None:
        self._hard_stop = True

    async def start(self) -> None:
        LOGGER.info("starting ring session alarm=%s device=%s", self.alarm_id, self.device_name)
        self._recast()
        try:
            while self.ended_reason is None:
                await self._tick()
                if self.ended_reason is None:
                    await asyncio.sleep(self.tick_sec)
        finally:
            self._caster.stop()
            self._caster.disconnect()
            await self._clear_current()
            LOGGER.info("ring session ended alarm=%s reason=%s", self.alarm_id, self.ended_reason)

    async def _clear_current(self) -> None:
        global current_session
        async with _session_lock:
            if current_session is self:
                current_session = None

    async def _tick(self) -> None:
        if self._hard_stop:
            self._caster.stop()
            self._end("manual")
            return
        if self._snooze_requested:
            self._snooze_requested = False
            if self.wake_check and self.emfit_enabled:
                # Snooze: silence and keep monitoring; re-rings after grace if
                # still in bed (or on return to bed). No full dismissal.
                self._caster.stop()
                self._enter_ack_grace()
            else:
                # No bed monitoring on this alarm — nothing to keep watching.
                self._caster.stop()
                self._end("manual")
            return
        if self._elapsed_sec() > self.max_session_sec:
            self._end("timeout")
            return
        if self.state == "RINGING":
            await self._tick_ringing()
        elif self.state == "ACK_GRACE":
            await self._tick_ack_grace()
        elif self.state == "OUT":
            await self._tick_out()
        elif self.state == "ENDED":
            return
        else:
            LOGGER.warning("unknown ring state %s; ending session", self.state)
            self._end("error")

    async def _tick_ringing(self) -> None:
        if self.emfit_enabled:
            in_bed = emfit.cached_in_bed()
            if in_bed is False:
                self._caster.stop()
                self._enter_out()
                return

        state_str = self._caster.player_state().upper()
        reason = self._caster.idle_reason().upper()

        # Ignore stale media state left over from a previous clip until the
        # freshly-cast media actually starts. Otherwise a leftover CANCELLED/
        # FINISHED idle_reason right after _recast() ends the session early.
        if state_str in {"PLAYING", "BUFFERING"}:
            self._seen_playing = True
        if not self._seen_playing:
            return

        if reason == "FINISHED":
            if self.wake_check:
                self._recast()
            else:
                self._end("finished")
            return
        if reason in {"CANCELLED", "INTERRUPTED"} or (
            state_str == "IDLE" and reason not in {"", "FINISHED"}
        ):
            if self.wake_check:
                self._caster.stop()
                self._enter_ack_grace()
            else:
                self._end("ack")
            return

        if self._settle_tick:
            self._settle_tick = False
            self._volume_ack_ticks = 0
            return

        volume = self._caster.get_volume()
        if volume < 0:
            # Volume unknown (not yet connected / transient read failure):
            # never treat this as a user volume change.
            self._volume_ack_ticks = 0
            return
        diff = abs(volume - self.ring_volume)

        if self.volume_ack_enabled:
            if diff > self.volume_ack_epsilon:
                self._volume_ack_ticks += 1
                if self._volume_ack_ticks >= self.volume_ack_ticks_required:
                    if self.wake_check:
                        self._caster.stop()
                        self._enter_ack_grace()
                    else:
                        self._end("ack")
            else:
                self._volume_ack_ticks = 0
        elif diff > self.volume_ack_epsilon:
            self._set_target_volume()

    async def _tick_ack_grace(self) -> None:
        in_bed = None
        if self.emfit_enabled:
            in_bed = emfit.cached_in_bed()
            if in_bed is False:
                self._enter_out()
                return

        if self.grace_start is None:
            self.grace_start = datetime.now()

        if (datetime.now() - self.grace_start).total_seconds() >= self.grace_sec:
            if in_bed is not False:
                self._enter_ringing()

    async def _tick_out(self) -> None:
        if not self.emfit_enabled:
            self._end("no_wake_check")
            return

        in_bed = emfit.cached_in_bed()
        if in_bed is True:
            self._enter_ringing()
            return
        if in_bed is False:
            self.continuous_out_sec += self.tick_sec
            self._continuous_none_sec = 0.0
            if self.continuous_out_sec >= self.awake_confirm_sec:
                self._end("woke")
            return

        self._continuous_none_sec += self.tick_sec
        self.continuous_out_sec = 0.0
        if self._continuous_none_sec >= self.none_continue_sec:
            self._enter_ringing()

    def _enter_ringing(self) -> None:
        self.state = "RINGING"
        self.grace_start = None
        self.out_start = None
        self.continuous_out_sec = 0.0
        self._continuous_none_sec = 0.0
        self._volume_ack_ticks = 0
        self._recast()

    def _enter_ack_grace(self) -> None:
        self.state = "ACK_GRACE"
        self.grace_start = datetime.now()
        self.out_start = None
        self.continuous_out_sec = 0.0
        self._continuous_none_sec = 0.0
        self._volume_ack_ticks = 0

    def _enter_out(self) -> None:
        self.state = "OUT"
        self.out_start = datetime.now()
        self.grace_start = None
        self.continuous_out_sec = 0.0
        self._continuous_none_sec = 0.0
        self._volume_ack_ticks = 0

    def _set_target_volume(self) -> None:
        self._caster.set_volume(self.ring_volume)
        self._settle_tick = True

    def _recast(self) -> None:
        self._seen_playing = False
        self._set_target_volume()
        self._caster.play(self.sound_url, guess_audio_mime(self.sound_url))

    def _end(self, reason: str) -> None:
        self.ended_reason = reason
        self.state = "ENDED"

    def _elapsed_sec(self) -> float:
        return (datetime.now() - self.session_start).total_seconds()

    def status(self) -> dict[str, Any]:
        now = datetime.now()
        session_elapsed = (now - self.session_start).total_seconds()
        grace_remaining = None
        if self.state == "ACK_GRACE" and self.grace_start is not None:
            grace_remaining = max(0.0, self.grace_sec - (now - self.grace_start).total_seconds())
        out_elapsed = None
        if self.out_start is not None:
            out_elapsed = max(0.0, (now - self.out_start).total_seconds())
        return {
            "state": self.state,
            "alarm_id": self.alarm_id,
            "device_name": self.device_name,
            "session_start": self.session_start.isoformat(timespec="seconds"),
            "session_elapsed": session_elapsed,
            "grace_remaining": grace_remaining,
            "out_elapsed": out_elapsed,
            "ended_reason": self.ended_reason,
            "continuous_out_sec": self.continuous_out_sec,
        }


async def start_session(
    alarm_id: int,
    sound_url: str,
    device_name: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    global current_session
    async with _session_lock:
        if current_session is not None and current_session.ended_reason is None:
            return current_session.status()
        session = RingSession(alarm_id, sound_url, device_name, settings)
        current_session = session
        session._task = asyncio.create_task(session.start())
        return session.status()


def snooze_session() -> bool:
    """Web button action: silence + keep monitoring (no full dismiss for
    wake-check sessions). See RingSession.request_snooze."""
    if current_session is None:
        return False
    current_session.request_snooze()
    return True


def stop_session() -> bool:
    """Hard stop — ends the session regardless of wake-check (used internally,
    e.g. when an alarm is deleted)."""
    if current_session is None:
        return False
    current_session.manual_stop()
    return True


def get_status() -> dict[str, Any]:
    if current_session is None:
        return {
            "state": "IDLE",
            "alarm_id": None,
            "device_name": None,
            "session_start": None,
            "session_elapsed": 0,
            "grace_remaining": None,
            "out_elapsed": None,
            "ended_reason": None,
            "continuous_out_sec": 0,
        }
    return current_session.status()
