from __future__ import annotations

import pytest

import app as alarm_app
import db
import ring


class ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


@pytest.mark.asyncio
async def test_api_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "alarm.db")
    monkeypatch.setattr(alarm_app.asyncio, "to_thread", _to_thread_now)
    monkeypatch.setattr(
        alarm_app,
        "download_youtube_audio",
        lambda url, filename=None: {
            "name": f"{filename or 'youtube'}.mp3",
            "size": 123,
            "url": f"/sounds/{filename or 'youtube'}.mp3",
        },
    )
    ring.current_session = None

    status_json = await alarm_app.api_status()
    assert "state" in status_json
    assert "emfit" in status_json

    alarms = await alarm_app.api_get_alarms()
    assert isinstance(alarms, list)

    created = await alarm_app.api_create_alarm(
        alarm_app.AlarmCreate(
            label="API",
            time="06:45",
            repeat_days=[0, 1],
            enabled=True,
            sound_type="upload",
            sound_ref="alarm_long.mp3",
            volume=0.8,
            devices=["ぬま"],
            wake_check=True,
        )
    )
    alarm_id = created["id"]

    imported = await alarm_app.api_download_youtube_sound(
        alarm_app.YouTubeDownload(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", filename="wake-song")
    )
    assert imported["name"] == "wake-song.mp3"

    updated = await alarm_app.api_update_alarm(
        alarm_id,
        alarm_app.AlarmUpdate(
            label="API Updated",
            enabled=False,
            volume=0.3,
            sound_type="random",
            sound_ref=["alarm_long.mp3", "wake-song.mp3"],
        ),
    )
    assert updated["label"] == "API Updated"
    assert updated["enabled"] is False
    assert updated["sound_type"] == "random"
    assert updated["sound_refs"] == ["alarm_long.mp3", "wake-song.mp3"]

    settings = await alarm_app.api_get_settings()
    assert isinstance(settings, dict)

    updated_settings = await alarm_app.api_update_settings({"ring_volume": 0.35, "default_devices": ["ぬま"]})
    assert updated_settings["ring_volume"] == 0.35

    deleted = await alarm_app.api_delete_alarm(alarm_id)
    assert deleted == {"ok": True}


async def _to_thread_now(func, *args, **kwargs):
    return func(*args, **kwargs)


def test_youtube_progress_line_parses_concrete_fields():
    progress = alarm_app._youtube_progress_from_line("[download]  42.5% of 10.00MiB at 1.25MiB/s ETA 00:08")

    assert progress["state"] == "downloading"
    assert progress["percent"] == 42.5
    assert progress["total"] == "10.00MiB"
    assert progress["speed"] == "1.25MiB/s"
    assert progress["eta"] == "00:08"


def test_youtube_download_job_records_progress_and_result(monkeypatch):
    alarm_app.YOUTUBE_JOBS.clear()
    monkeypatch.setattr(alarm_app.shutil, "which", lambda _name: "/usr/bin/yt-dlp")
    monkeypatch.setattr(alarm_app.threading, "Thread", ImmediateThread)

    def fake_download(url, filename=None, progress_callback=None):
        if progress_callback is not None:
            progress_callback("[download]  55.0% of 8.00MiB at 2.00MiB/s ETA 00:03")
            progress_callback("[ExtractAudio] Destination: wake.mp3")
        return {"name": "wake.mp3", "size": 123, "url": "/sounds/wake.mp3"}

    monkeypatch.setattr(alarm_app, "download_youtube_audio", fake_download)

    job = alarm_app.create_youtube_download_job("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "wake")
    loaded = alarm_app.get_youtube_download_job(job["id"])

    assert loaded is not None
    assert loaded["state"] == "done"
    assert loaded["percent"] == 100.0
    assert loaded["result"]["name"] == "wake.mp3"


def test_replace_sound_repoints_existing_alarm(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "alarm.db")
    monkeypatch.setattr(alarm_app, "SOUNDS_DIR", tmp_path / "sounds")
    alarm_app.SOUNDS_DIR.mkdir()
    (alarm_app.SOUNDS_DIR / "old.mp3").write_bytes(b"ID3old")
    alarm = db.create_alarm(sound_type="upload", sound_ref="old.mp3")

    replaced = alarm_app.replace_sound("old.mp3", "old.wav", b"RIFFnew")
    updated = db.get_alarm(alarm["id"])

    assert replaced["name"] == "old.wav"
    assert not (alarm_app.SOUNDS_DIR / "old.mp3").exists()
    assert (alarm_app.SOUNDS_DIR / "old.wav").exists()
    assert updated is not None
    assert updated["sound_ref"] == "old.wav"
