from __future__ import annotations

import json
import logging
import subprocess
import time
from typing import Any

from db import get_settings


LOGGER = logging.getLogger(__name__)
_BT_TIMEOUT_SEC = 10
_BT_RECHECK_SEC = 3
_PW_DUMP_TIMEOUT_SEC = 5
_PW_STREAM_CACHE_SEC = 5


class BtPlayer:
    """Play a local or remote audio source through the default PipeWire sink."""

    def __init__(self, device_name: str, bt_mac: str):
        self.device_name = device_name
        self.bt_mac = str(bt_mac or "").strip()
        self._process: subprocess.Popen[Any] | None = None
        self._last_connected_check = 0.0
        self._connected = not bool(self.bt_mac)
        self._next_volume = 1.0
        self._stream_cache_at = 0.0
        self._stream_cache_value: bool | None = None
        self._stream_cache_valid = False

    def _bluetoothctl(self, *args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["bluetoothctl", *args],
                capture_output=True,
                text=True,
                timeout=_BT_TIMEOUT_SEC,
                check=False,
            )
        except Exception as exc:
            LOGGER.warning("bluetoothctl %s failed: %s", " ".join(args), exc)
            return None

    def ensure_connected(self) -> bool:
        if not self.bt_mac:
            return True
        now = time.monotonic()
        if now - self._last_connected_check < _BT_RECHECK_SEC:
            return self._connected
        self._last_connected_check = now

        info = self._bluetoothctl("info", self.bt_mac)
        if info is not None and "Connected: yes" in (info.stdout or ""):
            self._connected = True
            return True

        self._connected = False
        connected = self._bluetoothctl("connect", self.bt_mac)
        if connected is None or connected.returncode != 0:
            LOGGER.warning("Bluetooth speaker connection failed: %s", self.bt_mac)
            return False
        verify = self._bluetoothctl("info", self.bt_mac)
        self._connected = bool(verify is not None and "Connected: yes" in (verify.stdout or ""))
        if not self._connected:
            LOGGER.warning("Bluetooth speaker did not report connected: %s", self.bt_mac)
        return self._connected

    def reconnect(self) -> bool:
        """Cycle the configured Bluetooth connection before a new session."""
        self._last_connected_check = 0.0
        self._connected = not bool(self.bt_mac)
        self._stream_cache_at = 0.0
        self._stream_cache_value = None
        self._stream_cache_valid = False
        if not self.bt_mac:
            LOGGER.info("Bluetooth reconnect skipped: no MAC configured")
            return True

        self._bluetoothctl("disconnect", self.bt_mac)
        time.sleep(2)
        connected = self._bluetoothctl("connect", self.bt_mac)
        time.sleep(2)
        ok = connected is not None and connected.returncode == 0
        LOGGER.info("Bluetooth reconnect %s: %s", "succeeded" if ok else "failed", self.bt_mac)
        return ok
    def play(self, path: str, volume: float, loop: bool = True) -> bool:
        self.stop()
        self._stream_cache_at = 0.0
        self._stream_cache_value = None
        self._stream_cache_valid = False
        level = max(0, min(100, round(float(volume) * 100)))
        command = ["mpv", "--no-video", "--really-quiet"]
        if loop:
            command.append("--loop=inf")
        command.extend([f"--volume={level}", str(path)])
        try:
            self._process = subprocess.Popen(command)
            self._next_volume = max(0.0, min(1.0, float(volume)))
            return True
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            LOGGER.warning("mpv play failed for %s: %s", path, exc)
            self._process = None
            return False

    def is_playing(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stream_active(self) -> bool | None:
        """Return whether mpv has a node in PipeWire, or None if unknown."""
        now = time.monotonic()
        if self._stream_cache_valid and now - self._stream_cache_at < _PW_STREAM_CACHE_SEC:
            return self._stream_cache_value

        process = self._process
        pid = getattr(process, "pid", None) if process is not None else None
        try:
            result = subprocess.run(
                ["pw-dump"],
                capture_output=True,
                text=True,
                timeout=_PW_DUMP_TIMEOUT_SEC,
                check=False,
            )
            if result.returncode != 0:
                raise subprocess.SubprocessError(f"pw-dump exited with {result.returncode}")
            objects = json.loads(result.stdout or "")
            if not isinstance(objects, list):
                raise ValueError("pw-dump output was not a list")
        except (OSError, subprocess.SubprocessError, TimeoutError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            LOGGER.warning("PipeWire stream check failed: %s", exc)
            value = None
        else:
            value = False
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                info = obj.get("info")
                props = info.get("props") if isinstance(info, dict) else None
                if not isinstance(props, dict):
                    continue
                process_id = props.get("application.process.id")
                same_pid = False
                if pid is not None and process_id is not None:
                    try:
                        same_pid = int(process_id) == int(pid)
                    except (TypeError, ValueError):
                        same_pid = str(process_id) == str(pid)
                application_name = str(props.get("application.name") or "").lower()
                if same_pid or "mpv" in application_name:
                    value = True
                    break

        self._stream_cache_at = now
        self._stream_cache_value = value
        self._stream_cache_valid = True
        return value
    def stop(self) -> bool:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return False
        try:
            process.terminate()
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.SubprocessError) as exc:
                LOGGER.warning("mpv kill failed: %s", exc)
        except (OSError, subprocess.SubprocessError) as exc:
            LOGGER.warning("mpv stop failed: %s", exc)
        return True

    def set_volume(self, volume: float) -> bool:
        self._next_volume = max(0.0, min(1.0, float(volume)))
        return True


def discover_devices() -> list[dict[str, Any]]:
    settings = get_settings()
    bt_mac = str(settings.get("bt_mac") or "").strip()
    connected = False
    if bt_mac:
        try:
            result = subprocess.run(
                ["bluetoothctl", "info", bt_mac],
                capture_output=True,
                text=True,
                timeout=_BT_TIMEOUT_SEC,
                check=False,
            )
            connected = "Connected: yes" in (result.stdout or "")
        except (OSError, subprocess.SubprocessError) as exc:
            LOGGER.warning("Bluetooth device discovery failed: %s", exc)
    return [{"name": "Miku-Miku Echo", "bt_mac": bt_mac, "connected": connected}]