"""Tranquility status straight from ESI: GET https://esi.evetech.net/latest/status/?datasource=tranquility

  200 -> {"players": 24109, "server_version": "3561556", "start_time": "2026-09-30T11:05:03Z", "vip": true?}
  5xx / connection failure while the cluster is down -> treated as offline

Polled every 30 s. Around downtime (11:00-11:30 UTC) it is polled every 5 s until the server is back up.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request

from . import APP_ID, REPO_URL, VERSION

STATUS_URL = "https://esi.evetech.net/latest/status/?datasource=tranquility"
USER_AGENT = f"{APP_ID}/{VERSION} (+{REPO_URL})"
NORMAL_INTERVAL = 30
DOWNTIME_INTERVAL = 5
DOWNTIME_START = dt.time(11, 0)
DOWNTIME_END = dt.time(11, 30)


def fetch(timeout: float = 10.0) -> dict:
    """Always returns a dict with "online" (True / False / None=unknown) plus ESI's fields when it answered."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    req = urllib.request.Request(STATUS_URL, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (502, 503, 504):  # ESI answers this way while Tranquility is down
            return {"online": False, "checked_at": now, "error": f"HTTP {exc.code}"}
        return {"online": None, "checked_at": now, "error": f"HTTP {exc.code}"}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"online": None, "checked_at": now, "error": str(getattr(exc, "reason", exc))}
    if not isinstance(data, dict) or "players" not in data:
        return {"online": None, "checked_at": now, "error": "unexpected response"}
    return {"online": True, "checked_at": now, "players": int(data.get("players") or 0),
            "server_version": str(data.get("server_version", "")), "start_time": data.get("start_time", ""),
            "vip": bool(data.get("vip", False)), "error": None}


def in_downtime_window(now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now(dt.timezone.utc)
    return DOWNTIME_START <= now.time() < DOWNTIME_END


def next_interval(status: dict, now: dt.datetime | None = None) -> int:
    """5 s while inside the downtime window and the server is not confirmed up, else 30 s."""
    if in_downtime_window(now) and status.get("online") is not True:
        return DOWNTIME_INTERVAL
    return NORMAL_INTERVAL


def describe(status: dict) -> tuple[str, str]:
    """(text, kind): kind is "ok" (up, open), "vip" (up, VIP only) or "muted" (not up / unknown)."""
    online = status.get("online")
    if online is True:
        players = status.get("players")
        text = f"TQ online · {players:,} players" if isinstance(players, int) else "TQ online"
        if status.get("vip"):
            return text + " · VIP", "vip"
        return text, "ok"
    if online is False:
        return "TQ offline" + (" (downtime)" if in_downtime_window() else ""), "muted"
    return "TQ status unavailable" + (f" ({status['error']})" if status.get("error") else ""), "muted"
