"""wauncher - a small third-party launcher for EVE Online.

Reads accounts, characters, launch groups and refresh tokens from the official EVE launcher, then
starts game clients itself the same way the official launcher does (OAuth refresh grant against the
EVE SSO, then exefile.exe with the launcher's argument set).
"""

APP_TITLE = "wauncher"
APP_ID = "wauncher"
DATA_FOLDER = "eve-wauncher"  # %LOCALAPPDATA%\eve-wauncher
REPO_URL = "https://github.com/wauncher/wauncher"  # sent as the ESI User-Agent contact

try:
    from .version import VERSION  # written by tools/bump_version.py (YYYYMMDD.XX)
except ImportError:  # running from a checkout that was never built
    VERSION = "00000000.00"
