from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import caster
import emfit
import ring


class FakeCastSession:
    instances: list["FakeCastSession"] = []
    default_volume = 1.0
    default_player_state = "PLAYING"
    default_idle_reason = ""

    def __init__(self, device_name: str):
        self.device_name = device_name
        self.volume = self.default_volume
        self.state = self.default_player_state
        self.reason = self.default_idle_reason
        self.play_calls: list[tuple[str, str]] = []
        self.stop_calls = 0
        self.set_volume_calls: list[float] = []
        FakeCastSession.instances.append(self)

    def play(self, url: str, mime: str = "audio/mpeg") -> bool:
        self.play_calls.append((url, mime))
        return True

    def stop(self) -> bool:
        self.stop_calls += 1
        return True

    def set_volume(self, level: float) -> bool:
        self.set_volume_calls.append(level)
        self.volume = level
        return True

    def get_volume(self) -> float:
        return self.volume

    def player_state(self) -> str:
        return self.state

    def idle_reason(self) -> str:
        return self.reason


@pytest.fixture(autouse=True)
def fake_cast(monkeypatch):
    FakeCastSession.instances = []
    FakeCastSession.default_volume = 1.0
    FakeCastSession.default_player_state = "PLAYING"
    FakeCastSession.default_idle_reason = ""
    monkeypatch.setattr(caster, "CastSession", FakeCastSession)
    yield
    ring.current_session = None


def settings(**overrides):
    data = {
        "tick_sec": 0.05,
        "poll_sec": 0.05,
        "awake_confirm_sec": 0.2,
        "grace_sec": 0.1,
        "ring_volume": 1.0,
        "volume_ack_epsilon": 0.05,
        "volume_ack_ticks_required": 2,
        "none_continue_sec": 0.1,
        "max_session_sec": 5,
        "volume_ack_enabled": True,
        "wake_check": True,
        "emfit_enabled": False,
    }
    data.update(overrides)
    return data


def session(**overrides):
    return ring.RingSession(1, "http://example.test/alarm.mp3", "ぬま", settings(**overrides))


async def set_in_bed(monkeypatch, values):
    remaining = list(values)

    def fake_cached_in_bed():
        if remaining:
            return remaining.pop(0)
        return values[-1] if values else None

    monkeypatch.setattr(emfit, "cached_in_bed", fake_cached_in_bed)


@pytest.mark.asyncio
async def test_volume_ack_enters_grace_after_two_ticks():
    alarm = session(volume_ack_enabled=True)
    cast = FakeCastSession.instances[-1]
    cast.volume = 0.4

    await alarm._tick()
    assert alarm.state == "RINGING"

    await alarm._tick()
    assert alarm.state == "ACK_GRACE"


@pytest.mark.asyncio
async def test_volume_ack_disabled_resets_volume_and_keeps_ringing():
    alarm = session(volume_ack_enabled=False)
    cast = FakeCastSession.instances[-1]
    cast.volume = 0.4

    await alarm._tick()

    assert alarm.state == "RINGING"
    assert cast.set_volume_calls == [1.0]


@pytest.mark.asyncio
async def test_out_of_bed_then_in_bed_returns_to_ringing(monkeypatch):
    await set_in_bed(monkeypatch, [False, True])
    alarm = session(emfit_enabled=True)

    await alarm._tick()
    assert alarm.state == "OUT"

    await alarm._tick()
    assert alarm.state == "RINGING"


@pytest.mark.asyncio
async def test_out_of_bed_sustained_ends_woke(monkeypatch):
    await set_in_bed(monkeypatch, [False, False, False, False, False])
    alarm = session(emfit_enabled=True)

    await alarm._tick()
    for _ in range(4):
        await alarm._tick()

    assert alarm.ended_reason == "woke"


@pytest.mark.asyncio
async def test_none_while_ringing_is_treated_as_in_bed(monkeypatch):
    await set_in_bed(monkeypatch, [None, None])
    alarm = session(emfit_enabled=True)

    await alarm._tick()

    assert alarm.state == "RINGING"
    assert alarm.ended_reason is None


@pytest.mark.asyncio
async def test_none_sustained_while_out_returns_to_ringing(monkeypatch):
    await set_in_bed(monkeypatch, [False, None, None])
    alarm = session(emfit_enabled=True)

    await alarm._tick()
    assert alarm.state == "OUT"

    await alarm._tick()
    assert alarm.state == "OUT"

    await alarm._tick()
    assert alarm.state == "RINGING"


@pytest.mark.asyncio
async def test_manual_stop_ends_manual():
    alarm = session()
    alarm.manual_stop()

    await alarm._tick()

    assert alarm.ended_reason == "manual"


@pytest.mark.asyncio
async def test_snooze_on_wake_check_enters_grace_not_end(monkeypatch):
    # Web "stop" button on a wake-check alarm = snooze: silence + keep watching,
    # NOT a full dismiss.
    await set_in_bed(monkeypatch, [True])
    alarm = session(emfit_enabled=True)
    alarm.request_snooze()

    await alarm._tick()

    assert alarm.state == "ACK_GRACE"
    assert alarm.ended_reason is None


@pytest.mark.asyncio
async def test_snooze_without_wake_check_ends():
    # With no bed monitoring there is nothing to keep watching, so snooze ends it.
    alarm = session(emfit_enabled=False, wake_check=False)
    alarm.request_snooze()

    await alarm._tick()

    assert alarm.ended_reason == "manual"


@pytest.mark.asyncio
async def test_max_session_elapsed_ends_timeout():
    alarm = session()
    alarm.session_start = datetime.now() - timedelta(seconds=10)

    await alarm._tick()

    assert alarm.ended_reason == "timeout"


@pytest.mark.asyncio
async def test_finished_audio_is_recast():
    FakeCastSession.default_idle_reason = "FINISHED"
    alarm = session()
    cast = FakeCastSession.instances[-1]

    await alarm._tick()

    assert alarm.state == "RINGING"
    assert len(cast.play_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["CANCELLED", "INTERRUPTED", "STOPPED"])
async def test_cancelled_or_interrupted_enters_ack_grace(reason):
    FakeCastSession.default_idle_reason = reason
    alarm = session()

    await alarm._tick()

    assert alarm.state == "ACK_GRACE"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["IDLE", "PAUSED"])
async def test_hardware_media_stop_without_reason_enters_ack_grace_after_two_ticks(state):
    alarm = session(media_stop_ticks_required=2)
    cast = FakeCastSession.instances[-1]

    await alarm._tick()
    cast.state = state
    cast.reason = ""

    await alarm._tick()
    assert alarm.state == "RINGING"

    await alarm._tick()
    assert alarm.state == "ACK_GRACE"


@pytest.mark.asyncio
async def test_hardware_media_stop_without_wake_check_ends_ack():
    alarm = session(wake_check=False, media_stop_ticks_required=2)
    cast = FakeCastSession.instances[-1]

    await alarm._tick()
    cast.state = "IDLE"
    cast.reason = ""
    await alarm._tick()
    await alarm._tick()

    assert alarm.ended_reason == "ack"


@pytest.mark.asyncio
async def test_stale_media_state_before_playback_is_ignored():
    # Right after _recast() the device may still report a leftover idle_reason
    # from the previous clip. It must NOT end/transition the session until the
    # freshly-cast media actually starts playing.
    FakeCastSession.default_player_state = "IDLE"
    FakeCastSession.default_idle_reason = "CANCELLED"
    alarm = session(wake_check=False)
    cast = FakeCastSession.instances[-1]

    await alarm._tick()
    assert alarm.state == "RINGING"
    assert alarm.ended_reason is None

    # Once playback is observed, real end-signals are honored again.
    cast.state = "PLAYING"
    cast.reason = "FINISHED"
    await alarm._tick()
    assert alarm.ended_reason == "finished"
