from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import anti_doze
import db
import ring


MONDAY = datetime(2026, 7, 20)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "alarm.db")
    ring.current_session = None
    yield
    ring.current_session = None


def create_anti_doze(**overrides):
    values = {
        "alarm_kind": "anti_doze",
        "label": "寝落ち防止",
        "time": "01:00",
        "monitor_start": "18:00",
        "reentry_block_min": 60,
        "repeat_days": [0],
        "enabled": True,
        "sound_type": "upload",
        "sound_ref": "alarm_long.mp3",
        "devices": ["Miku-Miku Echo"],
        "wake_check": True,
    }
    values.update(overrides)
    return db.create_alarm(**values)


def test_monitoring_window_spans_midnight_and_uses_start_day():
    alarm = create_anti_doze()

    assert anti_doze.is_monitoring_now(alarm, MONDAY.replace(hour=18))
    assert anti_doze.is_monitoring_now(alarm, (MONDAY + timedelta(days=1)).replace(hour=0, minute=59))
    assert not anti_doze.is_monitoring_now(alarm, (MONDAY + timedelta(days=1)).replace(hour=1))
    assert not anti_doze.is_monitoring_now(alarm, MONDAY.replace(hour=12))


@pytest.mark.asyncio
async def test_continuous_in_bed_for_twenty_minutes_starts_existing_ring(monkeypatch):
    alarm = create_anti_doze()
    calls = []

    async def fake_start(alarm_id, sound_urls, device, settings):
        calls.append((alarm_id, sound_urls, device, settings))
        return {"alarm_id": alarm_id, "session_kind": settings["session_kind"]}

    monkeypatch.setattr(anti_doze.ring, "start_session", fake_start)
    started = MONDAY.replace(hour=20)

    await anti_doze.tick(started, True)
    await anti_doze.tick(started + timedelta(minutes=19, seconds=59), True)
    assert calls == []

    await anti_doze.tick(started + timedelta(minutes=20), True)

    assert len(calls) == 1
    assert calls[0][0] == alarm["id"]
    assert calls[0][2] == "Miku-Miku Echo"
    assert calls[0][3]["wake_check"] is True
    assert db.get_anti_doze_runtime(alarm["id"])["phase"] == anti_doze.FIRED


@pytest.mark.asyncio
async def test_leaving_before_twenty_minutes_resets_countdown(monkeypatch):
    alarm = create_anti_doze()
    calls = []

    async def fake_start(*args):
        calls.append(args)
        return {"alarm_id": alarm["id"], "session_kind": "anti_doze"}

    monkeypatch.setattr(anti_doze.ring, "start_session", fake_start)
    started = MONDAY.replace(hour=20)

    await anti_doze.tick(started, True)
    await anti_doze.tick(started + timedelta(minutes=10), False)
    assert db.get_anti_doze_runtime(alarm["id"]) is None

    await anti_doze.tick(started + timedelta(minutes=11), True)
    await anti_doze.tick(started + timedelta(minutes=30), True)

    assert calls == []


@pytest.mark.asyncio
async def test_entry_before_window_end_still_fires_after_window_end(monkeypatch):
    alarm = create_anti_doze()
    calls = []

    async def fake_start(alarm_id, _urls, _device, settings):
        calls.append(alarm_id)
        return {"alarm_id": alarm_id, "session_kind": settings["session_kind"]}

    monkeypatch.setattr(anti_doze.ring, "start_session", fake_start)
    started = (MONDAY + timedelta(days=1)).replace(hour=0, minute=50)

    await anti_doze.tick(started, True)
    await anti_doze.tick(started + timedelta(minutes=20), True)

    assert calls == [alarm["id"]]


@pytest.mark.asyncio
async def test_reentry_during_cooldown_rings_immediately(monkeypatch):
    alarm = create_anti_doze(reentry_block_min=60)
    ended_at = MONDAY.replace(hour=20, minute=30)
    db.set_anti_doze_runtime(alarm["id"], phase=anti_doze.FIRED)

    await anti_doze.tick(ended_at, False)
    state = db.get_anti_doze_runtime(alarm["id"])
    assert state["phase"] == anti_doze.COOLDOWN
    assert datetime.fromisoformat(state["cooldown_until"]) == ended_at + timedelta(minutes=60)

    calls = []

    async def fake_start(alarm_id, _urls, _device, settings):
        calls.append(alarm_id)
        return {"alarm_id": alarm_id, "session_kind": settings["session_kind"]}

    monkeypatch.setattr(anti_doze.ring, "start_session", fake_start)
    await anti_doze.tick(ended_at + timedelta(minutes=1), True)

    assert calls == [alarm["id"]]
    assert db.get_anti_doze_runtime(alarm["id"])["phase"] == anti_doze.FIRED


@pytest.mark.asyncio
async def test_zero_cooldown_allows_a_new_twenty_minute_countdown():
    alarm = create_anti_doze(reentry_block_min=0)
    ended_at = MONDAY.replace(hour=20, minute=30)
    db.set_anti_doze_runtime(alarm["id"], phase=anti_doze.FIRED)

    await anti_doze.tick(ended_at, False)
    assert db.get_anti_doze_runtime(alarm["id"]) is None

    await anti_doze.tick(ended_at + timedelta(seconds=5), True)
    state = db.get_anti_doze_runtime(alarm["id"])
    assert state["phase"] == anti_doze.COUNTING


@pytest.mark.asyncio
async def test_unknown_sensor_value_cancels_continuous_count(monkeypatch):
    alarm = create_anti_doze()
    started = MONDAY.replace(hour=20)
    await anti_doze.tick(started, True)

    monkeypatch.setattr(anti_doze.emfit, "cached_in_bed", lambda: None)
    await anti_doze.tick(started + timedelta(minutes=10))

    assert db.get_anti_doze_runtime(alarm["id"]) is None


def test_invalid_or_equal_monitoring_times_are_rejected():
    with pytest.raises(ValueError):
        create_anti_doze(monitor_start="01:00", time="01:00")
    with pytest.raises(ValueError):
        create_anti_doze(monitor_start="not-a-time")
