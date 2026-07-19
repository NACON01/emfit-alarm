from __future__ import annotations

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
        FakeBtPlayer.instances.append(self)

    def ensure_connected(self) -> bool:
        self.ensure_calls += 1
        return True

    def play(self, path: str, volume: float, loop: bool = True) -> bool:
        self.play_calls.append((path, volume, loop))
        self.playing = True
        return True

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
    }
    data.update(overrides)
    return data


def session(**overrides):
    return ring.RingSession(1, "C:/sounds/alarm.mp3", "Miku-Miku Echo", settings(**overrides))


def random_session(**overrides):
    urls = ["C:/sounds/a.mp3", "C:/sounds/b.mp3"]
    return ring.RingSession(1, urls, "Miku-Miku Echo", settings(**overrides))


async def set_in_bed(monkeypatch, values):
    remaining = list(values)

    def fake_cached_in_bed():
        if remaining:
            return remaining.pop(0)
        return values[-1] if values else None

    monkeypatch.setattr(emfit, "cached_in_bed", fake_cached_in_bed)


@pytest.mark.asyncio
async def test_start_out_of_bed_does_not_ring_and_confirms_woke(monkeypatch):
    await set_in_bed(monkeypatch, [False, False, False, False, False])
    alarm = session(emfit_enabled=True, awake_confirm_sec=0.1, tick_sec=0.02)

    await alarm.start()

    assert alarm.ended_reason == "woke"
    assert FakeBtPlayer.instances[-1].play_calls == []


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
async def test_out_of_bed_stops_playback_and_enters_out(monkeypatch):
    await set_in_bed(monkeypatch, [False])
    alarm = session(emfit_enabled=True)
    fake = FakeBtPlayer.instances[-1]

    await alarm._tick()

    assert alarm.state == "OUT"
    assert fake.stop_calls >= 1


@pytest.mark.asyncio
async def test_return_to_bed_re_rings(monkeypatch):
    await set_in_bed(monkeypatch, [False, True])
    alarm = session(emfit_enabled=True)
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
    alarm = session(emfit_enabled=True)

    await alarm._tick()
    for _ in range(4):
        await alarm._tick()

    assert alarm.ended_reason == "woke"


@pytest.mark.asyncio
async def test_none_while_ringing_is_treated_as_in_bed(monkeypatch):
    await set_in_bed(monkeypatch, [None])
    alarm = session(emfit_enabled=True)

    await alarm._tick()

    assert alarm.state == "RINGING"
    assert alarm.ended_reason is None


@pytest.mark.asyncio
async def test_none_sustained_while_out_returns_to_ringing(monkeypatch):
    await set_in_bed(monkeypatch, [False, None, None])
    alarm = session(emfit_enabled=True)

    await alarm._tick()
    await alarm._tick()
    assert alarm.state == "OUT"
    await alarm._tick()

    assert alarm.state == "RINGING"


@pytest.mark.asyncio
async def test_web_snooze_enters_grace_then_re_rings_when_still_in_bed(monkeypatch):
    await set_in_bed(monkeypatch, [True, True])
    alarm = session(emfit_enabled=True)
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