from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote

import db
import scheduler


def test_editing_fired_alarm_clears_last_fired_date(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "alarm.db")
    monkeypatch.setattr(scheduler, "get_all_alarms", db.get_all_alarms)

    now = datetime.now()
    later = now + timedelta(minutes=5)
    alarm = db.create_alarm(
        label="Later",
        time=now.strftime("%H:%M"),
        repeat_days=[],
        enabled=False,
        last_fired_date=now.strftime("%Y-%m-%d"),
    )

    updated = db.update_alarm(alarm["id"], time=later.strftime("%H:%M"), enabled=True)
    assert updated is not None
    assert updated["last_fired_date"] is None

    next_alarm = scheduler.get_next_alarm()
    assert next_alarm is not None
    assert next_alarm["id"] == alarm["id"]
    assert 0 < next_alarm["seconds_until"] < 10 * 60


def test_next_alarm_recovers_stale_last_fired_date(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "alarm.db")
    monkeypatch.setattr(scheduler, "get_all_alarms", db.get_all_alarms)

    now = datetime.now()
    later = now + timedelta(minutes=5)
    alarm = db.create_alarm(
        label="Stale",
        time=later.strftime("%H:%M"),
        repeat_days=[],
        enabled=True,
        last_fired_date=now.strftime("%Y-%m-%d"),
    )

    next_alarm = scheduler.get_next_alarm()
    assert next_alarm is not None
    assert next_alarm["id"] == alarm["id"]
    assert db.get_alarm(alarm["id"])["last_fired_date"] is None


def test_random_alarm_sound_refs_expand_to_upload_urls():
    refs = ["one.mp3", "folder name.wav"]
    alarm = {"sound_type": "random", "sound_ref": refs}

    urls = scheduler._sound_urls_for_alarm(alarm, {"fallback_url": ""})

    assert urls == [f"{scheduler.HOST_AUDIO_BASE}/{quote(name)}" for name in refs]


def test_random_alarm_uses_fallback_when_refs_empty():
    alarm = {"sound_type": "random", "sound_ref": "[]"}

    urls = scheduler._sound_urls_for_alarm(alarm, {"fallback_url": "https://example.test/fallback.mp3"})

    assert urls == ["https://example.test/fallback.mp3"]
