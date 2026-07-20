from __future__ import annotations

import time

import pytest

import emfit


@pytest.mark.asyncio
async def test_stale_last_seen_is_unknown(monkeypatch):
    async def fake_fetch_status():
        return {
            "in_bed": False,
            "bed_status_label": "out of bed",
            "last_seen_timestamp": (time.time() - emfit.EMFIT_STALE_SEC - 1) * 1000,
        }

    monkeypatch.setattr(emfit, "_fetch_status", fake_fetch_status)

    assert await emfit.get_in_bed() is None
    assert emfit.last_status["in_bed"] is None
    assert emfit.last_status["label"].startswith("stale (last seen ")
    assert emfit.last_status["last_error"] is None