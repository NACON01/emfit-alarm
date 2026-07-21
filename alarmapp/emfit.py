from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


try:
    import httpx
except ImportError:  # pragma: no cover - used only when dependency install is unavailable.
    httpx = None


LOGGER = logging.getLogger(__name__)
STATUS_URL = "http://127.0.0.1:8001/api/status"
# The qs2 sidecar queries qs2.emfit.com live on each call (~4-5s), so allow ample time.
EMFIT_TIMEOUT = 10
EMFIT_STALE_SEC = 1800

last_status: dict[str, Any] = {
    "in_bed": None,
    "label": None,
    "last_error": None,
}


def _fetch_with_urllib() -> dict[str, Any]:
    req = Request(STATUS_URL, headers={"Accept": "application/json"})
    with urlopen(req, timeout=EMFIT_TIMEOUT) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


async def _fetch_status() -> dict[str, Any]:
    if httpx is not None:
        async with httpx.AsyncClient(timeout=EMFIT_TIMEOUT) as client:
            response = await client.get(STATUS_URL)
            response.raise_for_status()
            return response.json()
    return await asyncio.to_thread(_fetch_with_urllib)


def cached_in_bed() -> bool | None:
    """Last known in_bed value (kept fresh by the background poller). Lets the
    fast ring loop read presence without awaiting the slow sensor endpoint."""
    value = last_status.get("in_bed")
    return value if isinstance(value, bool) else None


async def get_in_bed() -> bool | None:
    try:
        data = await _fetch_status()
        in_bed = data.get("in_bed")
        if not isinstance(in_bed, bool):
            raise ValueError("emfit response did not contain boolean in_bed")
        label = data.get("bed_status_label")
        last_seen = data.get("last_seen_timestamp")
        stale_age_sec: float | None = None
        if last_seen is not None:
            try:
                stale_age_sec = max(0.0, time.time() - float(last_seen) / 1000.0)
            except (TypeError, ValueError):
                stale_age_sec = None
        if stale_age_sec is not None and stale_age_sec > EMFIT_STALE_SEC:
            in_bed = None
            label = f"stale (last seen {stale_age_sec / 60:.0f}m ago)"
        last_status.update(
            {
                "in_bed": in_bed,
                "label": label,
                "last_error": None,
            }
        )
        return in_bed
    except (Exception, URLError) as exc:
        LOGGER.warning("emfit status fetch failed: %s", exc)
        last_status.update(
            {
                "in_bed": None,
                "label": None,
                "last_error": str(exc),
            }
        )
        return None
