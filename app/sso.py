"""EVE SSO: the OAuth2 refresh grant the official launcher uses, plus JWT helpers.

POST https://login.eveonline.com/v2/oauth/token
     grant_type=refresh_token&client_id=eveLauncherTQ&refresh_token=...
-> {"access_token", "expires_in", "id_token", "refresh_token", "token_type"}

Observed 2026-09-30: the SSO returns the same refresh token every time (no rotation), so nothing has
to be written back anywhere for the official launcher to keep working.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"


class SsoError(Exception):
    pass


def refresh(client_id: str, refresh_token: str, timeout: float = 30.0) -> dict:
    body = urllib.parse.urlencode({"grant_type": "refresh_token", "client_id": client_id,
                                   "refresh_token": refresh_token}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read(300).decode("utf-8", "replace")
        raise SsoError(f"HTTP {exc.code} from SSO: {detail}") from None
    except urllib.error.URLError as exc:
        raise SsoError(f"cannot reach SSO: {exc.reason}") from None
    if "access_token" not in data:
        raise SsoError(f"SSO response has no access_token: {data}")
    return data


def jwt_claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return {}


def token_valid_for(token: str, margin: float = 60.0) -> float:
    """Seconds the access token is still good for (minus a safety margin); <= 0 when expired/unknown."""
    exp = jwt_claims(token).get("exp")
    if not exp:
        return 0.0
    return float(exp) - time.time() - margin
