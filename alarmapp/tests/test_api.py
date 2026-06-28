from __future__ import annotations

from fastapi.testclient import TestClient

import app as alarm_app
import db
import ring


def test_api_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "alarm.db")
    monkeypatch.setattr(alarm_app, "scheduler_loop", lambda: _never())
    monkeypatch.setattr(alarm_app, "emfit_poller", lambda: _never())
    ring.current_session = None

    with TestClient(alarm_app.app) as client:
        status = client.get("/api/status")
        assert status.status_code == 200
        status_json = status.json()
        assert "state" in status_json
        assert "emfit" in status_json

        alarms = client.get("/api/alarms")
        assert alarms.status_code == 200
        assert isinstance(alarms.json(), list)

        created = client.post(
            "/api/alarms",
            json={
                "label": "API",
                "time": "06:45",
                "repeat_days": [0, 1],
                "enabled": True,
                "sound_type": "upload",
                "sound_ref": "alarm_long.mp3",
                "volume": 0.8,
                "devices": ["ぬま"],
                "wake_check": True,
            },
        )
        assert created.status_code == 200
        alarm_id = created.json()["id"]

        updated = client.put(
            f"/api/alarms/{alarm_id}",
            json={"label": "API Updated", "enabled": False, "volume": 0.3},
        )
        assert updated.status_code == 200
        assert updated.json()["label"] == "API Updated"
        assert updated.json()["enabled"] is False

        settings = client.get("/api/settings")
        assert settings.status_code == 200
        assert isinstance(settings.json(), dict)

        updated_settings = client.put(
            "/api/settings",
            json={"ring_volume": 0.35, "default_devices": ["ぬま"]},
        )
        assert updated_settings.status_code == 200
        assert updated_settings.json()["ring_volume"] == 0.35

        deleted = client.delete(f"/api/alarms/{alarm_id}")
        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True}


async def _never():
    await _sleep_forever()


async def _sleep_forever():
    import asyncio

    while True:
        await asyncio.sleep(3600)
