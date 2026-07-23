from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

import emfit
import player
import ring


class FakeBtPlayer:
    instances: list["FakeBtPlayer"] = []

    def __init__(self, device_name: str, bt_mac: str):
        self.device_name = device_name
        self.bt_mac = bt_mac
        self.playing = False
        self.play_calls: list[tuple[str, float, bool]] = []
        self.stop_calls = 0
        self.ensure_calls = 0
        self.reconnect_calls = 0
        self.restart_calls = 0
        self.restart_result = True
        self.stream_value: bool | None = True
        FakeBtPlayer.instances.append(self)

    def restart_bt_stack(self) -> bool:
        self.restart_calls += 1
        return self.restart_result

    def reconnect(self) -> bool:
        self.reconnect_calls += 1
        return True
    def ensure_connected(self) -> bool:
        self.ensure_calls += 1
        return True

    def play(self, path: str, volume: float, loop: bool = True) -> bool:
        self.play_calls.append((path, volume, loop))
        self.playing = True
        return True

    def stream_active(self) -> bool | None:
        return self.stream_value
    def is_playing(self) -> bool:
        return self.playing

    def stop(self) -> bool:
        self.stop_calls += 1
        self.playing = False
        return True


@pytest.fixture(autouse=True)
def fake_player(monkeypatch):
    FakeBtPlayer.instances = []
    monkeypatch.setattr(player, "BtPlayer", FakeBtPlayer)
    ring.current_session = None
    yield
    ring.current_session = None


def settings(**overrides):
    data = {
        "tick_sec": 0.05,
        "poll_sec": 0.05,
        "awake_confirm_sec": 0.2,
        "grace_sec": 0.1,
        "ring_volume": 1.0,
        "none_continue_sec": 0.1,
        "max_session_sec": 5,
        "wake_check": True,
        "emfit_enabled": False,
        "bt_mac": "",
        "bt_stack_restart": True,
    }
    data.update(overrides)
    return data


def session(**overrides):
    return ring.RingSession(1, "C:/sounds/alarm.mp3", "Miku-Miku Echo", settings(**overrides))


def random_session(**overrides):
    urls = ["C:/sounds/a.mp3", "C:/sounds/b.mp3"]
    return ring.RingSession(1, urls, "Miku-Miku Echo", settings(**overrides))


async def wait_for_play(fake: FakeBtPlayer) -> None:
    for _ in range(100):
        if fake.play_calls:
            return
        await asyncio.sleep(0.001)
    raise AssertionError("playback did not start")


async def set_in_bed(monkeypatch, values):
    remaining = list(values)

    def fake_cached_in_bed():
        if remaining:
            return remaining.pop(0)
        return values[-1] if values else None

    monkeypatch.setattr(emfit, "cached_in_bed", fake_cached_in_bed)


@pytest.mark.asyncio
async def test_bt_stack_restart_runs_before_reconnect(monkeypatch):
    alarm = session(bt_mac="AA:BB:CC:DD:EE:FF", max_session_sec=5)
    fake = FakeBtPlayer.instances[-1]
    calls = []
    fake.restart_bt_stack = lambda: calls.append("restart") or True
    fake.reconnect = lambda: calls.append("reconnect") or True

    async def stop_after_first_tick(_seconds):
        alarm.manual_stop()

    monkeypatch.setattr(ring.asyncio, "sleep", stop_after_first_tick)
    await alarm.start()

    assert calls == ["restart", "reconnect"]


@pytest.mark.asyncio
@pytest.mark.parametrize("restart_enabled, bt_mac", [(False, "AA:BB:CC:DD:EE:FF"), (True, "")])
async def test_bt_stack_restart_is_skipped_when_disabled_or_unconfigured(
    restart_enabled, bt_mac, monkeypatch
):
    alarm = session(bt_mac=bt_mac, bt_stack_restart=restart_enabled, max_session_sec=5)
    fake = FakeBtPlayer.instances[-1]

    async def stop_after_first_tick(_seconds):
        alarm.manual_stop()

    monkeypatch.setattr(ring.asyncio, "sleep", stop_after_first_tick)
    await alarm.start()

    assert fake.restart_calls == 0


@pytest.mark.asyncio
async def test_ringing_continues_when_bt_stack_restart_fails(monkeypatch):
    alarm = session(bt_mac="AA:BB:CC:DD:EE:FF", max_session_sec=5)
    fake = FakeBtPlayer.instances[-1]
    fake.restart_result = False

    async def stop_after_first_tick(_seconds):
        alarm.manual_stop()

    monkeypatch.setattr(ring.asyncio, "sleep", stop_after_first_tick)
    await alarm.start()

    assert fake.restart_calls == 1
    assert fake.reconnect_calls == 1
    assert fake.play_calls


@pytest.mark.asyncio
async def test_start_out_of_bed_still_rings_before_initial_window(monkeypatch):
    await set_in_bed(monkeypatch, [False, False, False, False, False])
    alarm = session(emfit_enabled=True, initial_ring_sec=90, max_session_sec=1800)
    fake = FakeBtPlayer.instances[-1]

    await alarm._tick()

    assert alarm.state == "RINGING"
    assert fake.play_calls

    alarm.session_start = datetime.now() - timedelta(seconds=91)
    await alarm._tick()

    assert alarm.state == "OUT"

@pytest.mark.asyncio
async def test_start_out_of_bed_confirms_woke_after_initial_window(monkeypatch):
    await set_in_bed(monkeypatch, [False, False, False, False, False])
    alarm = session(emfit_enabled=True, initial_ring_sec=0, awake_confirm_sec=0.1, tick_sec=0.02)

    await alarm.start()

    assert alarm.ended_reason == "woke"
    assert FakeBtPlayer.instances[-1].play_calls


@pytest.mark.asyncio
async def test_playback_stopped_while_in_bed_restarts():
    alarm = session(emfit_enabled=False)
    fake = FakeBtPlayer.instances[-1]
    alarm._recast()
    fake.playing = False

    await alarm._tick()

    assert alarm.state == "RINGING"
    assert len(fake.play_calls) == 2
    assert fake.play_calls[-1][2] is True


@pytest.mark.asyncio
async def test_watchdog_restarts_after_two_inactive_stream_checks():
    alarm = session(emfit_enabled=False)
    fake = FakeBtPlayer.instances[-1]
    alarm._recast()
    fake.stream_value = False

    await alarm._tick()
    assert alarm._stream_inactive_checks == 1
    await alarm._tick()

    assert len(fake.play_calls) == 2
    assert alarm._playback_started is True
    assert alarm._stream_inactive_checks == 0


@pytest.mark.asyncio
async def test_playback_replay_resets_inactive_counter():
    alarm = session(emfit_enabled=False)
    fake = FakeBtPlayer.instances[-1]
    alarm._recast()
    fake.stream_value = False

    await alarm._tick()
    assert alarm._stream_inactive_checks == 1
    fake.playing = False
    await alarm._tick()

    assert len(fake.play_calls) == 2
    assert alarm._stream_inactive_checks == 0


@pytest.mark.asyncio
async def test_watchdog_does_not_restart_on_unknown_stream():
    alarm = session(emfit_enabled=False)
    fake = FakeBtPlayer.instances[-1]
    alarm._recast()
    fake.stream_value = None

    await alarm._tick()
    await alarm._tick()

    assert len(fake.play_calls) == 1
@pytest.mark.asyncio
async def test_out_of_bed_stops_playback_and_enters_out(monkeypatch):
    await set_in_bed(monkeypatch, [False])
    alarm = session(emfit_enabled=True, initial_ring_sec=0)
    fake = FakeBtPlayer.instances[-1]

    await alarm._tick()

    assert alarm.state == "OUT"
    assert fake.stop_calls >= 1


@pytest.mark.asyncio
async def test_return_to_bed_re_rings(monkeypatch):
    await set_in_bed(monkeypatch, [False, True])
    alarm = session(emfit_enabled=True, initial_ring_sec=0)
    fake = FakeBtPlayer.instances[-1]
    alarm._recast()

    await alarm._tick()
    assert alarm.state == "OUT"
    await alarm._tick()

    assert alarm.state == "RINGING"
    assert len(fake.play_calls) == 2


@pytest.mark.asyncio
async def test_out_of_bed_sustained_ends_woke(monkeypatch):
    await set_in_bed(monkeypatch, [False, False, False, False, False])
    alarm = session(emfit_enabled=True, initial_ring_sec=0)

    await alarm._tick()
    for _ in range(4):
        await alarm._tick()

    assert alarm.ended_reason == "woke"


@pytest.mark.asyncio
async def test_none_while_ringing_is_treated_as_in_bed(monkeypatch):
    await set_in_bed(monkeypatch, [None])
    alarm = session(emfit_enabled=True, initial_ring_sec=0)

    await alarm._tick()

    assert alarm.state == "RINGING"
    assert alarm.ended_reason is None


@pytest.mark.asyncio
async def test_none_sustained_while_out_returns_to_ringing(monkeypatch):
    await set_in_bed(monkeypatch, [False, None, None])
    alarm = session(emfit_enabled=True, initial_ring_sec=0)

    await alarm._tick()
    await alarm._tick()
    assert alarm.state == "OUT"
    await alarm._tick()

    assert alarm.state == "RINGING"


@pytest.mark.asyncio
async def test_web_snooze_enters_grace_then_re_rings_when_still_in_bed(monkeypatch):
    await set_in_bed(monkeypatch, [True, True])
    alarm = session(emfit_enabled=True, initial_ring_sec=0)
    fake = FakeBtPlayer.instances[-1]
    alarm._recast()
    alarm.request_snooze()

    await alarm._tick()
    assert alarm.state == "ACK_GRACE"
    assert fake.playing is False

    alarm.grace_start = datetime.now() - timedelta(seconds=1)
    await alarm._tick()

    assert alarm.state == "RINGING"
    assert len(fake.play_calls) == 2


@pytest.mark.asyncio
async def test_snooze_without_wake_check_ends_manual():
    alarm = session(emfit_enabled=False, wake_check=False)
    alarm.request_snooze()

    await alarm._tick()

    assert alarm.ended_reason == "manual"


@pytest.mark.asyncio
async def test_non_wake_check_ends_finished_when_playback_ends():
    alarm = session(emfit_enabled=False, wake_check=False)
    fake = FakeBtPlayer.instances[-1]
    alarm._recast()
    fake.playing = False

    await alarm._tick()

    assert alarm.ended_reason == "finished"
    assert fake.play_calls[-1][2] is False


@pytest.mark.asyncio
async def test_manual_stop_ends_manual():
    alarm = session()
    alarm.manual_stop()

    await alarm._tick()

    assert alarm.ended_reason == "manual"


@pytest.mark.asyncio
async def test_max_session_elapsed_ends_timeout():
    alarm = session()
    alarm.session_start = datetime.now() - timedelta(seconds=10)

    await alarm._tick()

    assert alarm.ended_reason == "timeout"


def test_ring_session_accepts_random_sound_paths(monkeypatch):
    monkeypatch.setattr(ring.random, "choice", lambda values: values[-1])
    alarm = random_session()
    fake = FakeBtPlayer.instances[-1]

    alarm._recast()

    assert fake.play_calls[-1][0] == "C:/sounds/b.mp3"
    assert alarm.sound_url == "C:/sounds/b.mp3"


@pytest.mark.asyncio
async def test_bed_entry_announcement_uses_one_shot_without_reconnect():
    status = await ring.start_announcement(
        7,
        "C:/assets/bed_entry_detected.wav",
        "Miku-Miku Echo",
        settings(emfit_enabled=True, wake_check=True),
    )
    announcement = ring.current_session
    assert announcement is not None
    fake = FakeBtPlayer.instances[-1]
    await wait_for_play(fake)

    assert status["session_kind"] == "bed_entry_announcement"
    assert announcement.wake_check is False
    assert announcement.emfit_enabled is False
    assert fake.restart_calls == 0
    assert fake.reconnect_calls == 0
    assert fake.ensure_calls >= 1
    assert fake.play_calls == [("C:/assets/bed_entry_detected.wav", 1.0, False)]

    announcement.manual_stop()
    await asyncio.wait_for(announcement._task, timeout=1)


@pytest.mark.asyncio
async def test_real_alarm_preempts_bed_entry_announcement():
    await ring.start_announcement(
        7,
        "C:/assets/bed_entry_detected.wav",
        "Miku-Miku Echo",
        settings(),
    )
    announcement = ring.current_session
    assert announcement is not None
    announcement_player = FakeBtPlayer.instances[-1]
    await wait_for_play(announcement_player)

    status = await ring.start_session(
        8,
        "C:/sounds/alarm.mp3",
        "Miku-Miku Echo",
        settings(session_kind="wake", session_label="Wake"),
    )

    assert announcement.ended_reason == "preempted"
    assert announcement_player.stop_calls >= 1
    assert status["alarm_id"] == 8
    assert status["session_kind"] == "wake"
    assert ring.current_session is not announcement

    current = ring.current_session
    assert current is not None
    current.manual_stop()
    await asyncio.wait_for(current._task, timeout=1)
    await asyncio.wait_for(announcement._task, timeout=1)


@pytest.mark.asyncio
async def test_immediate_alarm_preemption_prevents_late_announcement_playback():
    await ring.start_announcement(
        7,
        "C:/assets/bed_entry_detected.wav",
        "Miku-Miku Echo",
        settings(),
    )
    announcement = ring.current_session
    assert announcement is not None
    announcement_player = FakeBtPlayer.instances[-1]

    await ring.start_session(
        8,
        "C:/sounds/alarm.mp3",
        "Miku-Miku Echo",
        settings(session_kind="wake", session_label="Wake"),
    )
    await asyncio.wait_for(announcement._task, timeout=1)

    assert announcement.ended_reason == "preempted"
    assert announcement_player.play_calls == []

    current = ring.current_session
    assert current is not None
    current.manual_stop()
    await asyncio.wait_for(current._task, timeout=1)
