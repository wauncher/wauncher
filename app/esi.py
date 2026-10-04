"""Public ESI lookups (no authentication): a character's current corporation and alliance."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import APP_ID, REPO_URL, VERSION

ESI = "https://esi.evetech.net/latest"
USER_AGENT = f"{APP_ID}/{VERSION} (+{REPO_URL})"


class EsiError(Exception):
    pass


def _get(path: str) -> dict | list:
    req = urllib.request.Request(f"{ESI}{path}?datasource=tranquility", headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise EsiError(f"HTTP {exc.code} for {path}") from None
    except urllib.error.URLError as exc:
        raise EsiError(f"cannot reach ESI: {exc.reason}") from None


def _names(ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    body = json.dumps(sorted(set(ids))).encode()
    req = urllib.request.Request(f"{ESI}/universe/names/?datasource=tranquility", data=body, method="POST",
                                 headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return {int(e["id"]): e["name"] for e in json.loads(resp.read())}
    except urllib.error.HTTPError as exc:
        raise EsiError(f"HTTP {exc.code} resolving names") from None
    except urllib.error.URLError as exc:
        raise EsiError(f"cannot reach ESI: {exc.reason}") from None


def affiliation(character_id: int) -> dict:
    """{"name", "corporation_id", "corporation", "alliance_id", "alliance"} for a character (alliance may be blank)."""
    info = _get(f"/characters/{int(character_id)}/")
    corp_id = int(info.get("corporation_id") or 0)
    alli_id = int(info.get("alliance_id") or 0)
    names = _names([i for i in (corp_id, alli_id) if i])
    return {"name": info.get("name", ""), "corporation_id": corp_id, "corporation": names.get(corp_id, ""),
            "alliance_id": alli_id, "alliance": names.get(alli_id, "") if alli_id else ""}
