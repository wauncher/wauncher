"""Client settings profiles: the settings_<name> folders under the client's settings directory.

For a shared cache at C:\\CCP\\EVE the client keeps its settings in
%LOCALAPPDATA%\\CCP\\EVE\\c_ccp_eve_tq_tranquility\\settings_<profile>\\ and /settingsprofile=<profile> picks one.
"""
from __future__ import annotations

import os
import re


def settings_root() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "CCP", "EVE")


def mangled_dir(shared_cache: str) -> str:
    """C:\\CCP\\EVE -> c_ccp_eve_tq_tranquility (the launcher's naming)."""
    p = shared_cache.strip().rstrip("\\/").lower().replace(":\\", "_").replace(":/", "_")
    p = re.sub(r"[\\/]", "_", p)
    return f"{p}_tq_tranquility"


def settings_dir(shared_cache: str) -> str | None:
    root = settings_root()
    preferred = os.path.join(root, mangled_dir(shared_cache))
    if os.path.isdir(preferred):
        return preferred
    try:
        candidates = [os.path.join(root, d) for d in os.listdir(root)
                      if d.endswith("_tq_tranquility") and os.path.isdir(os.path.join(root, d))]
    except OSError:
        return None
    candidates = [c for c in candidates if any(n.startswith("settings_") for n in os.listdir(c))]
    return candidates[0] if candidates else None


def list_profiles(shared_cache: str) -> list[str]:
    """Profile names, alphabetical (case-insensitive). Always contains "Default"."""
    names: set[str] = {"Default"}
    d = settings_dir(shared_cache)
    if d:
        try:
            for entry in os.listdir(d):
                if entry.startswith("settings_") and os.path.isdir(os.path.join(d, entry)):
                    names.add(entry[len("settings_"):])
        except OSError:
            pass
    return sorted(names, key=str.lower)
