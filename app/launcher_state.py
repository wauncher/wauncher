"""The official EVE launcher's data: read it, back it up, restore it, and find / stop the launcher process.

%APPDATA%\\EVE Online\\
    Local State      {"os_crypt": {"encrypted_key": base64("DPAPI" + CryptProtectData(aes key))}}
    state.json       {"state": base64("v10" + 12-byte nonce + AES-256-GCM ciphertext + 16-byte tag)}
    launcher-data.json  plain JSON: launcher settings (language, DirectX, shared cache path, startup delay)

The decrypted state holds accounts ("v2.1/users"), characters, launch groups ("v2/launch-groups") and,
per account, the SSO tokens the launcher uses (clientId "eveLauncherTQ" and an opaque refresh token).

The launcher process is eve-online.exe (an Electron app, several processes). It keeps the state in memory
and re-persists it while running, so state.json must only be written while the launcher is closed.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import time
from dataclasses import dataclass, field

from .crypto import aes_gcm_decrypt, aes_gcm_encrypt, dpapi_unprotect

LAUNCHER_EXE = "eve-online.exe"
PRODUCT = "eve-online"
TENANT = "tranquility"


def launcher_dir() -> str:
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "EVE Online")


def launcher_aes_key(directory: str | None = None) -> bytes:
    with open(os.path.join(directory or launcher_dir(), "Local State"), "r", encoding="utf-8") as fh:
        local_state = json.load(fh)
    enc = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    if enc[:5] != b"DPAPI":
        raise ValueError("Local State encrypted_key does not start with DPAPI")
    return dpapi_unprotect(enc[5:])


def decrypt_state(directory: str | None = None) -> dict:
    directory = directory or launcher_dir()
    key = launcher_aes_key(directory)
    with open(os.path.join(directory, "state.json"), "r", encoding="utf-8") as fh:
        blob = base64.b64decode(json.load(fh)["state"])
    if blob[:3] != b"v10":
        raise ValueError(f"unexpected state.json prefix {blob[:3]!r}")
    plaintext = aes_gcm_decrypt(key, blob[3:15], blob[15:-16], blob[-16:])
    return json.loads(plaintext.decode("utf-8"))


def encrypt_state(state: dict, key: bytes) -> dict:
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(state, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ciphertext, tag = aes_gcm_encrypt(key, nonce, plaintext)
    return {"state": base64.b64encode(b"v10" + nonce + ciphertext + tag).decode("ascii")}


def launcher_settings(directory: str | None = None) -> dict:
    """language / dx / shared_cache / startup_delay from launcher-data.json (defaults when missing)."""
    out = {"language": "en", "dx": "dx11", "shared_cache": r"C:\CCP\EVE", "startup_delay": 2}
    try:
        with open(os.path.join(directory or launcher_dir(), "launcher-data.json"), "r", encoding="utf-8") as fh:
            d = json.load(fh)["state"]
        settings = d.get("v2/settings", {})
        out["language"] = settings.get("eve-launcher", {}).get("selectedLanguage") or out["language"]
        out["dx"] = settings.get("eve-online", {}).get("clientDirectXVersion") or out["dx"]
        out["startup_delay"] = int(settings.get("eve-online", {}).get("clientStartupDelay") or out["startup_delay"])
        out["shared_cache"] = d.get("shared-cache", {}).get("eve-online", {}).get("location", {}).get("path") or out["shared_cache"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return out


# ------------------------------------------------------------------ snapshot for import
@dataclass
class Character:
    character_id: int
    name: str
    corporation: str = ""
    alliance: str = ""


@dataclass
class Account:
    user_id: int
    name: str
    characters: list[Character] = field(default_factory=list)
    active_character_id: int | None = None


@dataclass
class GroupMember:
    user_id: int
    character_id: int | None
    profile: str


@dataclass
class Group:
    group_id: str
    name: str
    members: list[GroupMember] = field(default_factory=list)


@dataclass
class Snapshot:
    accounts: list[Account]
    groups: list[Group]
    tokens: dict[int, dict]      # user_id -> {"clientId", "refreshToken", "accessToken", "expiresAt"}
    settings: dict
    active_group_id: str | None = None


def snapshot(state: dict | None = None, directory: str | None = None) -> Snapshot:
    """Everything wauncher imports from the official launcher, in launcher order."""
    state = state if state is not None else decrypt_state(directory)
    users = state.get("v2.1/users", {}).get(PRODUCT, {}).get(TENANT, {})
    entities = users.get("entities", {})
    order = [str(u) for u in users.get("ids", [])] or list(entities.keys())
    accounts: list[Account] = []
    tokens: dict[int, dict] = {}
    for uid in order:
        u = entities.get(uid)
        if not u:
            continue
        chars_block = u.get("characters", {}).get(PRODUCT, {})
        c_entities = chars_block.get("entities", {})
        c_order = [str(c) for c in chars_block.get("ids", [])] or list(c_entities.keys())
        chars = []
        for cid in c_order:
            c = c_entities.get(cid)
            if not c:
                continue
            aff = c.get("affiliation", {}) or {}
            chars.append(Character(int(c["characterId"]), c.get("name", ""),
                                   aff.get("corporationName", "") or "", aff.get("allianceName", "") or ""))
        acc = Account(int(uid), u.get("name") or str(uid), chars, chars_block.get("activeCharacterId") or None)
        accounts.append(acc)
        t = u.get("tokens") or {}
        if t.get("refreshToken"):
            tokens[int(uid)] = {"clientId": t.get("clientId") or "eveLauncherTQ", "refreshToken": t["refreshToken"],
                                "accessToken": t.get("accessToken", ""), "expiresAt": t.get("expiresAt", 0)}
    lg = state.get("v2/launch-groups", {}).get(PRODUCT, {})
    groups: list[Group] = []
    for gid in lg.get("ids", []) or list(lg.get("entities", {}).keys()):
        g = lg.get("entities", {}).get(gid)
        if not g:
            continue
        members = []
        ub = g.get("users", {})
        for m_uid in ub.get("ids", []) or list(ub.get("entities", {}).keys()):
            m = ub.get("entities", {}).get(str(m_uid))
            if not m:
                continue
            members.append(GroupMember(int(m.get("userId", m_uid)), int(m["characterId"]) if m.get("characterId") else None,
                                       m.get("profile") or "Default"))
        groups.append(Group(str(gid), g.get("name", str(gid)), members))
    return Snapshot(accounts, groups, tokens, launcher_settings(directory), lg.get("activeGroupId"))


# ------------------------------------------------------------------ backup / restore
def backup_to(path: str, directory: str | None = None) -> dict:
    """Decrypt the launcher state and write it as readable JSON. Returns the state."""
    state = decrypt_state(directory)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True, ensure_ascii=False)
    os.replace(tmp, path)
    return state


def restore_from(path: str, keep_copy_dir: str, directory: str | None = None) -> str:
    """Re-encrypt a backup with the machine's current launcher key and write it as state.json.
    The launcher must be closed. The current state.json is copied to keep_copy_dir first; that path is returned."""
    directory = directory or launcher_dir()
    if launcher_pids():
        raise RuntimeError("the EVE launcher (eve-online.exe) is running; close it first")
    with open(path, "r", encoding="utf-8") as fh:
        state = json.load(fh)
    if not isinstance(state, dict) or "v2.1/users" not in state:
        raise ValueError("this file does not look like a decrypted launcher state backup")
    key = launcher_aes_key(directory)
    encrypted = encrypt_state(state, key)
    # self-check before touching the launcher's file
    blob = base64.b64decode(encrypted["state"])
    if json.loads(aes_gcm_decrypt(key, blob[3:15], blob[15:-16], blob[-16:])) != state:
        raise RuntimeError("round-trip verification failed; nothing written")
    target = os.path.join(directory, "state.json")
    os.makedirs(keep_copy_dir, exist_ok=True)
    kept = os.path.join(keep_copy_dir, time.strftime("launcher-state-before-restore-%Y%m%d-%H%M%S.json"))
    if os.path.exists(target):
        shutil.copy2(target, kept)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(encrypted, fh, separators=(",", ":"))
    os.replace(tmp, target)
    return kept


# ------------------------------------------------------------------ write launch groups into the launcher
def write_groups(groups: list[dict], keep_copy_dir: str, directory: str | None = None) -> tuple[int, int, str]:
    """Upsert launch groups into the official launcher's state.json. groups: [{"launcherGroupId", "name",
    "profile" (optional settings profile for every member), "members": [{"userId", "characterId" | None}]}].
    Groups the launcher has that are not in the list are left
    alone. The launcher must be closed. Returns (added, updated, path of the kept copy of the old state.json)."""
    directory = directory or launcher_dir()
    if launcher_pids():
        raise RuntimeError("the EVE launcher (eve-online.exe) is running; close it first")
    state = decrypt_state(directory)
    key = launcher_aes_key(directory)
    lg = state.setdefault("v2/launch-groups", {}).setdefault(PRODUCT, {})
    entities = lg.setdefault("entities", {})
    ids = lg.setdefault("ids", [])
    added = updated = 0
    for g in groups:
        gid = str(g["launcherGroupId"])
        existing_users = (entities.get(gid) or {}).get("users", {}).get("entities", {})
        user_entities: dict[str, dict] = {}
        user_ids: list[int] = []
        for m in g.get("members", []):
            uid = int(m["userId"])
            entry: dict = {"userId": uid}
            if m.get("characterId"):
                entry["characterId"] = int(m["characterId"])
            old = existing_users.get(str(uid)) or {}
            if g.get("profile"):
                entry["profile"] = g["profile"]     # the group's settings profile, applied to every member
            elif old.get("profile"):
                entry["profile"] = old["profile"]   # keep whatever the launcher had
            user_entities[str(uid)] = entry
            user_ids.append(uid)
        entity = {"groupId": gid, "name": g["name"], "users": {"entities": user_entities, "ids": user_ids}}
        if gid in entities:
            updated += 1
        else:
            added += 1
            ids.append(gid)  # the launcher appends new groups too (its list shows newest first)
        entities[gid] = entity
    if not lg.get("activeGroupId") and ids:
        lg["activeGroupId"] = ids[0]
    encrypted = encrypt_state(state, key)
    blob = base64.b64decode(encrypted["state"])
    if json.loads(aes_gcm_decrypt(key, blob[3:15], blob[15:-16], blob[-16:])) != state:
        raise RuntimeError("round-trip verification failed; nothing written")
    target = os.path.join(directory, "state.json")
    os.makedirs(keep_copy_dir, exist_ok=True)
    kept = os.path.join(keep_copy_dir, time.strftime("launcher-state-before-groups-%Y%m%d-%H%M%S.json"))
    if os.path.exists(target):
        shutil.copy2(target, kept)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(encrypted, fh, separators=(",", ":"))
    os.replace(tmp, target)
    return added, updated, kept


# ------------------------------------------------------------------ launcher process
def launcher_pids() -> list[int]:
    from .client import pids_by_name
    return pids_by_name(LAUNCHER_EXE)


def kill_launcher(grace: float = 4.0) -> int:
    """Terminate every eve-online.exe (the launcher only - game clients are exefile.exe). Returns the count."""
    import psutil
    procs = []
    for pid in launcher_pids():
        try:
            procs.append(psutil.Process(pid))
        except psutil.NoSuchProcess:
            pass
    for p in procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _gone, alive = psutil.wait_procs(procs, timeout=grace)
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if alive:
        psutil.wait_procs(alive, timeout=grace)
    return len(procs)
