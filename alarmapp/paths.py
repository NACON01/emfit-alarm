from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SOUNDS_DIR = REPO_ROOT / "sounds"


def sound_path(name: str) -> Path:
    path = (SOUNDS_DIR / str(name)).resolve()
    if SOUNDS_DIR.resolve() not in path.parents:
        raise ValueError("invalid sound path")
    return path


def default_sound_path() -> str:
    return str(sound_path("alarm_long.mp3"))