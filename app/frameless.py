"""Borderless-looking window on Windows without giving up the native window manager.

Instead of overrideredirect (no taskbar button, no minimise, no Aero snap) the top-level answers
WM_NCCALCSIZE so that the caption and top frame become client area: nothing is painted above the
app's own title strip. The left / right / bottom frame stays as Windows draws it (a hairline plus the
invisible resize grips, which Tk widgets never cover), so edge resizing keeps working natively.

A Python window procedure must not be installed while Windows runs one of its modal loops (moving,
sizing): the nested ctypes callbacks from inside a Tk handler are fatal on recent Pythons. So the
subclass is applied only for the instant needed to force a frame recalculation, then the original
procedure is restored. Windows recalculates the frame on every size change, which is why `refresh`
must run from the top-level's <Configure> event.

Moving is started from a Tk click on the title strip with ReleaseCapture + a posted
WM_SYSCOMMAND(SC_MOVE), so Windows runs its own smooth move loop (with Aero snap).
Tk on Windows gives every widget its own HWND, which is why WM_NCHITTEST on the top-level alone
cannot be used for the strip.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import tkinter as tk

WM_NCCALCSIZE = 0x0083
HTCAPTION = 2
VK_LBUTTON = 0x01
WM_SYSCOMMAND, SC_MOVE, SC_SIZE, HT_TOP_DIR = 0x0112, 0xF010, 0xF000, 3  # SC_SIZE + 3 = top edge
GWLP_WNDPROC = -4
SM_CYSIZEFRAME, SM_CXPADDEDBORDER = 33, 92
SWP_FRAMECHANGED_ONLY = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE | NOMOVE | NOZORDER | FRAMECHANGED

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)

if os.name == "nt":
    _user32 = ctypes.windll.user32
    _user32.SetWindowLongPtrW.argtypes = (wt.HWND, ctypes.c_int, ctypes.c_ssize_t)
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowRect.argtypes = (wt.HWND, ctypes.POINTER(wt.RECT))
    _user32.SetWindowPos.argtypes = (wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint)
    _user32.PostMessageW.argtypes = (wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
    # Calls that re-enter our (temporary) window procedure keep the GIL.
    _CallWindowProcW = ctypes.PyDLL("user32").CallWindowProcW
    _CallWindowProcW.argtypes = (ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
    _CallWindowProcW.restype = LRESULT
    _SetWindowPosGIL = ctypes.PyDLL("user32").SetWindowPos
    _SetWindowPosGIL.argtypes = _user32.SetWindowPos.argtypes


class Frameless:
    """Attach to a tk.Tk after it is mapped; call refresh() from the top-level's <Configure>."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.hwnd = int(_user32.GetParent(root.winfo_id()) or root.winfo_id())
        self._proc = WNDPROC(self._wndproc)  # keep a reference or the callback is garbage collected
        self._old = 0
        self._last_size: tuple[int, int] = (0, 0)
        self.refresh(force=True)

    # ---------------------------------------------------------------- public
    def window_size(self) -> tuple[int, int]:
        rect = wt.RECT()
        _user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        return rect.right - rect.left, rect.bottom - rect.top

    def refresh(self, force: bool = False) -> None:
        """Recalculate the frame with our WM_NCCALCSIZE answer, then step out of the way again."""
        size = self.window_size()
        if not force and size == self._last_size:
            return  # plain move: Windows did not recalculate the frame, nothing to do
        if _user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
            # Still inside Windows' sizing loop (<Configure> fires during it): touching the frame now
            # would run our callback nested in that loop. Try again once the button is released.
            self.root.after(60, self.refresh)
            return
        self._last_size = size
        self._old = _user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, ctypes.cast(self._proc, ctypes.c_void_p).value)
        try:
            _SetWindowPosGIL(self.hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED_ONLY)  # sends WM_NCCALCSIZE synchronously
        finally:
            _user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, self._old)
            self._old = 0
        self._last_size = self.window_size()

    def start_move(self) -> None:
        """Call from a Tk <ButtonPress-1> on the title strip: Windows takes over the drag.
        Posted, not sent: the modal move loop must run from the message loop, not nested inside
        the Tk handler (which would also nest our WM_NCCALCSIZE callback and crash)."""
        _user32.ReleaseCapture()
        _user32.PostMessageW(self.hwnd, WM_SYSCOMMAND, SC_MOVE | HTCAPTION, 0)

    def start_resize_top(self) -> None:
        """Call from a <ButtonPress-1> right at the top edge (the only edge Windows no longer owns)."""
        _user32.ReleaseCapture()
        _user32.PostMessageW(self.hwnd, WM_SYSCOMMAND, SC_SIZE | HT_TOP_DIR, 0)

    # -------------------------------------------------------------- internals
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_NCCALCSIZE and wparam:
                rect = ctypes.cast(lparam, ctypes.POINTER(wt.RECT)).contents  # NCCALCSIZE_PARAMS.rgrc[0]
                top = rect.top
                result = _CallWindowProcW(self._old, hwnd, msg, wparam, lparam)
                if _user32.IsZoomed(hwnd):
                    # Maximised windows hang their (invisible) frame off-screen; start at the screen edge.
                    top += _user32.GetSystemMetrics(SM_CYSIZEFRAME) + _user32.GetSystemMetrics(SM_CXPADDEDBORDER)
                rect.top = top  # reclaim the caption + top frame, keep the side / bottom frame
                return result
        except Exception:  # never let a Python error escape into the message loop
            pass
        return _CallWindowProcW(self._old, hwnd, msg, wparam, lparam)
