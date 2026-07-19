from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

import player
import emfit
import ring
from db import create_alarm, delete_alarm, get_all_alarms, get_alarm, get_settings, init_db, update_alarm, update_settings
from scheduler import get_next_alarm, scheduler_loop


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
SOUNDS_DIR = ROOT_DIR / "sounds"
UNSAFE_SOUND_CHARS_RE = re.compile(r"[\x00-\x1f\x7f/\\]+")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".flac")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
DOWNLOAD_PERCENT_RE = re.compile(r"\[download\]\s+(?P<percent>\d+(?:\.\d+)?)%")
DOWNLOAD_TOTAL_RE = re.compile(r"\bof\s+~?\s*(?P<total>[^\s]+)")
DOWNLOAD_SPEED_RE = re.compile(r"\bat\s+(?P<speed>[^\s]+/s)")
DOWNLOAD_ETA_RE = re.compile(r"\bETA\s+(?P<eta>[^\s]+)")
DOWNLOAD_FRAGMENT_RE = re.compile(r"\((?P<fragment>frag\s+[^)]+)\)")
YOUTUBE_JOBS: dict[str, dict[str, Any]] = {}
YOUTUBE_JOBS_LOCK = threading.Lock()
YOUTUBE_JOB_TTL_SEC = 3600


try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field

    FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in dependency-limited environments.
    FASTAPI_AVAILABLE = False


def _json_list(value: Any, default: list[Any] | None = None) -> list[Any]:
    if default is None:
        default = []
    if value in (None, ""):
        return default
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, list) else default
    except (TypeError, json.JSONDecodeError):
        return default


def _model_payload(model: Any, exclude_unset: bool = False) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def _bool_int(value: Any) -> int:
    if isinstance(value, str):
        return int(value.lower() in {"1", "true", "yes", "on"})
    return int(bool(value))


def public_alarm(alarm: dict[str, Any]) -> dict[str, Any]:
    return {
        **alarm,
        "enabled": bool(alarm.get("enabled")),
        "wake_check": bool(alarm.get("wake_check")),
        "repeat_days": _json_list(alarm.get("repeat_days"), []),
        "devices": _json_list(alarm.get("devices"), ["Miku-Miku Echo"]),
        "sound_refs": _sound_refs_for_alarm(alarm),
    }


def list_sound_files() -> list[dict[str, Any]]:
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    sounds = []
    for path in sorted(SOUNDS_DIR.iterdir()):
        if not path.is_file():
            continue
        sounds.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "url": sound_file_url(path.name),
            }
        )
    return sounds


def _sound_info(path: Path) -> dict[str, Any]:
    return {"name": path.name, "size": path.stat().st_size, "url": sound_file_url(path.name)}


def sound_file_url(name: str) -> str:
    return f"/sounds/{quote(name)}"


def _safe_sound_name(name: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    safe = UNSAFE_SOUND_CHARS_RE.sub("_", base).strip("._ \t\r\n")
    if not safe:
        raise ValueError("empty filename")
    return safe


def _sound_path(name: str) -> Path:
    safe = _safe_sound_name(name)
    path = (SOUNDS_DIR / safe).resolve()
    if SOUNDS_DIR.resolve() not in path.parents:
        raise ValueError("invalid sound path")
    return path


def _unique_sound_path(name: str) -> Path:
    candidate = _sound_path(name)
    if candidate.suffix == "":
        candidate = candidate.with_suffix(".mp3")
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(2, 1000):
        next_candidate = _sound_path(f"{stem}-{index}{suffix}")
        if not next_candidate.exists():
            return next_candidate
    raise FileExistsError("could not find a unique sound filename")


def _sound_refs_for_alarm(alarm: dict[str, Any]) -> list[str]:
    sound_ref = alarm.get("sound_ref") or ""
    if alarm.get("sound_type") == "random":
        return [str(item) for item in _json_list(sound_ref, []) if str(item)]
    if alarm.get("sound_type") == "upload" and sound_ref:
        return [str(sound_ref)]
    return []


def _fallback_sound_name(excluded_name: str | None = None) -> str:
    for sound in list_sound_files():
        if sound["name"] != excluded_name:
            return str(sound["name"])
    return "alarm_long.mp3"


def _repoint_sound_refs(old_name: str, new_name: str) -> None:
    for alarm in get_all_alarms():
        if alarm.get("sound_type") == "upload" and alarm.get("sound_ref") == old_name:
            update_alarm(int(alarm["id"]), sound_ref=new_name)
        elif alarm.get("sound_type") == "random":
            refs = _sound_refs_for_alarm(alarm)
            next_refs = [new_name if ref == old_name else ref for ref in refs]
            if next_refs != refs:
                update_alarm(int(alarm["id"]), sound_ref=next_refs)


def rename_sound(old_name: str, new_name: str) -> dict[str, Any]:
    """Rename a sound file (keeping its original extension) and repoint any
    alarms that referenced it. Returns the new sound's info."""
    src = _sound_path(old_name)
    if not src.exists():
        raise FileNotFoundError("sound not found")
    ext = src.suffix
    base = os.path.basename(new_name or "")
    if base.lower().endswith(ext.lower()):
        base = base[: -len(ext)]
    safe_base = _safe_sound_name(base)
    if not safe_base:
        raise ValueError("empty filename")
    dst = _sound_path(safe_base + ext)
    if dst != src and dst.exists():
        raise FileExistsError("a sound with that name already exists")
    src.rename(dst)
    _repoint_sound_refs(src.name, dst.name)
    return _sound_info(dst)


def replace_sound(old_name: str, new_name: str, data: bytes) -> dict[str, Any]:
    src = _sound_path(old_name)
    if not src.exists():
        raise FileNotFoundError("sound not found")
    filename = _safe_sound_name(new_name or "")
    if not filename.lower().endswith(AUDIO_EXTENSIONS):
        raise ValueError("unsupported audio extension")
    if not data:
        raise ValueError("empty upload")
    dst = _sound_path(filename)
    if dst != src and dst.exists():
        raise FileExistsError("a sound with that name already exists")
    dst.write_bytes(data)
    if dst != src and src.exists():
        src.unlink()
        _repoint_sound_refs(src.name, dst.name)
    return _sound_info(dst)


def delete_sound(name: str) -> bool:
    path = _sound_path(name)
    existed = path.exists()
    if existed:
        path.unlink()

    replacement = _fallback_sound_name(path.name)
    for alarm in get_all_alarms():
        if alarm.get("sound_type") == "upload" and alarm.get("sound_ref") == path.name:
            update_alarm(int(alarm["id"]), sound_ref=replacement)
        elif alarm.get("sound_type") == "random":
            refs = [ref for ref in _sound_refs_for_alarm(alarm) if ref != path.name]
            if len(refs) >= 2:
                update_alarm(int(alarm["id"]), sound_ref=refs)
            elif len(refs) == 1:
                update_alarm(int(alarm["id"]), sound_type="upload", sound_ref=refs[0])
            else:
                update_alarm(int(alarm["id"]), sound_type="upload", sound_ref=replacement)
    return existed


def _validate_youtube_url(url: str) -> str:
    trimmed = str(url or "").strip()
    parsed = urlparse(trimmed)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in YOUTUBE_HOSTS:
        raise ValueError("YouTube URLを入力してください")
    return trimmed


def _yt_dlp_error(stderr: str, stdout: str) -> str:
    combined = "\n".join(part for part in [stderr.strip(), stdout.strip()] if part)
    if not combined:
        return "yt-dlp failed"
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    return "\n".join(lines[-4:])[:800]


def _clean_progress_line(line: str) -> str:
    return ANSI_RE.sub("", str(line or "")).strip()


def _youtube_progress_from_line(line: str) -> dict[str, Any]:
    clean = _clean_progress_line(line)
    if not clean:
        return {}

    lower = clean.lower()
    if "[download]" in clean:
        updates: dict[str, Any] = {"state": "downloading", "message": clean}
        percent_match = DOWNLOAD_PERCENT_RE.search(clean)
        if percent_match:
            updates["percent"] = float(percent_match.group("percent"))
        total_match = DOWNLOAD_TOTAL_RE.search(clean)
        if total_match:
            updates["total"] = total_match.group("total")
        speed_match = DOWNLOAD_SPEED_RE.search(clean)
        if speed_match:
            updates["speed"] = speed_match.group("speed")
        eta_match = DOWNLOAD_ETA_RE.search(clean)
        if eta_match:
            updates["eta"] = eta_match.group("eta")
        fragment_match = DOWNLOAD_FRAGMENT_RE.search(clean)
        if fragment_match:
            updates["fragment"] = fragment_match.group("fragment")
        if "100%" in clean:
            updates["percent"] = 100.0
            updates["eta"] = None
        return updates

    if "[extractaudio]" in lower or "destination:" in lower and "extractaudio" in lower:
        return {"state": "processing", "message": clean, "percent": 100.0, "eta": None}
    if lower.startswith("deleting original file") or lower.startswith("[metadata]"):
        return {"state": "processing", "message": clean, "percent": 100.0, "eta": None}
    if clean.startswith("["):
        return {"message": clean}
    return {"message": clean}


def _youtube_job_payload(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key != "thread"}


def _purge_old_youtube_jobs() -> None:
    cutoff = time.time() - YOUTUBE_JOB_TTL_SEC
    with YOUTUBE_JOBS_LOCK:
        for job_id, job in list(YOUTUBE_JOBS.items()):
            if float(job.get("updated_ts", 0)) < cutoff and job.get("state") in {"done", "error"}:
                YOUTUBE_JOBS.pop(job_id, None)


def _set_youtube_job(job_id: str, **updates: Any) -> dict[str, Any] | None:
    with YOUTUBE_JOBS_LOCK:
        job = YOUTUBE_JOBS.get(job_id)
        if job is None:
            return None
        job.update(updates)
        job["updated_ts"] = time.time()
        job["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(job["updated_ts"]))
        return _youtube_job_payload(job.copy())


def get_youtube_download_job(job_id: str) -> dict[str, Any] | None:
    with YOUTUBE_JOBS_LOCK:
        job = YOUTUBE_JOBS.get(job_id)
        return _youtube_job_payload(job.copy()) if job is not None else None


def _update_youtube_job_from_line(job_id: str, line: str) -> None:
    updates = _youtube_progress_from_line(line)
    if updates:
        _set_youtube_job(job_id, **updates)


def _run_youtube_download_job(job_id: str, url: str, filename: str | None) -> None:
    _set_youtube_job(job_id, state="downloading", message="yt-dlpを開始しています")
    try:
        result = download_youtube_audio(url, filename, progress_callback=lambda line: _update_youtube_job_from_line(job_id, line))
        _set_youtube_job(
            job_id,
            state="done",
            percent=100.0,
            eta=None,
            result=result,
            message=f"完了: {result['name']}",
        )
    except FileNotFoundError as exc:
        _set_youtube_job(job_id, state="error", error=str(exc), message=str(exc))
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        _set_youtube_job(job_id, state="error", error=str(exc), message=str(exc))


def create_youtube_download_job(url: str, filename: str | None = None) -> dict[str, Any]:
    safe_url = _validate_youtube_url(url)
    if shutil.which("yt-dlp") is None:
        raise FileNotFoundError("yt-dlp is not installed")
    _purge_old_youtube_jobs()
    now_ts = time.time()
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "state": "queued",
        "url": safe_url,
        "filename": filename or "",
        "percent": None,
        "total": "",
        "speed": "",
        "eta": "",
        "fragment": "",
        "message": "待機中",
        "error": "",
        "result": None,
        "created_ts": now_ts,
        "updated_ts": now_ts,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now_ts)),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now_ts)),
    }
    thread = threading.Thread(target=_run_youtube_download_job, args=(job_id, safe_url, filename), daemon=True)
    job["thread"] = thread
    with YOUTUBE_JOBS_LOCK:
        YOUTUBE_JOBS[job_id] = job
    thread.start()
    return _youtube_job_payload(job.copy())


def download_youtube_audio(
    url: str,
    filename: str | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Download one YouTube URL as an MP3 alarm sound using yt-dlp."""
    safe_url = _validate_youtube_url(url)
    binary = shutil.which("yt-dlp")
    if binary is None:
        raise FileNotFoundError("yt-dlp is not installed")

    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="alarm-ytdlp-") as tmp:
        temp_dir = Path(tmp)
        output_template = str(temp_dir / "%(title).80s-%(id)s.%(ext)s")
        cmd = [
            binary,
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--newline",
            "--progress",
            "--progress-delta",
            "0.5",
            "--no-color",
            "--restrict-filenames",
            "--no-mtime",
            "-o",
            output_template,
            safe_url,
        ]
        output_lines: list[str] = []
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                output_lines.append(line)
                if progress_callback is not None:
                    progress_callback(line)
            returncode = process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            process.kill()
            raise
        if returncode != 0:
            raise RuntimeError(_yt_dlp_error("", "".join(output_lines)))

        candidates = [path for path in temp_dir.iterdir() if path.is_file() and path.suffix.lower() == ".mp3"]
        if not candidates:
            candidates = [path for path in temp_dir.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS]
        if not candidates:
            raise RuntimeError("downloaded audio file was not found")

        source = max(candidates, key=lambda item: item.stat().st_mtime)
        if filename:
            base = _safe_sound_name(filename)
            if not base.lower().endswith(".mp3"):
                base = f"{Path(base).stem}.mp3"
        else:
            base = _safe_sound_name(source.name)
            if not base.lower().endswith(".mp3"):
                base = f"{Path(base).stem}.mp3"
        destination = _unique_sound_path(base)
        shutil.move(str(source), destination)
        return _sound_info(destination)


TEST_RING_SECONDS = 20
REAL_TEST_MAX_SECONDS = 120


def _build_test_ring(mode: str = "sound") -> tuple[str, str, dict[str, Any]]:
    """Build args for a test ring.

    mode="sound": just play the sound for a fixed time, no bed logic (quick check).
    mode="real" : exercise the real anti-oversleep behaviour (volume-ACK snooze +
                  emfit bed monitoring) with a safety cap so the user can feel it.
    """
    settings = get_settings()
    sounds = list_sound_files()
    sound_name = sounds[0]["name"] if sounds else "alarm_long.mp3"
    sound_url = str(_sound_path(sound_name))
    devices = settings.get("default_devices") or ["Miku-Miku Echo"]
    if not isinstance(devices, list):
        devices = _json_list(devices, ["Miku-Miku Echo"])
    device = str(devices[0]) if devices else "Miku-Miku Echo"
    if mode == "real":
        test_settings = {
            **settings,
            # keep the configured sensor and timing settings,
            "wake_check": True,
            "max_session_sec": REAL_TEST_MAX_SECONDS,
        }
    else:
        test_settings = {
            **settings,
            "emfit_enabled": False,
            "wake_check": False,
            "max_session_sec": TEST_RING_SECONDS,
        }
    return sound_url, device, test_settings


def _status_payload() -> dict[str, Any]:
    status = ring.get_status()
    return {
        **status,
        "emfit": emfit.last_status.copy(),
        "next_alarm": get_next_alarm(),
    }


async def emfit_poller() -> None:
    while True:
        settings = get_settings()
        if settings.get("emfit_enabled", True):
            await emfit.get_in_bed()
        await asyncio.sleep(max(1.0, float(settings.get("poll_sec", 5))))


if FASTAPI_AVAILABLE:

    class AlarmCreate(BaseModel):
        label: str = "Alarm"
        time: str
        repeat_days: list[int] = Field(default_factory=list)
        enabled: bool = True
        sound_type: str = "upload"
        sound_ref: str | list[str] = "alarm_long.mp3"
        volume: float = 1.0
        devices: list[str] = Field(default_factory=lambda: ["Miku-Miku Echo"])
        wake_check: bool = True


    class AlarmUpdate(BaseModel):
        label: str | None = None
        time: str | None = None
        repeat_days: list[int] | None = None
        enabled: bool | None = None
        sound_type: str | None = None
        sound_ref: str | list[str] | None = None
        volume: float | None = None
        devices: list[str] | None = None
        wake_check: bool | None = None
        last_fired_date: str | None = None


    class YouTubeDownload(BaseModel):
        url: str
        filename: str | None = None


    app = FastAPI(title="Wake Alarm", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


    @app.on_event("startup")
    async def startup() -> None:
        init_db()
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        asyncio.create_task(scheduler_loop())
        asyncio.create_task(emfit_poller())


    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.mount("/sounds", StaticFiles(directory=SOUNDS_DIR), name="sounds")


    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")


    @app.get("/api/alarms")
    async def api_get_alarms() -> list[dict[str, Any]]:
        return [public_alarm(alarm) for alarm in get_all_alarms()]


    @app.post("/api/alarms")
    async def api_create_alarm(payload: AlarmCreate) -> dict[str, Any]:
        alarm = create_alarm(**_model_payload(payload))
        return public_alarm(alarm)


    @app.put("/api/alarms/{alarm_id}")
    async def api_update_alarm(alarm_id: int, payload: AlarmUpdate) -> dict[str, Any]:
        alarm = update_alarm(alarm_id, **_model_payload(payload, exclude_unset=True))
        if alarm is None:
            raise HTTPException(status_code=404, detail="alarm not found")
        return public_alarm(alarm)


    @app.delete("/api/alarms/{alarm_id}")
    async def api_delete_alarm(alarm_id: int) -> dict[str, bool]:
        if not delete_alarm(alarm_id):
            raise HTTPException(status_code=404, detail="alarm not found")
        return {"ok": True}


    @app.post("/api/alarms/{alarm_id}/toggle")
    async def api_toggle_alarm(alarm_id: int) -> dict[str, Any]:
        alarm = get_alarm(alarm_id)
        if alarm is None:
            raise HTTPException(status_code=404, detail="alarm not found")
        updated = update_alarm(alarm_id, enabled=0 if alarm.get("enabled") else 1)
        return public_alarm(updated or alarm)


    @app.get("/api/sounds")
    async def api_get_sounds() -> list[dict[str, Any]]:
        return list_sound_files()


    @app.post("/api/sounds")
    async def api_upload_sound(file: UploadFile = File(...)) -> dict[str, Any]:
        try:
            filename = _safe_sound_name(file.filename or "")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not filename.lower().endswith(AUDIO_EXTENSIONS):
            raise HTTPException(status_code=400, detail="unsupported audio extension")
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty upload")
        if filename.lower().endswith(".mp3") and not (data.startswith(b"ID3") or data[:2] == b"\xff\xfb"):
            raise HTTPException(status_code=400, detail="not an mp3 file")
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        path = _sound_path(filename)
        path.write_bytes(data)
        return _sound_info(path)


    @app.post("/api/sounds/youtube")
    async def api_download_youtube_sound(payload: YouTubeDownload) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(download_youtube_audio, payload.url, payload.filename)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.post("/api/sounds/youtube/jobs")
    async def api_create_youtube_download_job(payload: YouTubeDownload) -> dict[str, Any]:
        try:
            return create_youtube_download_job(payload.url, payload.filename)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.get("/api/sounds/youtube/jobs/{job_id}")
    async def api_get_youtube_download_job(job_id: str) -> dict[str, Any]:
        job = get_youtube_download_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="download job not found")
        return job


    @app.post("/api/sounds/{name}/trim")
    async def api_trim_sound(
        name: str,
        file: UploadFile = File(...),
        final_name: str = Form(""),
    ) -> dict[str, Any]:
        data = await file.read()
        try:
            return replace_sound(name, final_name or file.filename or "", data)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FileExistsError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.delete("/api/sounds/{name}")
    async def api_delete_sound(name: str) -> dict[str, bool]:
        try:
            deleted = delete_sound(name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": deleted}


    @app.post("/api/sounds/{name}/rename")
    async def api_rename_sound(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        new_name = str((payload or {}).get("new_name", "")).strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="new_name is required")
        try:
            return rename_sound(name, new_name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FileExistsError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.get("/api/devices")
    async def api_devices() -> dict[str, Any]:
        devices = await asyncio.to_thread(player.discover_devices)
        return {"devices": devices, "names": [device["name"] for device in devices if device.get("name")]}


    @app.get("/api/status")
    async def api_status() -> dict[str, Any]:
        return _status_payload()


    @app.post("/api/ring/test")
    async def api_test_ring(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        mode = (payload or {}).get("mode", "sound")
        sound_url, device, test_settings = _build_test_ring(str(mode))
        return await ring.start_session(-1, sound_url, device, test_settings)


    @app.post("/api/ring/stop")
    async def api_stop_ring() -> dict[str, Any]:
        # The web "stop" button is a snooze: silence + keep monitoring. For
        # wake-check alarms it re-rings if still/again in bed (no full dismiss).
        stopped = ring.snooze_session()
        return {"ok": stopped, **ring.get_status()}


    @app.get("/api/settings")
    async def api_get_settings() -> dict[str, Any]:
        return get_settings()


    @app.put("/api/settings")
    async def api_update_settings(payload: dict[str, Any]) -> dict[str, Any]:
        return update_settings(payload)

else:

    class _CompatModel:
        _defaults: dict[str, Any] = {}

        def __init__(self, **kwargs: Any):
            self._provided = set(kwargs)
            for key, default in self._defaults.items():
                setattr(self, key, kwargs.get(key, default))

        def dict(self, exclude_unset: bool = False) -> dict[str, Any]:
            keys = self._provided if exclude_unset else self._defaults
            return {key: getattr(self, key) for key in keys if key in self._defaults}

    class AlarmCreate(_CompatModel):
        _defaults = {
            "label": "Alarm", "time": "07:00", "repeat_days": [], "enabled": True,
            "sound_type": "upload", "sound_ref": "alarm_long.mp3", "volume": 1.0,
            "devices": ["Miku-Miku Echo"], "wake_check": True,
        }

    class AlarmUpdate(_CompatModel):
        _defaults = {
            "label": None, "time": None, "repeat_days": None, "enabled": None,
            "sound_type": None, "sound_ref": None, "volume": None, "devices": None,
            "wake_check": None, "last_fired_date": None,
        }

    class YouTubeDownload(_CompatModel):
        _defaults = {"url": "", "filename": None}

    async def api_status() -> dict[str, Any]:
        return _status_payload()

    async def api_get_alarms() -> list[dict[str, Any]]:
        return [public_alarm(alarm) for alarm in get_all_alarms()]

    async def api_create_alarm(payload: AlarmCreate) -> dict[str, Any]:
        return public_alarm(create_alarm(**_model_payload(payload)))

    async def api_update_alarm(alarm_id: int, payload: AlarmUpdate) -> dict[str, Any]:
        alarm = update_alarm(alarm_id, **_model_payload(payload, exclude_unset=True))
        return public_alarm(alarm or {})

    async def api_delete_alarm(alarm_id: int) -> dict[str, bool]:
        return {"ok": delete_alarm(alarm_id)}

    async def api_download_youtube_sound(payload: YouTubeDownload) -> dict[str, Any]:
        return await asyncio.to_thread(download_youtube_audio, payload.url, payload.filename)

    async def api_get_settings() -> dict[str, Any]:
        return get_settings()

    async def api_update_settings(payload: dict[str, Any]) -> dict[str, Any]:
        return update_settings(payload)

    class MinimalASGIApp:
        def __init__(self) -> None:
            self.started = False

        async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
            if scope["type"] == "lifespan":
                await self._lifespan(receive, send)
                return
            if scope["type"] != "http":
                return
            self._ensure_started()
            body = await self._read_body(receive)
            await self._route(scope, body, send)

        async def _lifespan(self, receive: Any, send: Any) -> None:
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    self._ensure_started()
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

        def _ensure_started(self) -> None:
            if self.started:
                return
            init_db()
            SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(scheduler_loop())
                loop.create_task(emfit_poller())
            except RuntimeError:
                pass
            self.started = True

        async def _read_body(self, receive: Any) -> bytes:
            chunks: list[bytes] = []
            while True:
                message = await receive()
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    return b"".join(chunks)

        async def _route(self, scope: dict[str, Any], body: bytes, send: Any) -> None:
            method = scope["method"].upper()
            path = unquote(scope["path"])
            try:
                if path == "/" and method == "GET":
                    await self._send_file(send, STATIC_DIR / "index.html")
                elif path.startswith("/static/") and method == "GET":
                    await self._send_file(send, STATIC_DIR / path.removeprefix("/static/"))
                elif path.startswith("/sounds/") and method == "GET":
                    await self._send_file(send, SOUNDS_DIR / path.removeprefix("/sounds/"))
                elif path == "/api/status" and method == "GET":
                    await self._json(send, _status_payload())
                elif path == "/api/settings" and method == "GET":
                    await self._json(send, get_settings())
                elif path == "/api/settings" and method == "PUT":
                    await self._json(send, update_settings(self._json_body(body)))
                elif path == "/api/alarms" and method == "GET":
                    await self._json(send, [public_alarm(alarm) for alarm in get_all_alarms()])
                elif path == "/api/alarms" and method == "POST":
                    await self._json(send, public_alarm(create_alarm(**self._json_body(body))), status=201)
                elif path.startswith("/api/alarms/") and method in {"PUT", "DELETE", "POST"}:
                    await self._alarm_route(send, method, path, body)
                elif path == "/api/sounds" and method == "GET":
                    await self._json(send, list_sound_files())
                elif path == "/api/sounds" and method == "POST":
                    await self._json(send, {"detail": "sound upload requires python-multipart/FastAPI"}, status=503)
                elif path == "/api/sounds/youtube/jobs" and method == "POST":
                    payload = self._json_body(body)
                    try:
                        job = create_youtube_download_job(str(payload.get("url", "")), payload.get("filename"))
                        await self._json(send, job)
                    except FileNotFoundError as exc:
                        await self._json(send, {"detail": str(exc)}, status=503)
                    except ValueError as exc:
                        await self._json(send, {"detail": str(exc)}, status=400)
                elif path.startswith("/api/sounds/youtube/jobs/") and method == "GET":
                    job_id = path.removeprefix("/api/sounds/youtube/jobs/")
                    job = get_youtube_download_job(job_id)
                    if job is None:
                        await self._json(send, {"detail": "download job not found"}, status=404)
                    else:
                        await self._json(send, job)
                elif path.startswith("/api/sounds/") and path.endswith("/trim") and method == "POST":
                    await self._json(send, {"detail": "sound trimming requires python-multipart/FastAPI"}, status=503)
                elif path == "/api/sounds/youtube" and method == "POST":
                    payload = self._json_body(body)
                    try:
                        sound = await asyncio.to_thread(
                            download_youtube_audio,
                            str(payload.get("url", "")),
                            payload.get("filename"),
                        )
                        await self._json(send, sound)
                    except FileNotFoundError as exc:
                        await self._json(send, {"detail": str(exc)}, status=503)
                    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                        await self._json(send, {"detail": str(exc)}, status=400)
                elif path.startswith("/api/sounds/") and path.endswith("/rename") and method == "POST":
                    name = path.removeprefix("/api/sounds/").removesuffix("/rename")
                    new_name = str(self._json_body(body).get("new_name", "")).strip()
                    if not new_name:
                        await self._json(send, {"detail": "new_name is required"}, status=400)
                    else:
                        await self._json(send, rename_sound(name, new_name))
                elif path.startswith("/api/sounds/") and method == "DELETE":
                    deleted = delete_sound(path.removeprefix("/api/sounds/"))
                    await self._json(send, {"ok": deleted})
                elif path == "/api/devices" and method == "GET":
                    devices = await asyncio.to_thread(player.discover_devices)
                    await self._json(send, {"devices": devices, "names": [d["name"] for d in devices if d.get("name")]})
                elif path == "/api/ring/test" and method == "POST":
                    mode = str(self._json_body(body).get("mode", "sound"))
                    sound_url, device, test_settings = _build_test_ring(mode)
                    await self._json(send, await ring.start_session(-1, sound_url, device, test_settings))
                elif path == "/api/ring/stop" and method == "POST":
                    stopped = ring.snooze_session()
                    await self._json(send, {"ok": stopped, **ring.get_status()})
                else:
                    await self._json(send, {"detail": "not found"}, status=404)
            except Exception as exc:
                await self._json(send, {"detail": str(exc)}, status=500)

        async def _alarm_route(self, send: Any, method: str, path: str, body: bytes) -> None:
            suffix = path.removeprefix("/api/alarms/")
            toggle = suffix.endswith("/toggle")
            alarm_id_text = suffix[:-7] if toggle else suffix
            alarm_id = int(alarm_id_text.strip("/"))
            alarm = get_alarm(alarm_id)
            if alarm is None:
                await self._json(send, {"detail": "alarm not found"}, status=404)
                return
            if method == "POST" and toggle:
                updated = update_alarm(alarm_id, enabled=0 if alarm.get("enabled") else 1)
                await self._json(send, public_alarm(updated or alarm))
            elif method == "PUT":
                updated = update_alarm(alarm_id, **self._json_body(body))
                await self._json(send, public_alarm(updated or alarm))
            elif method == "DELETE":
                delete_alarm(alarm_id)
                await self._json(send, {"ok": True})
            else:
                await self._json(send, {"detail": "not found"}, status=404)

        def _json_body(self, body: bytes) -> dict[str, Any]:
            if not body:
                return {}
            decoded = json.loads(body.decode("utf-8"))
            return decoded if isinstance(decoded, dict) else {}

        async def _json(self, send: Any, payload: Any, status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"content-length", str(len(data)).encode("ascii")),
                        (b"access-control-allow-origin", b"*"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": data})

        async def _send_file(self, send: Any, path: Path) -> None:
            resolved = path.resolve()
            allowed_roots = [STATIC_DIR.resolve(), SOUNDS_DIR.resolve()]
            if not any(resolved == root or root in resolved.parents for root in allowed_roots):
                await self._json(send, {"detail": "not found"}, status=404)
                return
            if not resolved.exists() or not resolved.is_file():
                await self._json(send, {"detail": "not found"}, status=404)
                return
            data = resolved.read_bytes()
            content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", content_type.encode("ascii")),
                        (b"content-length", str(len(data)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": data})


    app = MinimalASGIApp()
