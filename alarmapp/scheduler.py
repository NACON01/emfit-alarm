from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import ring
from db import get_all_alarms, get_settings, update_alarm


LOGGER = logging.getLogger(__name__)
HOST_AUDIO_BASE = "http://192.168.0.45:8123/sounds"


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


def _sound_url_for_alarm(alarm: dict[str, Any], settings: dict[str, Any]) -> str:
    urls = _sound_urls_for_alarm(alarm, settings)
    return random.choice(urls) if urls else ""


def _sound_urls_for_alarm(alarm: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    sound_ref = alarm.get("sound_ref") or ""
    if alarm.get("sound_type") == "random":
        refs = [str(item) for item in _json_list(sound_ref, []) if str(item)]
        urls = [f"{HOST_AUDIO_BASE}/{quote(ref)}" for ref in refs]
        if urls:
            return urls
        fallback = str(settings.get("fallback_url") or "")
        return [fallback] if fallback else []
    if alarm.get("sound_type") == "upload" and sound_ref:
        return [f"{HOST_AUDIO_BASE}/{quote(str(sound_ref))}"]
    if sound_ref:
        return [str(sound_ref)]
    fallback = str(settings.get("fallback_url") or "")
    return [fallback] if fallback else []


def _devices_for_alarm(alarm: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    devices = _json_list(alarm.get("devices"), [])
    default_devices = settings.get("default_devices", ["ぬま"])
    if not isinstance(default_devices, list):
        default_devices = _json_list(default_devices, ["ぬま"])
    return [str(device) for device in (devices or default_devices or ["ぬま"])]


def _settings_for_alarm(alarm: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    session_settings = settings.copy()
    if alarm.get("volume") is not None:
        session_settings["ring_volume"] = float(alarm["volume"])
    session_settings["wake_check"] = bool(alarm.get("wake_check", 1))
    return session_settings


async def scheduler_loop() -> None:
    while True:
        await asyncio.sleep(5)
        if ring.current_session is not None:
            continue

        alarms = get_all_alarms()
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today_weekday = now.weekday()
        today_str = now.strftime("%Y-%m-%d")

        for alarm in alarms:
            if not alarm.get("enabled"):
                continue
            try:
                hour, minute = [int(part) for part in str(alarm.get("time") or "").split(":", 1)]
            except (ValueError, TypeError):
                continue
            alarm_minute = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days = _json_list(alarm.get("repeat_days"), [])
            if alarm.get("last_fired_date") == today_str and (alarm_minute > now or not days):
                update_alarm(int(alarm["id"]), last_fired_date=None)
                alarm["last_fired_date"] = None
            if alarm.get("time") != current_time:
                continue
            if alarm.get("last_fired_date") == today_str:
                continue

            if days and today_weekday not in [int(day) for day in days]:
                continue

            settings = get_settings()
            sound_urls = _sound_urls_for_alarm(alarm, settings)
            if not sound_urls:
                LOGGER.warning("alarm %s skipped because it has no sound URL", alarm["id"])
                continue
            devices = _devices_for_alarm(alarm, settings)
            device_name = devices[0] if devices else "ぬま"
            await ring.start_session(
                int(alarm["id"]),
                sound_urls,
                device_name,
                _settings_for_alarm(alarm, settings),
            )
            update_alarm(int(alarm["id"]), last_fired_date=today_str)
            if not days:
                update_alarm(int(alarm["id"]), enabled=0)
            break


def get_next_alarm() -> dict[str, Any] | None:
    alarms = [alarm for alarm in get_all_alarms() if alarm.get("enabled")]
    if not alarms:
        return None

    now = datetime.now()
    best: tuple[datetime, dict[str, Any]] | None = None
    for alarm in alarms:
        alarm_time = str(alarm.get("time") or "")
        try:
            hour, minute = [int(part) for part in alarm_time.split(":", 1)]
        except (ValueError, TypeError):
            continue
        days = _json_list(alarm.get("repeat_days"), [])
        for offset in range(0, 8):
            day = now.date() + timedelta(days=offset)
            if days and day.weekday() not in [int(item) for item in days]:
                continue
            candidate = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
            if candidate <= now:
                continue
            if alarm.get("last_fired_date") == day.strftime("%Y-%m-%d"):
                update_alarm(int(alarm["id"]), last_fired_date=None)
                alarm["last_fired_date"] = None
            if best is None or candidate < best[0]:
                best = (candidate, alarm)
            break

    if best is None:
        return None
    candidate, alarm = best
    return {
        "id": alarm["id"],
        "label": alarm.get("label"),
        "time": alarm.get("time"),
        "seconds_until": int((candidate - now).total_seconds()),
    }
