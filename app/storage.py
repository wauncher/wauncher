"""Where wauncher keeps things (all under %LOCALAPPDATA%\\eve-wauncher):

  config.json    settings + window geometry + display order of accounts / characters (plain JSON)
  data.json      accounts, characters, launch groups as imported from the official launcher (plain JSON,
                 no secrets)
  tokens.dat     DPAPI-protected JSON: per account clientId / refreshToken / last access token. Only the
                 Windows user that wrote it can read it. Kept apart from config.json on purpose.
  launched.json  clients wauncher started: processId + creationTime (+ who), so a reused PID is never
                 mistaken for our client
  backups\\       launcher state backups (readable JSON) and the copies taken before a restore
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any

from . import DATA_FOLDER
from .crypto import dpapi_protect, dpapi_unprotect

DEFAULT_CONFIG: dict[str, Any] = {
    "kill_conflicting": False,   # close a running client of the same account before launching
    "login_screen": False,       # start at the login / character screen (no /autoSelectCharacter)
    "profile_mode": "group",     # group: the launch group's profile, else Default / default: always Default /
                                 # force: always the profile named below
    "profile": "Default",        # the forced settings_<profile> when profile_mode is "force"
    "startup_delay": 0,          # seconds between clients (0 = the official launcher's setting)
    "dx": "",                    # dx11 / dx12 / dx0; blank = the official launcher's setting
    "language": "",              # blank = the official launcher's setting
    "shared_cache": "",          # folder holding tq\\bin64\\exefile.exe; blank = the launcher's setting
    "account_order": [],         # user ids in display order (accounts not listed go last, launcher order)
    "character_order": {},       # user id -> [character ids] in display order
    "streamer_mode": False,      # hide account names / ids in the UI (characters stay visible)
    "exit_to_tray": False,       # the close button hides the window to the tray instead of quitting
    "theme": "midnight",         # midnight / orange / gray / white (psycho)
    "window_geometry": "",
    "window_zoomed": False,
}


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> str:
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundle_dir() -> str:
    return getattr(sys, "_MEIPASS", exe_dir())


def data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, DATA_FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def backups_dir() -> str:
    path = os.path.join(data_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


class Config:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.path = os.path.join(data_dir(), "config.json")
        self.values: dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))
        loaded = _read_json(self.path)
        if isinstance(loaded, dict):
            self.values.update({k: v for k, v in loaded.items() if k in DEFAULT_CONFIG})

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.values.get(key, DEFAULT_CONFIG.get(key, default))

    def update(self, **changes: Any) -> None:
        with self._lock:
            self.values.update(changes)
            try:
                _write_json(self.path, self.values)
            except OSError:
                pass


class Data:
    """Accounts / characters / groups (no secrets). Shape:
    {"imported_at": epoch, "accounts": [{"userId", "name", "activeCharacterId",
        "characters": [{"characterId", "name", "corporation", "alliance"}]}],
     "groups": [{"groupId", "name", "local": bool, "members": [{"userId", "characterId"}]}],
     "active_group_id": str|None, "launcher_settings": {...}}"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.path = os.path.join(data_dir(), "data.json")
        loaded = _read_json(self.path)
        self.d: dict[str, Any] = loaded if isinstance(loaded, dict) else {
            "imported_at": 0, "accounts": [], "groups": [], "active_group_id": None, "launcher_settings": {}}

    @property
    def accounts(self) -> list[dict]:
        return self.d.get("accounts", [])

    @property
    def groups(self) -> list[dict]:
        return self.d.get("groups", [])

    def group(self, group_id: str) -> dict | None:
        return next((g for g in self.groups if g.get("groupId") == group_id), None)

    def account(self, user_id: int) -> dict | None:
        return next((a for a in self.accounts if int(a["userId"]) == int(user_id)), None)

    def character(self, character_id: int) -> tuple[dict, dict] | None:
        for a in self.accounts:
            for c in a.get("characters", []):
                if int(c["characterId"]) == int(character_id):
                    return a, c
        return None

    def save(self) -> None:
        with self._lock:
            try:
                _write_json(self.path, self.d)
            except OSError:
                pass


class TokenStore:
    """user id -> {"clientId", "refreshToken", "accessToken", "expiresAt", "updatedAt"}, DPAPI-protected."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.path = os.path.join(data_dir(), "tokens.dat")
        self.tokens: dict[str, dict] = {}
        self.load_error = ""
        try:
            with open(self.path, "rb") as fh:
                blob = fh.read()
            if blob:
                self.tokens = json.loads(dpapi_unprotect(blob).decode("utf-8"))
        except FileNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001 - a store another Windows user wrote, or a damaged file
            self.load_error = str(exc)

    def get(self, user_id: int) -> dict | None:
        return self.tokens.get(str(user_id))

    def set(self, user_id: int, **fields: Any) -> None:
        with self._lock:
            entry = self.tokens.setdefault(str(user_id), {})
            entry.update(fields)
            entry["updatedAt"] = time.time()
        self.save()

    def replace_all(self, tokens: dict[int, dict]) -> None:
        with self._lock:
            for uid, t in tokens.items():
                entry = self.tokens.setdefault(str(uid), {})
                entry.update(t)
                entry["updatedAt"] = time.time()
        self.save()

    def save(self) -> None:
        with self._lock:
            blob = dpapi_protect(json.dumps(self.tokens).encode("utf-8"), "wauncher tokens")
            tmp = self.path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(blob)
            os.replace(tmp, self.path)

    def __len__(self) -> int:
        return len(self.tokens)


class Launched:
    """Clients started by wauncher: [{"pid", "creationTime", "userId", "characterId", "characterName",
    "accountName", "profile", "launchedAt"}]. creationTime is the process creation time (epoch seconds)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.path = os.path.join(data_dir(), "launched.json")
        loaded = _read_json(self.path)
        self.clients: list[dict] = loaded.get("clients", []) if isinstance(loaded, dict) else []

    def add(self, **entry: Any) -> None:
        with self._lock:
            self.clients.append(entry)
        self.save()

    def prune(self, alive) -> list[dict]:
        """Drop entries whose process is gone. alive(pid, creationTime) -> bool. Returns the removed ones."""
        with self._lock:
            keep, gone = [], []
            for c in self.clients:
                (keep if alive(int(c.get("pid", 0)), float(c.get("creationTime", 0))) else gone).append(c)
            changed = bool(gone)
            self.clients = keep
        if changed:
            self.save()
        return gone

    def for_user(self, user_id: int) -> list[dict]:
        return [c for c in self.clients if int(c.get("userId", -1)) == int(user_id)]

    def save(self) -> None:
        with self._lock:
            try:
                _write_json(self.path, {"clients": self.clients, "updatedAt": time.time()})
            except OSError:
                pass
