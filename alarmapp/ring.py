from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from typing import Any

import emfit
import player


LOGGER = logging.getLogger(__name__)


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
        sound_url: str | list[str],
        device_name: str,
        settings_dict: dict[str, Any],
    ):
        self.alarm_id = alarm_id
        if isinstance(sound_url, list):
            self.sound_urls = [str(url) for url in sound_url if str(url)]
        else:
            self.sound_urls = [str(sound_url)] if str(sound_url) else []
        self.sound_url = self.sound_urls[0] if self.sound_urls else ""
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
        self.tick_sec = max(0.01, _as_float(self.settings.get("tick_sec"), 1.0))
        self.poll_sec = max(0.01, _as_float(self.settings.get("poll_sec"), 5.0))
        self.ring_volume = max(0.0, min(1.0, _as_float(self.settings.get("ring_volume"), 1.0)))
        self.awake_confirm_sec = max(0.01, _as_float(self.settings.get("awake_confirm_sec"), 180.0))
        self.grace_sec = max(0.01, _as_float(self.settings.get("grace_sec"), 120.0))
        self.none_continue_sec = max(0.01, _as_float(self.settings.get("none_continue_sec"), 60.0))
        self.initial_ring_sec = max(0.0, _as_float(self.settings.get("initial_ring_sec"), 90.0))
        self.max_session_sec = max(0.01, _as_float(self.settings.get("max_session_sec"), 1800.0))
        self.wake_check = _as_bool(self.settings.get("wake_check"), True)
        self.emfit_enabled = _as_bool(self.settings.get("emfit_enabled"), True) and self.wake_check
        self.player = player.BtPlayer(device_name, str(self.settings.get("bt_mac") or ""))
        self._playback_started = False
        self._stream_inactive_checks = 0

    def request_snooze(self) -> None:
        """Silence the alarm temporarily while continuing bed monitoring."""
        self._snooze_requested = True

    def manual_stop(self) -> None:
        self._hard_stop = True

    async def start(self) -> None:
        initial_in_bed = emfit.cached_in_bed() if self.emfit_enabled else None
        LOGGER.info(
            "session start alarm=%s device=%s initial_in_bed=%s sound_path=%s",
            self.alarm_id,
            self.device_name,
            initial_in_bed,
            self.sound_url,
        )
        try:
            reconnect_ok = await asyncio.to_thread(self.player.reconnect)
        except Exception as exc:
            reconnect_ok = False
            LOGGER.warning("Bluetooth reconnect raised alarm=%s: %s", self.alarm_id, exc)
        LOGGER.info("Bluetooth reconnect result alarm=%s ok=%s", self.alarm_id, reconnect_ok)
        self._recast()
        try:
            while self.ended_reason is None:
                await self._tick()
                if self.ended_reason is None:
                    await asyncio.sleep(self.tick_sec)
        finally:
            self.player.stop()
            await self._clear_current()
            LOGGER.info("ring session ended alarm=%s reason=%s", self.alarm_id, self.ended_reason)

    async def _clear_current(self) -> None:
        global current_session
        async with _session_lock:
            if current_session is self:
                current_session = None

    async def _tick(self) -> None:
        if self._hard_stop:
            self.player.stop()
            self._end("manual")
            return
        if self._snooze_requested:
            self._snooze_requested = False
            self.player.stop()
            if self.wake_check and self.emfit_enabled:
                self._enter_ack_grace("web_snooze")
            else:
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
        elif self.state != "ENDED":
            LOGGER.warning("unknown ring state %s; ending session", self.state)
            self._end("error")

    async def _tick_ringing(self) -> None:
        in_bed = emfit.cached_in_bed() if self.emfit_enabled else None
        if self.emfit_enabled and in_bed is False and self._elapsed_sec() >= self.initial_ring_sec:
            self.player.stop()
            self._enter_out("sensor_out_after_initial_ring")
            return

        if self.player.is_playing():
            stream_active = self.player.stream_active()
            if stream_active is False:
                self._stream_inactive_checks += 1
                if self._stream_inactive_checks >= 2:
                    LOGGER.warning(
                        "watchdog restarting playback alarm=%s path=%s inactive_checks=%s",
                        self.alarm_id,
                        self.sound_url,
                        self._stream_inactive_checks,
                    )
                    self.player.stop()
                    restarted = self.player.play(
                        self.sound_url,
                        self.ring_volume,
                        loop=self.wake_check,
                    )
                    LOGGER.info("watchdog restart result alarm=%s restarted=%s", self.alarm_id, restarted)
                    self._stream_inactive_checks = 0
                return
            self._stream_inactive_checks = 0
            return

        self._stream_inactive_checks = 0
        if not self.wake_check and self._playback_started:
            self._end("finished")
            return
        if not self.player.ensure_connected():
            return
        self._playback_started = self.player.play(
            self.sound_url,
            self.ring_volume,
            loop=self.wake_check,
        )

    async def _tick_ack_grace(self) -> None:
        in_bed = None
        if self.emfit_enabled:
            in_bed = emfit.cached_in_bed()
            if in_bed is False:
                self._enter_out("sensor_out_during_ack_grace")
                return

        if self.grace_start is None:
            self.grace_start = datetime.now()
        if (datetime.now() - self.grace_start).total_seconds() >= self.grace_sec:
            if in_bed is not False:
                self._enter_ringing("sensor_in_bed_after_grace")

    async def _tick_out(self) -> None:
        if not self.emfit_enabled:
            self._end("no_wake_check")
            return

        in_bed = emfit.cached_in_bed()
        if in_bed is True:
            self._enter_ringing("sensor_in_bed")
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
            self._enter_ringing("sensor_in_bed")

    def _set_state(self, state: str, reason: str) -> None:
        previous = self.state
        self.state = state
        if previous != state:
            LOGGER.info(
                "state transition alarm=%s %s->%s reason=%s",
                self.alarm_id,
                previous,
                state,
                reason,
            )

    def _enter_ringing(self, reason: str = "sensor_in_bed") -> None:
        self._set_state("RINGING", reason)
        self.grace_start = None
        self.out_start = None
        self.continuous_out_sec = 0.0
        self._continuous_none_sec = 0.0
        self._stream_inactive_checks = 0
        self._recast()

    def _enter_ack_grace(self, reason: str = "web_snooze") -> None:
        self._set_state("ACK_GRACE", reason)
        self.grace_start = datetime.now()
        self.out_start = None
        self.continuous_out_sec = 0.0
        self._continuous_none_sec = 0.0

    def _enter_out(self, reason: str = "sensor_out") -> None:
        self._set_state("OUT", reason)
        self.out_start = datetime.now()
        self.grace_start = None
        self.continuous_out_sec = 0.0
        self._continuous_none_sec = 0.0

    def _recast(self) -> None:
        if self.sound_urls:
            self.sound_url = random.choice(self.sound_urls)
        self._playback_started = False
        self._stream_inactive_checks = 0
        if self.player.ensure_connected():
            self._playback_started = self.player.play(
                self.sound_url,
                self.ring_volume,
                loop=self.wake_check,
            )

    def _end(self, reason: str) -> None:
        self.ended_reason = reason
        previous = self.state
        self.state = "ENDED"
        LOGGER.info("session end alarm=%s reason=%s state=%s->ENDED", self.alarm_id, reason, previous)

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


async def start_session(alarm_id: int, sound_url: str | list[str], device_name: str, settings: dict[str, Any]) -> dict[str, Any]:
    global current_session
    async with _session_lock:
        if current_session is not None and current_session.ended_reason is None:
            return current_session.status()
        session = RingSession(alarm_id, sound_url, device_name, settings)
        current_session = session
        session._task = asyncio.create_task(session.start())
        return session.status()


def snooze_session() -> bool:
    if current_session is None:
        return False
    current_session.request_snooze()
    return True


def stop_session() -> bool:
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