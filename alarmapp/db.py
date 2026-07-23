from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "alarm.db"

DEFAULT_SETTINGS: dict[str, Any] = {
    "emfit_enabled": True,
    "awake_confirm_sec": 180,
    "grace_sec": 120,
    "poll_sec": 5,
    "ring_volume": 1.0,
    "none_continue_sec": 60,
    "initial_ring_sec": 90,
    "max_session_sec": 1800,
    "default_devices": ["Miku-Miku Echo"],
    "bt_mac": "",
    "bt_stack_restart": True,
    "fallback_url": "",
}

ALARM_FIELDS = {
    "alarm_kind",
    "label",
    "time",
    "monitor_start",
    "anti_doze_delay_min",
    "reentry_block_min",
    "repeat_days",
    "enabled",
    "sound_type",
    "sound_ref",
    "volume",
    "devices",
    "wake_check",
    "last_fired_date",
}

TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _connect() -> sqlite3.Connection:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _encode_setting(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _decode_setting(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _json_text(value: Any, default: Any) -> str:
    if value is None:
        value = default
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _sound_ref_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _validate_alarm_values(values: dict[str, Any]) -> None:
    if (values.get("alarm_kind") or "wake") != "anti_doze":
        return
    monitor_start = str(values.get("monitor_start") or "")
    monitor_end = str(values.get("time") or "")
    if not TIME_RE.fullmatch(monitor_start) or not TIME_RE.fullmatch(monitor_end):
        raise ValueError("anti-doze monitoring times must use HH:MM")
    if monitor_start == monitor_end:
        raise ValueError("anti-doze monitoring start and end must differ")


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY,
                alarm_kind TEXT NOT NULL DEFAULT 'wake',
                label TEXT,
                time TEXT,
                monitor_start TEXT,
                anti_doze_delay_min INTEGER NOT NULL DEFAULT 20,
                reentry_block_min INTEGER NOT NULL DEFAULT 0,
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
        _ensure_column(conn, "alarms", "alarm_kind", "TEXT NOT NULL DEFAULT 'wake'")
        _ensure_column(conn, "alarms", "monitor_start", "TEXT")
        _ensure_column(conn, "alarms", "anti_doze_delay_min", "INTEGER NOT NULL DEFAULT 20")
        _ensure_column(conn, "alarms", "reentry_block_min", "INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS anti_doze_runtime (
                alarm_id INTEGER PRIMARY KEY,
                phase TEXT NOT NULL,
                in_bed_since TEXT,
                cooldown_until TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            [(key, _encode_setting(value)) for key, value in DEFAULT_SETTINGS.items()],
        )
        conn.commit()


def get_all_alarms() -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM alarms ORDER BY time, id").fetchall()
    return [dict(row) for row in rows]


def get_alarm(alarm_id: int) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM alarms WHERE id = ?", (alarm_id,)).fetchone()
    return _row_to_dict(row)


def create_alarm(**kwargs: Any) -> dict[str, Any]:
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    values = {
        "alarm_kind": kwargs.get("alarm_kind") if kwargs.get("alarm_kind") in {"wake", "anti_doze"} else "wake",
        "label": kwargs.get("label") or "Alarm",
        "time": kwargs.get("time") or "07:00",
        "monitor_start": kwargs.get("monitor_start"),
        "anti_doze_delay_min": max(
            1,
            min(
                720,
                int(20 if kwargs.get("anti_doze_delay_min") is None else kwargs["anti_doze_delay_min"]),
            ),
        ),
        "reentry_block_min": max(0, min(720, int(kwargs.get("reentry_block_min") or 0))),
        "repeat_days": _json_text(kwargs.get("repeat_days"), []),
        "enabled": int(bool(kwargs.get("enabled", True))),
        "sound_type": kwargs.get("sound_type") or "upload",
        "sound_ref": _sound_ref_text(kwargs.get("sound_ref") or "alarm_long.mp3"),
        "volume": float(kwargs.get("volume", 1.0)),
        "devices": _json_text(kwargs.get("devices"), DEFAULT_SETTINGS["default_devices"]),
        "wake_check": int(bool(kwargs.get("wake_check", True))),
        "last_fired_date": kwargs.get("last_fired_date"),
        "created_at": now,
    }
    _validate_alarm_values(values)
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO alarms (
                alarm_kind, label, time, monitor_start, anti_doze_delay_min, reentry_block_min,
                repeat_days, enabled, sound_type, sound_ref,
                volume, devices, wake_check, last_fired_date, created_at
            )
            VALUES (
                :alarm_kind, :label, :time, :monitor_start, :anti_doze_delay_min, :reentry_block_min,
                :repeat_days, :enabled, :sound_type, :sound_ref,
                :volume, :devices, :wake_check, :last_fired_date, :created_at
            )
            """,
            values,
        )
        conn.commit()
        alarm_id = int(cur.lastrowid)
    alarm = get_alarm(alarm_id)
    if alarm is None:
        raise RuntimeError("created alarm could not be loaded")
    return alarm


def update_alarm(alarm_id: int, **kwargs: Any) -> dict[str, Any] | None:
    init_db()
    current = get_alarm(alarm_id)
    if current is None:
        return None
    _validate_alarm_values({**current, **kwargs})
    updates: dict[str, Any] = {}
    should_clear_fired_date = (
        "last_fired_date" not in kwargs
        and (
            "time" in kwargs
            or "repeat_days" in kwargs
            or kwargs.get("enabled") is True
        )
    )
    for key, value in kwargs.items():
        if key not in ALARM_FIELDS:
            continue
        if key == "alarm_kind":
            value = value if value in {"wake", "anti_doze"} else "wake"
        elif key in {"repeat_days", "devices"}:
            value = _json_text(value, [])
        elif key == "sound_ref":
            value = _sound_ref_text(value)
        elif key in {"enabled", "wake_check"} and value is not None:
            value = int(bool(value))
        elif key == "volume" and value is not None:
            value = float(value)
        elif key == "anti_doze_delay_min" and value is not None:
            value = max(1, min(720, int(value)))
        elif key == "reentry_block_min" and value is not None:
            value = max(0, min(720, int(value)))
        updates[key] = value

    if should_clear_fired_date:
        updates["last_fired_date"] = None

    if not updates:
        return get_alarm(alarm_id)

    assignments = ", ".join(f"{key} = :{key}" for key in updates)
    updates["id"] = alarm_id
    with _connect() as conn:
        conn.execute(f"UPDATE alarms SET {assignments} WHERE id = :id", updates)
        if any(
            key in updates
            for key in {
                "alarm_kind",
                "time",
                "monitor_start",
                "anti_doze_delay_min",
                "reentry_block_min",
                "repeat_days",
                "enabled",
            }
        ):
            conn.execute("DELETE FROM anti_doze_runtime WHERE alarm_id = :id", {"id": alarm_id})
        conn.commit()
    return get_alarm(alarm_id)


def delete_alarm(alarm_id: int) -> bool:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM anti_doze_runtime WHERE alarm_id = ?", (alarm_id,))
        cur = conn.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))
        conn.commit()
        return cur.rowcount > 0


def get_settings() -> dict[str, Any]:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = DEFAULT_SETTINGS.copy()
    for row in rows:
        if row["key"] in DEFAULT_SETTINGS:
            settings[row["key"]] = _decode_setting(row["value"])
    return settings


def update_settings(values: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            [(key, _encode_setting(value)) for key, value in values.items() if key in DEFAULT_SETTINGS],
        )
        conn.commit()
    return get_settings()


def get_anti_doze_runtime(alarm_id: int) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM anti_doze_runtime WHERE alarm_id = ?",
            (alarm_id,),
        ).fetchone()
    return _row_to_dict(row)


def set_anti_doze_runtime(alarm_id: int, **values: Any) -> dict[str, Any]:
    init_db()
    current = get_anti_doze_runtime(alarm_id) or {}
    now = datetime.now().isoformat(timespec="seconds")
    state = {
        "phase": str(values.get("phase", current.get("phase") or "COUNTING")),
        "in_bed_since": values.get("in_bed_since", current.get("in_bed_since")),
        "cooldown_until": values.get("cooldown_until", current.get("cooldown_until")),
        "updated_at": now,
    }
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO anti_doze_runtime(
                alarm_id, phase, in_bed_since, cooldown_until, updated_at
            )
            VALUES(:alarm_id, :phase, :in_bed_since, :cooldown_until, :updated_at)
            ON CONFLICT(alarm_id) DO UPDATE SET
                phase = excluded.phase,
                in_bed_since = excluded.in_bed_since,
                cooldown_until = excluded.cooldown_until,
                updated_at = excluded.updated_at
            """,
            {"alarm_id": alarm_id, **state},
        )
        conn.commit()
    loaded = get_anti_doze_runtime(alarm_id)
    if loaded is None:
        raise RuntimeError("anti-doze runtime could not be loaded")
    return loaded


def clear_anti_doze_runtime(alarm_id: int) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM anti_doze_runtime WHERE alarm_id = ?", (alarm_id,))
        conn.commit()
