r"""Game clients: build the launcher's argument set, start exefile.exe, and find the ones already running.

Argument set (from the official launcher 1.16.1, in its order; prefix "/", separator "=" except the two
colon keys). Sensitive: ssoToken, refreshToken, deviceID, machineHash, journeyID.

  /noconsole
  /server:tranquility.servers.eveonline.com
  /ssoToken=<access token JWT, scope eveClientLogin>
  /refreshToken=<refresh token>
  /settingsprofile=<profile>                  ("Default" unless the launch group says otherwise)
  /language=<launcher language>
  /LauncherData=base64("eve-online:tranquility::<userId>:<characterId or empty>")
  /triplatform=<dx11|dx12>                    (omitted for dx0)
  /deviceID=<HKCU\SOFTWARE\CCP\EVE\DeviceIdV2>
  /machineHash=<DeviceIdV2 without dashes>
  /journeyID=base64(bytes of HKCU\SOFTWARE\CCP\EVE\JourneyIdV2)
  /autoSelectCharacter:<characterId>          (only when a character is chosen)

The EVE client window title is "EVE - <Character Name>" once logged in and plain "EVE" on the login /
character-selection screens.
"""
from __future__ import annotations

import base64
import ctypes
import json
import ctypes.wintypes as wt
import os
import subprocess
import uuid
import winreg
from dataclasses import dataclass

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

CLIENT_EXE = "exefile.exe"
PRODUCT = "eve-online"
TENANT = "tranquility"
SENSITIVE_KEYS = ("/ssotoken", "/refreshtoken", "/deviceid", "/machinehash", "/journeyid")


def registry_ids() -> tuple[str, str]:
    """(DeviceIdV2, JourneyIdV2) as the official launcher stored them; random UUIDs when absent."""
    device_id = journey_id = ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\CCP\EVE") as key:
            try:
                device_id = str(winreg.QueryValueEx(key, "DeviceIdV2")[0])
            except OSError:
                pass
            try:
                journey_id = str(winreg.QueryValueEx(key, "JourneyIdV2")[0])
            except OSError:
                pass
    except OSError:
        pass
    return device_id or str(uuid.uuid4()), journey_id or str(uuid.uuid4())


def client_exe(shared_cache: str) -> str:
    return os.path.join(shared_cache, "tq", "bin64", CLIENT_EXE)


def installed_build(shared_cache: str) -> str:
    """The client build number from tq/start.ini ([main] build = ...), "" when unknown. ESI reports the
    same number as server_version, so the two can be compared directly."""
    import configparser
    ini = os.path.join(shared_cache, "tq", "start.ini")
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(ini, encoding="utf-8")
        return cp.get("main", "build", fallback="").strip()
    except (configparser.Error, OSError):
        return ""


def build_args(user_id: int, character_id: int | None, access_token: str, refresh_token: str, profile: str,
               language: str, dx: str, device_id: str, journey_id: str) -> list[str]:
    launcher_data = base64.b64encode(f"{PRODUCT}:{TENANT}::{user_id}:{character_id or ''}".encode()).decode()
    try:
        journey_b64 = base64.b64encode(uuid.UUID(journey_id).bytes).decode()
    except ValueError:
        journey_b64 = base64.b64encode(journey_id.encode()).decode()
    args = [
        "/noconsole",
        f"/server:{TENANT}.servers.eveonline.com",
        f"/ssoToken={access_token}",
        f"/refreshToken={refresh_token}",
        f"/settingsprofile={profile or 'Default'}",
        f"/language={language or 'en'}",
        f"/LauncherData={launcher_data}",
    ]
    if dx and dx != "dx0":
        args.append(f"/triplatform={dx}")
    args += [f"/deviceID={device_id}", f"/machineHash={device_id.replace('-', '')}", f"/journeyID={journey_b64}"]
    if character_id:
        args.append(f"/autoSelectCharacter:{character_id}")
    return args


def redact(args: list[str]) -> str:
    out = []
    for a in args:
        key = a.split("=", 1)[0].split(":", 1)[0].lower()
        out.append(key + "=***" if key in SENSITIVE_KEYS else a)
    return " ".join(out)


def spawn(exe: str, args: list[str]) -> tuple[int, float]:
    """Start the client detached. Returns (pid, process creation time as epoch seconds)."""
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen([exe] + args, cwd=os.path.dirname(exe), creationflags=flags, close_fds=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ctime = 0.0
    if psutil is not None:
        try:
            ctime = float(psutil.Process(proc.pid).create_time())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return proc.pid, ctime


# ------------------------------------------------------------------ running clients
@dataclass
class RunningClient:
    pid: int
    create_time: float
    title: str
    character_name: str | None   # from the window title: None = login / character screen (or no window yet)
    hwnd: int = 0
    user_id: int | None = None       # from the command line (/LauncherData or the ssoToken JWT)
    character_id: int | None = None  # from the command line (/LauncherData or /autoSelectCharacter)
    profile: str = ""                # /settingsprofile
    tenant: str = ""                 # /server or the token
    cmdline_read: bool = False       # False when the command line could not be read (elevated process)


def _jwt_claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return {}


def parse_command_line(args: list[str]) -> dict:
    """Identify a client from its arguments, the way the official launcher does: /LauncherData first
    (product:tenant:branch:userId:characterId), then the ssoToken's sub claim (USER:EVE:<id>), then
    /autoSelectCharacter, /settingsprofile and /server."""
    out: dict = {"user_id": None, "character_id": None, "profile": "", "tenant": ""}
    for raw in args[1:]:
        a = raw.strip('"')
        low = a.lower()
        if low.startswith("/launcherdata="):
            try:
                parts = (base64.b64decode(a.split("=", 1)[1]).decode("utf-8").split(":", 4) + [""] * 5)[:5]
            except (ValueError, UnicodeDecodeError):
                continue
            _product, tenant, _branch, uid, cid = parts
            out["tenant"] = out["tenant"] or tenant
            if uid.isdigit():
                out["user_id"] = int(uid)
            if cid.isdigit():
                out["character_id"] = int(cid)
        elif low.startswith("/ssotoken="):
            claims = _jwt_claims(a.split("=", 1)[1])
            sub = str(claims.get("sub", ""))
            if out["user_id"] is None and sub.rsplit(":", 1)[-1].isdigit():
                out["user_id"] = int(sub.rsplit(":", 1)[-1])
            out["tenant"] = out["tenant"] or str(claims.get("tenant", ""))
        elif low.startswith("/autoselectcharacter:"):
            value = a.split(":", 1)[1]
            if value.isdigit() and out["character_id"] is None:
                out["character_id"] = int(value)
        elif low.startswith("/settingsprofile="):
            out["profile"] = a.split("=", 1)[1]
        elif low.startswith("/server:"):
            out["tenant"] = out["tenant"] or a.split(":", 1)[1].split(".")[0]
    return out


def _eve_windows() -> dict[int, list[tuple[int, str]]]:
    """pid -> [(hwnd, title)] for visible windows titled "EVE" / "EVE - <name>"."""
    user32 = ctypes.windll.user32
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    titles: dict[int, list[tuple[int, str]]] = {}

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if title == "EVE" or title.startswith("EVE - "):
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            titles.setdefault(pid.value, []).append((int(hwnd), title))
        return True

    user32.EnumWindows(proc_type(callback), 0)
    return titles


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def pids_by_name(exe_name: str) -> list[int]:
    """PIDs of every process with this image name, from a CreateToolhelp32Snapshot walk (the official
    launcher does the same). Takes a few milliseconds and needs no handle to any process; psutil's
    process_iter costs seconds the first time because it opens every process on the machine."""
    k32 = ctypes.windll.kernel32
    TH32CS_SNAPPROCESS, INVALID = 0x2, ctypes.c_void_p(-1).value
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = (ctypes.c_void_p, ctypes.POINTER(_PROCESSENTRY32W))
    k32.CloseHandle.argtypes = (ctypes.c_void_p,)
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID:
        return []
    pids: list[int] = []
    want = exe_name.lower()
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == want:
                pids.append(int(entry.th32ProcessID))
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return pids


def list_running() -> list[RunningClient]:
    if psutil is None:
        return []
    titles = _eve_windows()
    out: list[RunningClient] = []
    for pid in pids_by_name(CLIENT_EXE):
        try:
            proc = psutil.Process(pid)
            ctime = float(proc.create_time() or 0.0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        info: dict = {}
        read_ok = False
        try:
            info = parse_command_line(proc.cmdline())
            read_ok = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError):
            pass
        best: tuple[int, str] | None = None
        for hwnd, title in titles.get(pid, []):
            if title.startswith("EVE - "):
                best = (hwnd, title)
                break
            best = best or (hwnd, title)
        if best is None:
            client = RunningClient(pid, ctime, CLIENT_EXE, None, 0)
        elif best[1].startswith("EVE - "):
            client = RunningClient(pid, ctime, best[1], best[1][len("EVE - "):].strip() or None, best[0])
        else:
            client = RunningClient(pid, ctime, best[1], None, best[0])
        client.user_id, client.character_id = info.get("user_id"), info.get("character_id")
        client.profile, client.tenant, client.cmdline_read = info.get("profile", ""), info.get("tenant", ""), read_ok
        out.append(client)
    return sorted(out, key=lambda c: c.create_time)


def is_alive(pid: int, create_time: float, tolerance: float = 1.0) -> bool:
    """True when this exact process (pid AND creation time) still exists."""
    if psutil is None:
        return False
    try:
        p = psutil.Process(pid)
        return p.name().lower() == CLIENT_EXE and (not create_time or abs(p.create_time() - create_time) < tolerance)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def kill(pid: int, create_time: float, grace: float = 5.0) -> bool:
    if not is_alive(pid, create_time):
        return False
    p = psutil.Process(pid)
    try:
        p.terminate()
        p.wait(grace)
    except psutil.TimeoutExpired:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return True


def focus(hwnd: int) -> None:
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindowAsync(hwnd, 9)  # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
