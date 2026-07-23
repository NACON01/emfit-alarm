from __future__ import annotations

import sqlite3

import db


def test_alarm_crud_and_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "alarm.db")

    created = db.create_alarm(
        label="Morning",
        time="07:30",
        repeat_days=[0, 1, 2],
        enabled=True,
        sound_type="upload",
        sound_ref="alarm_long.mp3",
        volume=0.75,
        devices=["Miku-Miku Echo"],
        wake_check=True,
    )

    loaded = db.get_alarm(created["id"])
    assert loaded is not None
    assert loaded["label"] == "Morning"

    updated = db.update_alarm(
        created["id"],
        label="Updated",
        time="08:00",
        repeat_days=[5, 6],
        enabled=False,
        volume=0.5,
        devices=["Bedroom"],
        wake_check=False,
    )
    assert updated is not None
    assert updated["label"] == "Updated"
    assert updated["enabled"] == 0
    assert updated["volume"] == 0.5

    settings = db.update_settings(
        {
            "emfit_enabled": False,
            "ring_volume": 0.4,
            "default_devices": ["Bedroom", "Miku-Miku Echo"],
            "fallback_url": "https://example.test/alarm.mp3",
        }
    )
    assert settings["emfit_enabled"] is False
    assert settings["ring_volume"] == 0.4
    assert settings["default_devices"] == ["Bedroom", "Miku-Miku Echo"]
    assert settings["fallback_url"] == "https://example.test/alarm.mp3"

    assert db.delete_alarm(created["id"]) is True
    assert db.get_alarm(created["id"]) is None


def test_init_db_migrates_existing_alarm_table(tmp_path, monkeypatch):
    db_path = tmp_path / "alarm.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE alarms (
                id INTEGER PRIMARY KEY,
                label TEXT,
                time TEXT,
                repeat_days TEXT,
                enabled INTEGER,
                sound_type TEXT,
                sound_ref TEXT,
                volume REAL,
                devices TEXT,
                wake_check INTEGER,
                last_fired_date TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute("INSERT INTO alarms(id, label, time) VALUES(1, 'Legacy', '07:00')")

    db.init_db()
    alarm = db.get_alarm(1)

    assert alarm["alarm_kind"] == "wake"
    assert alarm["monitor_start"] is None
    assert alarm["reentry_block_min"] == 0
