from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import anti_doze
import ring
from db import get_all_alarms, get_anti_doze_runtime, get_settings
from paths import bed_entry_announcement_path
from scheduler import (
    DEFAULT_DEVICE,
    _devices_for_alarm,
    _json_list,
    _settings_for_alarm,
    get_next_alarm,
)


LOGGER = logging.getLogger(__name__)
OUT_CONFIRM_SAMPLES = 2
WAKE_ALARM_GUARD_SEC = 60

_last_valid_in_bed: bool | None = None
_last_valid_at: datetime | None = None
_continuous_out_samples = 0
_armed = False
_last_detected_at: datetime | None = None
_last_announced_at: datetime | None = None
_last_result = "initializing"


def reset_state() -> None:
    global _last_valid_in_bed, _last_valid_at, _continuous_out_samples, _armed
    global _last_detected_at, _last_announced_at, _last_result
    _last_valid_in_bed = None
    _last_valid_at = None
    _continuous_out_samples = 0
    _armed = False
    _last_detected_at = None
    _last_announced_at = None
    _last_result = "initializing"


def _is_due_now(alarm: dict[str, Any], now: datetime) -> bool:
    if str(alarm.get("time") or "") != now.strftime("%H:%M"):
        return False
    days = _json_list(alarm.get("repeat_days"), [])
    if days and now.weekday() not in [int(day) for day in days]:
        return False
    return alarm.get("last_fired_date") != now.strftime("%Y-%m-%d")


def _select_alarm(now: datetime) -> tuple[dict[str, Any] | None, str | None]:
    alarms = get_all_alarms()
    anti_alarms = [
        alarm
        for alarm in alarms
        if alarm.get("enabled")
        and (alarm.get("alarm_kind") or "wake") == "anti_doze"
        and anti_doze.is_monitoring_now(alarm, now)
    ]
    for alarm in anti_alarms:
        runtime = get_anti_doze_runtime(int(alarm["id"]))
        if runtime and runtime.get("phase") == anti_doze.COOLDOWN:
            return None, "anti_doze_cooldown"
    if anti_alarms:
        anti_alarms.sort(key=lambda alarm: (str(alarm.get("time") or ""), int(alarm["id"])))
        return anti_alarms[0], None

    wake_alarms = [
        alarm
        for alarm in alarms
        if alarm.get("enabled") and (alarm.get("alarm_kind") or "wake") == "wake"
    ]
    if not wake_alarms:
        return None, "no_eligible_alarm"
    if any(_is_due_now(alarm, now) for alarm in wake_alarms):
        return None, "wake_alarm_due"

    next_alarm = get_next_alarm(now)
    if next_alarm is not None:
        if int(next_alarm.get("seconds_until") or 0) <= WAKE_ALARM_GUARD_SEC:
            return None, "wake_alarm_imminent"
        next_id = int(next_alarm["id"])
        for alarm in wake_alarms:
            if int(alarm["id"]) == next_id:
                return alarm, None
    wake_alarms.sort(key=lambda alarm: (str(alarm.get("time") or ""), int(alarm["id"])))
    return wake_alarms[0], None


async def _announce(now: datetime) -> bool:
    global _last_announced_at, _last_result
    alarm, skip_reason = _select_alarm(now)
    if alarm is None:
        _last_result = str(skip_reason or "no_eligible_alarm")
        LOGGER.info("bed-entry announcement skipped reason=%s", _last_result)
        return False

    announcement_path = bed_entry_announcement_path()
    if not Path(announcement_path).is_file():
        _last_result = "sound_missing"
        LOGGER.warning("bed-entry announcement sound is missing: %s", announcement_path)
        return False

    settings = get_settings()
    devices = _devices_for_alarm(alarm, settings)
    device_name = devices[0] if devices else DEFAULT_DEVICE
    session_settings = _settings_for_alarm(alarm, settings)
    status = await ring.start_announcement(
        int(alarm["id"]),
        announcement_path,
        device_name,
        session_settings,
    )
    started = (
        status.get("alarm_id") == int(alarm["id"])
        and status.get("session_kind") == "bed_entry_announcement"
    )
    if not started:
        _last_result = "ring_busy"
        LOGGER.info("bed-entry announcement skipped because ring is busy")
        return False

    _last_announced_at = now
    _last_result = "announced"
    LOGGER.info("bed-entry announcement started alarm=%s device=%s", alarm["id"], device_name)
    return True


async def observe(in_bed: bool | None, now: datetime | None = None) -> bool:
    global _last_valid_in_bed, _last_valid_at, _continuous_out_samples, _armed
    global _last_detected_at, _last_result
    current = now or datetime.now()
    if in_bed is None:
        _last_result = "sensor_unknown"
        return False

    if _last_valid_in_bed is None:
        _last_valid_in_bed = in_bed
        _last_valid_at = current
        _continuous_out_samples = 1 if in_bed is False else 0
        _last_result = "baseline_out" if in_bed is False else "baseline_in_bed"
        return False

    previous = _last_valid_in_bed
    previous_at = _last_valid_at
    _last_valid_in_bed = in_bed
    _last_valid_at = current

    if in_bed is False:
        _continuous_out_samples = _continuous_out_samples + 1 if previous is False else 1
        if _continuous_out_samples >= OUT_CONFIRM_SAMPLES:
            _armed = True
            _last_result = "armed"
        else:
            _last_result = "confirming_out"
        return False

    gap_sec = (current - previous_at).total_seconds() if previous_at is not None else 0.0
    max_unknown_sec = max(1.0, float(get_settings().get("none_continue_sec", 60)))
    should_announce = _armed and previous is False and gap_sec <= max_unknown_sec
    _continuous_out_samples = 0
    _armed = False
    if not should_announce:
        _last_result = "in_bed_without_armed_transition"
        return False

    _last_detected_at = current
    _last_result = "detected"
    return await _announce(current)


def get_status() -> dict[str, Any]:
    return {
        "armed": _armed,
        "last_sensor_value": _last_valid_in_bed,
        "last_detected_at": _last_detected_at.isoformat(timespec="seconds") if _last_detected_at else None,
        "last_announced_at": _last_announced_at.isoformat(timespec="seconds") if _last_announced_at else None,
        "last_result": _last_result,
    }
