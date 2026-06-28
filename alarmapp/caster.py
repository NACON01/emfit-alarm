from __future__ import annotations

import logging
import re
import threading
from typing import Any


try:
    import pychromecast
    from pychromecast.discovery import get_device_info
except ImportError:  # pragma: no cover - pychromecast is expected on the target host.
    pychromecast = None
    get_device_info = None


LOGGER = logging.getLogger(__name__)

# mDNS/zeroconf discovery is unreliable inside the systemd unit (it silently
# returns "device not found"), so we connect to known Cast devices by IP. The
# device's own HTTP endpoint (get_device_info) gives us the uuid/model we need.
DEVICE_HOSTS: dict[str, str] = {
    "ぬま": "192.168.0.108",
    "リビングルーム": "192.168.0.107",
    "SONY": "192.168.0.182",
}

CAST_PORT = 8009
CONNECT_TIMEOUT = 8
_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def _resolve_host(device_name: str) -> str | None:
    if not device_name:
        return None
    if device_name in DEVICE_HOSTS:
        return DEVICE_HOSTS[device_name]
    if _IP_RE.match(device_name.strip()):
        return device_name.strip()
    return None


class CastSession:
    """A persistent connection to one Cast device, reused across ring ticks."""

    def __init__(self, device_name: str):
        self.device_name = device_name
        self.host = _resolve_host(device_name)
        self.cast: Any | None = None
        self._lock = threading.Lock()

    # -- connection -------------------------------------------------------
    def _is_alive(self, cast: Any) -> bool:
        try:
            client = getattr(cast, "socket_client", None)
            if client is None:
                return False
            connecting = getattr(client, "is_connected", None)
            return bool(connecting)
        except Exception:
            return False

    def discover(self) -> Any | None:
        """Return a connected Chromecast, reconnecting if needed."""
        if pychromecast is None or get_device_info is None:
            LOGGER.warning("pychromecast is not installed")
            return None
        with self._lock:
            if self.cast is not None and self._is_alive(self.cast):
                return self.cast
            self._teardown_locked()
            host = self.host or _resolve_host(self.device_name)
            if host is None:
                LOGGER.warning("no known IP for cast device %s", self.device_name)
                return self._discover_mdns_locked()
            try:
                info = get_device_info(host, timeout=CONNECT_TIMEOUT)
                if info is None:
                    LOGGER.warning("cast device %s (%s) did not respond", self.device_name, host)
                    return None
                host_tuple = (host, CAST_PORT, info.uuid, info.model_name, info.friendly_name)
                cast = pychromecast.get_chromecast_from_host(host_tuple, tries=2, timeout=CONNECT_TIMEOUT)
                cast.wait(timeout=CONNECT_TIMEOUT)
                self.cast = cast
                LOGGER.info("connected to cast device %s at %s", self.device_name, host)
                return cast
            except Exception as exc:
                LOGGER.warning("cast connect failed for %s (%s): %s", self.device_name, host, exc)
                self._teardown_locked()
                return None

    def _discover_mdns_locked(self) -> Any | None:
        """Best-effort mDNS fallback for devices without a known IP."""
        try:
            result = pychromecast.get_listed_chromecasts(friendly_names=[self.device_name], timeout=CONNECT_TIMEOUT)
            casts, _browser = result if isinstance(result, tuple) else (result, None)
            if not casts:
                LOGGER.warning("cast device not found via mDNS: %s", self.device_name)
                return None
            cast = casts[0]
            cast.wait(timeout=CONNECT_TIMEOUT)
            self.cast = cast
            return cast
        except Exception as exc:
            LOGGER.warning("mDNS discovery failed for %s: %s", self.device_name, exc)
            return None

    def _teardown_locked(self) -> None:
        cast = self.cast
        self.cast = None
        if cast is None:
            return
        try:
            cast.disconnect(blocking=False)
        except Exception:
            pass

    def disconnect(self) -> None:
        with self._lock:
            self._teardown_locked()

    # -- media controls ---------------------------------------------------
    def play(self, url: str, mime: str = "audio/mpeg") -> bool:
        cast = self.discover()
        if cast is None:
            return False
        try:
            cast.media_controller.play_media(url, mime)
            return True
        except Exception as exc:
            LOGGER.warning("cast play failed for %s: %s", self.device_name, exc)
            self.disconnect()
            return False

    def stop(self) -> bool:
        cast = self.cast
        if cast is None or not self._is_alive(cast):
            return False
        try:
            cast.media_controller.stop()
            return True
        except Exception as exc:
            LOGGER.warning("cast stop failed for %s: %s", self.device_name, exc)
            return False

    def set_volume(self, level: float) -> bool:
        cast = self.discover()
        if cast is None:
            return False
        try:
            cast.set_volume(max(0.0, min(1.0, float(level))))
            return True
        except Exception as exc:
            LOGGER.warning("cast set_volume failed for %s: %s", self.device_name, exc)
            self.disconnect()
            return False

    def get_volume(self) -> float:
        cast = self.cast
        if cast is None:
            return -1.0
        try:
            status = getattr(cast, "status", None)
            level = getattr(status, "volume_level", None)
            return float(level) if level is not None else -1.0
        except Exception:
            return -1.0

    def player_state(self) -> str:
        cast = self.cast
        if cast is None:
            return ""
        try:
            status = getattr(cast.media_controller, "status", None)
            return str(getattr(status, "player_state", "") or "")
        except Exception:
            return ""

    def idle_reason(self) -> str:
        cast = self.cast
        if cast is None:
            return ""
        try:
            status = getattr(cast.media_controller, "status", None)
            return str(getattr(status, "idle_reason", "") or "")
        except Exception:
            return ""


def discover_devices(timeout: int = 3) -> list[dict[str, str]]:
    """Return known Cast devices, probed by IP (mDNS-free, fast, systemd-safe)."""
    if get_device_info is None:
        return [{"name": name, "host": host, "model_name": ""} for name, host in DEVICE_HOSTS.items()]
    devices: list[dict[str, str]] = []
    for name, host in DEVICE_HOSTS.items():
        model = ""
        try:
            info = get_device_info(host, timeout=timeout)
            if info is None:
                continue
            model = info.model_name or ""
        except Exception:
            continue
        devices.append({"name": name, "host": host, "model_name": model})
    return devices
