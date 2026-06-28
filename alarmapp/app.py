from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import caster
import emfit
import ring
from db import create_alarm, delete_alarm, get_all_alarms, get_alarm, get_settings, init_db, update_alarm, update_settings
from scheduler import HOST_AUDIO_BASE, get_next_alarm, scheduler_loop


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
SOUNDS_DIR = ROOT_DIR / "sounds"
UNSAFE_SOUND_CHARS_RE = re.compile(r"[\x00-\x1f\x7f/\\]+")


try:
    from fastapi import FastAPI, File, HTTPException, UploadFile
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
        "devices": _json_list(alarm.get("devices"), ["ぬま"]),
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


def sound_file_url(name: str) -> str:
    return f"{HOST_AUDIO_BASE}/{quote(name)}"


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
    # Repoint alarms that used the old upload by name.
    for alarm in get_all_alarms():
        if alarm.get("sound_type") == "upload" and alarm.get("sound_ref") == src.name:
            update_alarm(int(alarm["id"]), sound_ref=dst.name)
    return {"name": dst.name, "size": dst.stat().st_size, "url": sound_file_url(dst.name)}


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
    sound_url = sound_file_url(sound_name)
    devices = settings.get("default_devices") or ["ぬま"]
    if not isinstance(devices, list):
        devices = _json_list(devices, ["ぬま"])
    device = str(devices[0]) if devices else "ぬま"
    if mode == "real":
        test_settings = {
            **settings,
            # keep emfit_enabled/volume_ack_enabled/thresholds as configured,
            "wake_check": True,
            "max_session_sec": REAL_TEST_MAX_SECONDS,
        }
    else:
        test_settings = {
            **settings,
            "emfit_enabled": False,
            "wake_check": False,
            "volume_ack_enabled": False,
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
        sound_ref: str = "alarm_long.mp3"
        volume: float = 1.0
        devices: list[str] = Field(default_factory=lambda: ["ぬま"])
        wake_check: bool = True


    class AlarmUpdate(BaseModel):
        label: str | None = None
        time: str | None = None
        repeat_days: list[int] | None = None
        enabled: bool | None = None
        sound_type: str | None = None
        sound_ref: str | None = None
        volume: float | None = None
        devices: list[str] | None = None
        wake_check: bool | None = None
        last_fired_date: str | None = None


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
        if not filename.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
            raise HTTPException(status_code=400, detail="unsupported audio extension")
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty upload")
        if filename.lower().endswith(".mp3") and not (data.startswith(b"ID3") or data[:2] == b"\xff\xfb"):
            raise HTTPException(status_code=400, detail="not an mp3 file")
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        path = _sound_path(filename)
        path.write_bytes(data)
        return {"name": path.name, "size": path.stat().st_size, "url": sound_file_url(path.name)}


    @app.delete("/api/sounds/{name}")
    async def api_delete_sound(name: str) -> dict[str, bool]:
        try:
            path = _sound_path(name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if path.exists():
            path.unlink()
        return {"ok": True}


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
        devices = await asyncio.to_thread(caster.discover_devices, 5)
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
                elif path.startswith("/api/sounds/") and path.endswith("/rename") and method == "POST":
                    name = path.removeprefix("/api/sounds/").removesuffix("/rename")
                    new_name = str(self._json_body(body).get("new_name", "")).strip()
                    if not new_name:
                        await self._json(send, {"detail": "new_name is required"}, status=400)
                    else:
                        await self._json(send, rename_sound(name, new_name))
                elif path.startswith("/api/sounds/") and method == "DELETE":
                    target = _sound_path(path.removeprefix("/api/sounds/"))
                    if target.exists():
                        target.unlink()
                    await self._json(send, {"ok": True})
                elif path == "/api/devices" and method == "GET":
                    devices = await asyncio.to_thread(caster.discover_devices, 5)
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
