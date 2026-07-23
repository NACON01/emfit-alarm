from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import anti_doze
import bed_entry
import db
import ring


MONDAY = datetime(2026, 7, 20, 20, 0)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "alarm.db")
    bed_entry.reset_state()
    ring.current_session = None
    yield
    bed_entry.reset_state()
    ring.current_session = None


def create_wake(**overrides):
    values = {
        "alarm_kind": "wake",
        "label": "Wake",
        "time": "07:00",
        "repeat_days": [0],
        "enabled": True,
        "sound_type": "upload",
        "sound_ref": "alarm_long.mp3",
        "volume": 0.6,
        "devices": ["Miku-Miku Echo"],
        "wake_check": True,
    }
    values.update(overrides)
    return db.create_alarm(**values)


def create_anti_doze(**overrides):
    values = {
        "alarm_kind": "anti_doze",
        "label": "No dozing",
        "time": "01:00",
        "monitor_start": "18:00",
        "anti_doze_delay_min": 20,
        "reentry_block_min": 60,
        "repeat_days": [0],
        "enabled": True,
        "sound_type": "upload",
        "sound_ref": "alarm_long.mp3",
        "volume": 0.5,
        "devices": ["Miku-Miku Echo"],
        "wake_check": True,
    }
    values.update(overrides)
    return db.create_alarm(**values)


def fake_announcement(monkeypatch, calls):
    async def fake_start(alarm_id, sound_url, device_name, settings):
        calls.append((alarm_id, sound_url, device_name, settings))
        return {"alarm_id": alarm_id, "session_kind": "bed_entry_announcement"}

    monkeypatch.setattr(bed_entry.ring, "start_announcement", fake_start)


@pytest.mark.asyncio
async def test_initial_in_bed_value_does_not_announce(monkeypatch):
    create_wake()
    calls = []
    fake_announcement(monkeypatch, calls)

    assert await bed_entry.observe(True, MONDAY) is False
    assert calls == []
    assert bed_entry.get_status()["last_result"] == "baseline_in_bed"


@pytest.mark.asyncio
async def test_stable_out_to_in_announces_once_for_wake_alarm(monkeypatch):
    wake = create_wake()
    calls = []
    fake_announcement(monkeypatch, calls)

    await bed_entry.observe(False, MONDAY)
    await bed_entry.observe(False, MONDAY + timedelta(seconds=10))
    assert await bed_entry.observe(True, MONDAY + timedelta(seconds=20)) is True
    assert await bed_entry.observe(True, MONDAY + timedelta(seconds=30)) is False

    assert len(calls) == 1
    assert calls[0][0] == wake["id"]
    assert calls[0][2] == "Miku-Miku Echo"
    assert calls[0][3]["ring_volume"] == 0.6
    assert bed_entry.get_status()["last_result"] == "in_bed_without_armed_transition"


@pytest.mark.asyncio
async def test_active_anti_doze_is_preferred_and_both_features_announce_once(monkeypatch):
    create_wake()
    anti = create_anti_doze()
    calls = []
    fake_announcement(monkeypatch, calls)

    await bed_entry.observe(False, MONDAY)
    await bed_entry.observe(False, MONDAY + timedelta(seconds=10))
    await bed_entry.observe(True, MONDAY + timedelta(seconds=20))

    assert len(calls) == 1
    assert calls[0][0] == anti["id"]
    assert calls[0][3]["ring_volume"] == 0.5


@pytest.mark.asyncio
async def test_anti_doze_outside_monitoring_window_does_not_announce(monkeypatch):
    create_anti_doze()
    calls = []
    fake_announcement(monkeypatch, calls)
    noon = MONDAY.replace(hour=12)

    await bed_entry.observe(False, noon)
    await bed_entry.observe(False, noon + timedelta(seconds=10))
    assert await bed_entry.observe(True, noon + timedelta(seconds=20)) is False

    assert calls == []
    assert bed_entry.get_status()["last_result"] == "no_eligible_alarm"


@pytest.mark.asyncio
async def test_reentry_during_cooldown_defers_to_immediate_alarm(monkeypatch):
    anti = create_anti_doze()
    db.set_anti_doze_runtime(
        anti["id"],
        phase=anti_doze.COOLDOWN,
        cooldown_until=(MONDAY + timedelta(minutes=30)).isoformat(timespec="seconds"),
    )
    calls = []
    fake_announcement(monkeypatch, calls)

    await bed_entry.observe(False, MONDAY)
    await bed_entry.observe(False, MONDAY + timedelta(seconds=10))
    assert await bed_entry.observe(True, MONDAY + timedelta(seconds=20)) is False

    assert calls == []
    assert bed_entry.get_status()["last_result"] == "anti_doze_cooldown"


@pytest.mark.asyncio
async def test_long_unknown_gap_does_not_create_false_entry_announcement(monkeypatch):
    create_wake()
    calls = []
    fake_announcement(monkeypatch, calls)

    await bed_entry.observe(False, MONDAY)
    await bed_entry.observe(False, MONDAY + timedelta(seconds=10))
    await bed_entry.observe(None, MONDAY + timedelta(seconds=20))
    assert await bed_entry.observe(True, MONDAY + timedelta(seconds=80)) is False

    assert calls == []
    assert bed_entry.get_status()["last_result"] == "in_bed_without_armed_transition"
