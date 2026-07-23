from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

import emfit
import ring
from db import (
    clear_anti_doze_runtime,
    get_all_alarms,
    get_anti_doze_runtime,
    get_settings,
    set_anti_doze_runtime,
    update_alarm,
)
from scheduler import (
    DEFAULT_DEVICE,
    _devices_for_alarm,
    _json_list,
    _settings_for_alarm,
    _sound_urls_for_alarm,
)


LOGGER = logging.getLogger(__name__)
COUNTING = "COUNTING"
FIRED = "FIRED"
COOLDOWN = "COOLDOWN"


def _parse_time(value: Any) -> time | None:
    try:
        hour, minute = [int(part) for part in str(value or "").split(":", 1)]
        return time(hour=hour, minute=minute)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _window_anchor(alarm: dict[str, Any], now: datetime) -> date | None:
    start = _parse_time(alarm.get("monitor_start"))
    end = _parse_time(alarm.get("time"))
    if start is None or end is None or start == end:
        return None

    current = now.time().replace(second=0, microsecond=0)
    if start < end:
        anchor = now.date() if start <= current < end else None
    elif current >= start:
        anchor = now.date()
    elif current < end:
        anchor = now.date() - timedelta(days=1)
    else:
        anchor = None

    if anchor is None:
        return None
    days = _json_list(alarm.get("repeat_days"), [])
    if days and anchor.weekday() not in [int(day) for day in days]:
        return None
    return anchor


def is_monitoring_now(alarm: dict[str, Any], now: datetime | None = None) -> bool:
    return _window_anchor(alarm, now or datetime.now()) is not None


def _anti_doze_alarms() -> list[dict[str, Any]]:
    return [
        alarm
        for alarm in get_all_alarms()
        if (alarm.get("alarm_kind") or "wake") == "anti_doze"
    ]


def _same_ring_session(alarm_id: int) -> bool:
    session = ring.current_session
    return bool(
        session is not None
        and session.ended_reason is None
        and session.alarm_id == alarm_id
        and session.session_kind == "anti_doze"
    )


def _delay_sec(alarm: dict[str, Any]) -> int:
    value = alarm.get("anti_doze_delay_min")
    return max(1, min(720, int(20 if value is None else value))) * 60


def _enter_cooldown_or_clear(alarm: dict[str, Any], now: datetime, active: bool) -> None:
    alarm_id = int(alarm["id"])
    block_min = max(0, min(720, int(alarm.get("reentry_block_min") or 0)))
    if active and block_min > 0:
        set_anti_doze_runtime(
            alarm_id,
            phase=COOLDOWN,
            in_bed_since=None,
            cooldown_until=(now + timedelta(minutes=block_min)).isoformat(timespec="seconds"),
        )
    else:
        clear_anti_doze_runtime(alarm_id)


async def _start_ring(alarm: dict[str, Any], settings: dict[str, Any], reason: str) -> bool:
    if ring.current_session is not None:
        return False
    sound_urls = _sound_urls_for_alarm(alarm, settings)
    if not sound_urls:
        LOGGER.warning("anti-doze alarm %s skipped because it has no sound", alarm["id"])
        return False
    devices = _devices_for_alarm(alarm, settings)
    device_name = devices[0] if devices else DEFAULT_DEVICE
    session_settings = _settings_for_alarm(alarm, settings)
    session_settings["wake_check"] = True
    status = await ring.start_session(
        int(alarm["id"]),
        sound_urls,
        device_name,
        session_settings,
    )
    started = (
        status.get("alarm_id") == int(alarm["id"])
        and status.get("session_kind") == "anti_doze"
    )
    if started:
        LOGGER.info("anti-doze alarm fired alarm=%s reason=%s", alarm["id"], reason)
        if not _json_list(alarm.get("repeat_days"), []):
            update_alarm(int(alarm["id"]), enabled=0)
        set_anti_doze_runtime(
            int(alarm["id"]),
            phase=FIRED,
            in_bed_since=None,
            cooldown_until=None,
        )
    return started


async def _tick_alarm(
    alarm: dict[str, Any],
    settings: dict[str, Any],
    in_bed: bool | None,
    now: datetime,
) -> None:
    alarm_id = int(alarm["id"])
    state = get_anti_doze_runtime(alarm_id)
    phase = str(state.get("phase")) if state else None
    active = is_monitoring_now(alarm, now)
    enabled = bool(alarm.get("enabled"))

    if phase == FIRED:
        if _same_ring_session(alarm_id) or ring.current_session is not None:
            return
        if in_bed is False:
            _enter_cooldown_or_clear(alarm, now, active)
        return

    if phase == COOLDOWN:
        cooldown_until = _parse_datetime(state.get("cooldown_until") if state else None)
        if not active or cooldown_until is None or now >= cooldown_until:
            clear_anti_doze_runtime(alarm_id)
            if not enabled or not active or in_bed is not True:
                return
            set_anti_doze_runtime(
                alarm_id,
                phase=COUNTING,
                in_bed_since=now.isoformat(timespec="seconds"),
                cooldown_until=None,
            )
            return
        if in_bed is True:
            await _start_ring(alarm, settings, "reentry_during_cooldown")
        return

    if not enabled:
        if state is not None:
            clear_anti_doze_runtime(alarm_id)
        return

    if phase == COUNTING:
        if in_bed is False:
            _enter_cooldown_or_clear(alarm, now, active)
            return
        if in_bed is not True:
            clear_anti_doze_runtime(alarm_id)
            return
        in_bed_since = _parse_datetime(state.get("in_bed_since") if state else None)
        if in_bed_since is None:
            set_anti_doze_runtime(
                alarm_id,
                phase=COUNTING,
                in_bed_since=now.isoformat(timespec="seconds"),
                cooldown_until=None,
            )
            return
        delay_sec = _delay_sec(alarm)
        if (now - in_bed_since).total_seconds() >= delay_sec:
            await _start_ring(alarm, settings, "continuous_in_bed")
        return

    if state is not None:
        clear_anti_doze_runtime(alarm_id)
    if active and in_bed is True:
        set_anti_doze_runtime(
            alarm_id,
            phase=COUNTING,
            in_bed_since=now.isoformat(timespec="seconds"),
            cooldown_until=None,
        )


async def tick(now: datetime | None = None, in_bed: bool | None = None) -> None:
    current = now or datetime.now()
    sensor_value = emfit.cached_in_bed() if in_bed is None else in_bed
    settings = get_settings()
    for alarm in _anti_doze_alarms():
        await _tick_alarm(alarm, settings, sensor_value, current)


async def anti_doze_loop() -> None:
    while True:
        try:
            await tick()
        except Exception:
            LOGGER.exception("anti-doze monitor tick failed")
        settings = get_settings()
        await asyncio.sleep(max(1.0, float(settings.get("poll_sec", 5))))


def get_status(now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now()
    candidates: list[dict[str, Any]] = []

    for alarm in _anti_doze_alarms():
        alarm_id = int(alarm["id"])
        state = get_anti_doze_runtime(alarm_id)
        if not alarm.get("enabled") and state is None:
            continue
        phase = str(state.get("phase")) if state else "IDLE"
        in_bed_since = _parse_datetime(state.get("in_bed_since") if state else None)
        cooldown_until = _parse_datetime(state.get("cooldown_until") if state else None)
        remaining_sec = None
        cooldown_remaining_sec = None
        if phase == COUNTING and in_bed_since is not None:
            delay_sec = _delay_sec(alarm)
            remaining_sec = max(0, int(delay_sec - (current - in_bed_since).total_seconds()))
        if phase == COOLDOWN and cooldown_until is not None:
            cooldown_remaining_sec = max(0, int((cooldown_until - current).total_seconds()))
        candidates.append(
            {
                "state": phase,
                "alarm_id": alarm_id,
                "label": alarm.get("label"),
                "enabled": bool(alarm.get("enabled")),
                "monitor_start": alarm.get("monitor_start"),
                "monitor_end": alarm.get("time"),
                "delay_min": _delay_sec(alarm) // 60,
                "monitoring_now": is_monitoring_now(alarm, current),
                "remaining_sec": remaining_sec,
                "cooldown_remaining_sec": cooldown_remaining_sec,
                "reentry_block_min": int(alarm.get("reentry_block_min") or 0),
            }
        )

    priority = {FIRED: 0, COOLDOWN: 1, COUNTING: 2, "IDLE": 3}
    candidates.sort(
        key=lambda item: (
            priority.get(str(item["state"]), 9),
            item["remaining_sec"] if item["remaining_sec"] is not None else 10**9,
            item["alarm_id"],
        )
    )
    if not candidates:
        return {
            "state": "IDLE",
            "alarm_id": None,
            "monitoring_now": False,
            "remaining_sec": None,
            "cooldown_remaining_sec": None,
        }
    return candidates[0]
