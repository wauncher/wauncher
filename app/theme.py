"""Palettes and the ttk theme. Flat surfaces separated by shade rather than borders.

The colour names are module globals so the rest of the app reads them as theme.BG etc.; set_palette()
rebinds them and apply_theme() re-styles ttk. Widgets that were given explicit colours (tk.Frame, tk.Text,
Listbox, ...) have to be rebuilt after a switch, which the main window does.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

UI_FAMILY = "Segoe UI"
FONT = (UI_FAMILY, 10)
FONT_BOLD = (UI_FAMILY, 10, "bold")
FONT_SMALL = (UI_FAMILY, 9)
FONT_SMALL_BOLD = (UI_FAMILY, 9, "bold")
FONT_BIG = (UI_FAMILY, 10, "bold")

PALETTES: dict[str, dict[str, str]] = {
    "midnight": dict(
        STATUS_OK="#88ff88", STATUS_VIP="#ff8844", STATUS_MUTED="#8484ac",
        BG="#0d0d1a", TOOLBAR="#08080f", PANEL="#111128", PANEL_ALT="#0f0f22", PANEL2="#1c1c36", BTN_ACTIVE="#2e2e50",
        ENTRY="#16162a", TITLEBAR="#151f3a", BORDER="#2a2a44", WINDOW_BORDER="#6a6a72",
        FG="#f0f0f6", FG_BTN="#dcdcf4", MUTED="#8484ac", LABEL="#a4a4d2", HEAD="#bcbcff", TITLE_FG="#a0a0e0",
        ACCENT="#88ccff", YELLOW="#ffdd44", ORANGE="#ff8844", RED="#ff6666", RED_BG="#3a1a1a", GREEN="#88ff88",
        GREEN_BG="#1a3a1a", SELECT="#2a3a5a", SELECT_FG="#ffffff", LOG_FG="#b8b8dc", MEMBER_BG="#141a33",
        TOOLBAR_BTN="#14142a", STRIP_BTN="#1d2a4d", STRIP_BTN_ACTIVE="#26386a", ACCENT_ACTIVE="#1e2e55",
        LAUNCH_ACTIVE="#245024", DANGER_ACTIVE="#4a2a2a", DISABLED_FG="#5a5a88",
    ),
    "orange": dict(
        STATUS_OK="#0b4a18", STATUS_VIP="#5a1a00", STATUS_MUTED="#4a2a08",
        BG="#e9862a", TOOLBAR="#c86f18", PANEL="#f2973f", PANEL_ALT="#e98c33", PANEL2="#f7ad62", BTN_ACTIVE="#ffc27e",
        ENTRY="#fbd39f", TITLEBAR="#d47a1e", BORDER="#b56412", WINDOW_BORDER="#6a6a72",
        FG="#1e1000", FG_BTN="#2a1600", MUTED="#5a3410", LABEL="#3e2208", HEAD="#2a1200", TITLE_FG="#fff1dc",
        ACCENT="#3a1a00", YELLOW="#4a3a00", ORANGE="#6a2000", RED="#8a0c0c", RED_BG="#f3a9a9", GREEN="#0b5a1e",
        GREEN_BG="#b9e5b9", SELECT="#ffe2bd", SELECT_FG="#1e1000", LOG_FG="#fff1dc", MEMBER_BG="#f9b672",
        TOOLBAR_BTN="#e08a2a", STRIP_BTN="#f0a04a", STRIP_BTN_ACTIVE="#ffbb6e", ACCENT_ACTIVE="#f0a04a",
        LAUNCH_ACTIVE="#9fd69f", DANGER_ACTIVE="#f08a8a", DISABLED_FG="#9a6a3a",
    ),
    "gray": dict(
        STATUS_OK="#b9dcb0", STATUS_VIP="#f2b27a", STATUS_MUTED="#a8a8a8",
        BG="#3a3a3a", TOOLBAR="#2c2c2c", PANEL="#454545", PANEL_ALT="#3f3f3f", PANEL2="#585858", BTN_ACTIVE="#6a6a6a",
        ENTRY="#505050", TITLEBAR="#525252", BORDER="#666666", WINDOW_BORDER="#6a6a72",
        FG="#f0f0f0", FG_BTN="#e8e8e8", MUTED="#b0b0b0", LABEL="#cccccc", HEAD="#ffffff", TITLE_FG="#e6e6e6",
        ACCENT="#9ad0ff", YELLOW="#ffe066", ORANGE="#ffb070", RED="#ff8a8a", RED_BG="#5a3030", GREEN="#8fe08f",
        GREEN_BG="#2f5a2f", SELECT="#707070", SELECT_FG="#ffffff", LOG_FG="#dcdcdc", MEMBER_BG="#4e4e58",
        TOOLBAR_BTN="#484848", STRIP_BTN="#666666", STRIP_BTN_ACTIVE="#7a7a7a", ACCENT_ACTIVE="#6a6a6a",
        LAUNCH_ACTIVE="#3f7a3f", DANGER_ACTIVE="#7a4040", DISABLED_FG="#8a8a8a",
    ),
    "green": dict(
        STATUS_OK="#9dff9d", STATUS_VIP="#ffb070", STATUS_MUTED="#8ab89a",
        BG="#0f2a18", TOOLBAR="#0a1e11", PANEL="#143520", PANEL_ALT="#11301c", PANEL2="#1e4a2e", BTN_ACTIVE="#2a6a40",
        ENTRY="#183f26", TITLEBAR="#1a4a2c", BORDER="#2a5a3a", WINDOW_BORDER="#6a6a72",
        FG="#eaf6ec", FG_BTN="#d8f0dc", MUTED="#8ab89a", LABEL="#a8d0b4", HEAD="#c8ffd8", TITLE_FG="#b8f0c8",
        ACCENT="#8fe0a8", YELLOW="#ffe066", ORANGE="#ffb070", RED="#ff8a8a", RED_BG="#4a2a2a", GREEN="#9dff9d",
        GREEN_BG="#245a34", SELECT="#2e6a44", SELECT_FG="#ffffff", LOG_FG="#c8e8d0", MEMBER_BG="#1a3f28",
        TOOLBAR_BTN="#173a24", STRIP_BTN="#246a3c", STRIP_BTN_ACTIVE="#2e8a4e", ACCENT_ACTIVE="#246a3c",
        LAUNCH_ACTIVE="#2f7a44", DANGER_ACTIVE="#6a3a3a", DISABLED_FG="#5a8a68",
    ),
    "red": dict(
        STATUS_OK="#9dff9d", STATUS_VIP="#ffb070", STATUS_MUTED="#b88a92",
        BG="#2a0f12", TOOLBAR="#1e0a0c", PANEL="#351418", PANEL_ALT="#30111a", PANEL2="#4a1e24", BTN_ACTIVE="#6a2a34",
        ENTRY="#3f181e", TITLEBAR="#4a1a22", BORDER="#5a2a32", WINDOW_BORDER="#6a6a72",
        FG="#f6eaec", FG_BTN="#f0d8dc", MUTED="#b88a92", LABEL="#d0a8b0", HEAD="#ffc8d0", TITLE_FG="#f0b8c0",
        ACCENT="#ff9fb0", YELLOW="#ffe066", ORANGE="#ffb070", RED="#ff8a8a", RED_BG="#5a2a2a", GREEN="#9dff9d",
        GREEN_BG="#2a4a2a", SELECT="#6a2e3a", SELECT_FG="#ffffff", LOG_FG="#e8c8d0", MEMBER_BG="#3f1a24",
        TOOLBAR_BTN="#3a1720", STRIP_BTN="#6a2434", STRIP_BTN_ACTIVE="#8a2e44", ACCENT_ACTIVE="#6a2434",
        LAUNCH_ACTIVE="#3f6a3f", DANGER_ACTIVE="#7a3a3a", DISABLED_FG="#8a5a62",
    ),
    "white (psycho)": dict(
        STATUS_OK="#1d6f35", STATUS_VIP="#b35a00", STATUS_MUTED="#6a6a6a",
        BG="#ffffff", TOOLBAR="#efefef", PANEL="#fafafa", PANEL_ALT="#f1f1f1", PANEL2="#e4e4e4", BTN_ACTIVE="#d2d2d2",
        ENTRY="#f3f3f3", TITLEBAR="#dfe5f0", BORDER="#cfcfcf", WINDOW_BORDER="#6a6a72",
        FG="#101010", FG_BTN="#202020", MUTED="#707070", LABEL="#404040", HEAD="#1a2a6a", TITLE_FG="#2a3a7a",
        ACCENT="#0050b0", YELLOW="#8a6a00", ORANGE="#c05000", RED="#c00000", RED_BG="#ffd6d6", GREEN="#0a7a2a",
        GREEN_BG="#d6f5d6", SELECT="#cfe0ff", SELECT_FG="#000000", LOG_FG="#303030", MEMBER_BG="#eef2ff",
        TOOLBAR_BTN="#e2e2e2", STRIP_BTN="#c9d4e8", STRIP_BTN_ACTIVE="#b8c6e0", ACCENT_ACTIVE="#c9d4e8",
        LAUNCH_ACTIVE="#b8ebb8", DANGER_ACTIVE="#ffb8b8", DISABLED_FG="#a0a0a0",
    ),
}
THEME_NAMES = list(PALETTES)
DEFAULT_THEME = "midnight"
current_theme = DEFAULT_THEME


def set_palette(name: str) -> str:
    """Rebind the colour globals to a palette. Unknown names fall back to the default. Returns the name used."""
    global current_theme
    name = name if name in PALETTES else DEFAULT_THEME
    globals().update(PALETTES[name])
    current_theme = name
    return name


set_palette(DEFAULT_THEME)

BRAND_FAMILIES = ("Cascadia Code", "Cascadia Mono", "JetBrains Mono", "Fira Code", "Source Code Pro", "Consolas",
                  "Lucida Console", "Courier New")


def brand_family(root: tk.Misc) -> str:
    import tkinter.font as tkfont
    installed = set(tkfont.families(root))
    return next((f for f in BRAND_FAMILIES if f in installed), "Courier")


def apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)
    root.option_add("*Font", FONT)
    style.configure(".", background=BG, foreground=FG, font=FONT, borderwidth=0, focuscolor=BG,
                    bordercolor=BG, lightcolor=BG, darkcolor=BG, troughcolor=PANEL_ALT)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Toolbar.TFrame", background=TOOLBAR)
    style.configure("Titlebar.TFrame", background=TITLEBAR)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Panel.TLabel", background=PANEL, foreground=FG)
    style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=FONT_SMALL)
    style.configure("Toolbar.TLabel", background=TOOLBAR, foreground=MUTED, font=FONT_SMALL)
    style.configure("Brand.TLabel", background=TOOLBAR, foreground=HEAD, font=(brand_family(root), 17, "bold"))
    style.configure("Titlebar.TLabel", background=TITLEBAR, foreground=TITLE_FG, font=FONT_BOLD)
    style.configure("Head.TLabel", background=PANEL, foreground=HEAD, font=FONT_BOLD)
    style.configure("Field.TLabel", background=PANEL, foreground=LABEL, font=FONT_BOLD)
    style.configure("Ok.TLabel", background=PANEL, foreground=GREEN, font=FONT_BOLD)
    style.configure("Err.TLabel", background=PANEL, foreground=RED, font=FONT_SMALL)

    def button(name, bg, fg, active=BTN_ACTIVE, font=FONT, padding=(10, 3)):
        style.configure(name, background=bg, foreground=fg, font=font, padding=padding, relief="flat",
                        borderwidth=0, bordercolor=bg, lightcolor=bg, darkcolor=bg, focuscolor=bg)
        style.map(name, background=[("active", active), ("disabled", PANEL_ALT)],
                  foreground=[("disabled", DISABLED_FG)])

    button("TButton", PANEL2, FG_BTN)
    button("Toolbar.TButton", TOOLBAR_BTN, FG_BTN, padding=(10, 3, 10, 5))
    button("Accent.TButton", TITLEBAR, HEAD, active=ACCENT_ACTIVE, font=FONT_BOLD)
    button("Launch.TButton", GREEN_BG, GREEN, active=LAUNCH_ACTIVE, font=FONT_BIG, padding=(14, 5))
    button("Danger.TButton", RED_BG, RED, active=DANGER_ACTIVE)
    button("DangerBig.TButton", RED_BG, RED, active=DANGER_ACTIVE, font=FONT_BIG, padding=(14, 5))
    button("Small.TButton", PANEL2, FG_BTN, font=FONT_SMALL, padding=(6, 1))
    button("Strip.TButton", STRIP_BTN, TITLE_FG, active=STRIP_BTN_ACTIVE, font=FONT_SMALL, padding=(8, 1))
    # the search box arrow: same surface as the entry so the two read as one control, a bigger glyph
    button("Arrow.TButton", ENTRY, FG, active=BTN_ACTIVE, font=(UI_FAMILY, 11), padding=(12, 0))

    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=24, font=FONT,
                    borderwidth=0, relief="flat")
    style.configure("Treeview.Heading", background=PANEL_ALT, foreground=LABEL, font=FONT_SMALL_BOLD,
                    relief="flat", padding=(6, 4), borderwidth=0)
    style.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", SELECT_FG)])
    style.map("Treeview.Heading", background=[("active", PANEL2)])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("TSpinbox", fieldbackground=ENTRY, background=PANEL2, foreground=ACCENT, arrowcolor=FG_BTN,
                    insertcolor=ACCENT, bordercolor=ENTRY, lightcolor=ENTRY, darkcolor=ENTRY, padding=2)
    style.configure("TEntry", fieldbackground=ENTRY, foreground=ACCENT, insertcolor=ACCENT, bordercolor=ENTRY,
                    lightcolor=ENTRY, darkcolor=ENTRY, padding=3)
    style.configure("Search.TEntry", fieldbackground=ENTRY, foreground=FG, insertcolor=ACCENT, bordercolor=ENTRY,
                    lightcolor=ENTRY, darkcolor=ENTRY, padding=(8, 5))
    style.configure("TCombobox", fieldbackground=ENTRY, background=PANEL2, foreground=ACCENT, arrowcolor=FG_BTN,
                    bordercolor=ENTRY, lightcolor=ENTRY, darkcolor=ENTRY, insertcolor=ACCENT, padding=3,
                    selectbackground=ENTRY, selectforeground=ACCENT)
    style.map("TCombobox", fieldbackground=[("readonly", ENTRY), ("disabled", PANEL_ALT)],
              foreground=[("readonly", ACCENT), ("disabled", MUTED)], background=[("active", BTN_ACTIVE)],
              selectbackground=[("readonly", ENTRY)], selectforeground=[("readonly", ACCENT)])
    root.option_add("*TCombobox*Listbox.background", PANEL2)
    root.option_add("*TCombobox*Listbox.foreground", FG_BTN)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT)
    root.option_add("*TCombobox*Listbox.selectForeground", SELECT_FG)
    root.option_add("*TCombobox*Listbox.font", FONT)
    style.configure("TCheckbutton", background=PANEL, foreground=LABEL, indicatorbackground=PANEL2,
                    indicatorforeground=GREEN, focuscolor=PANEL)
    style.map("TCheckbutton", background=[("active", PANEL)], indicatorbackground=[("selected", PANEL2)],
              foreground=[("disabled", MUTED)])
    style.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=PANEL, arrowcolor=FG_BTN,
                    bordercolor=PANEL, lightcolor=PANEL2, darkcolor=PANEL2, relief="flat", arrowsize=12)
    style.map("Vertical.TScrollbar", background=[("active", BTN_ACTIVE)])
    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=6, sashrelief="flat", background=BG)
    style.configure("Status.TFrame", background=TOOLBAR)
    style.configure("Status.TLabel", background=TOOLBAR, foreground=STATUS_MUTED, font=FONT_SMALL)
    style.configure("StatusOn.TLabel", background=TOOLBAR, foreground=STATUS_OK, font=FONT_SMALL_BOLD)
    style.configure("StatusWarn.TLabel", background=TOOLBAR, foreground=YELLOW, font=FONT_SMALL_BOLD)
    style.configure("StatusVip.TLabel", background=TOOLBAR, foreground=STATUS_VIP, font=FONT_SMALL_BOLD)
    style.configure("StatusErr.TLabel", background=TOOLBAR, foreground=RED, font=FONT_SMALL_BOLD)
    style.configure("StatusMsg.TLabel", background=TOOLBAR, foreground=FG_BTN, font=FONT_SMALL)
    style.configure("StatusSep.TLabel", background=TOOLBAR, foreground=BORDER, font=FONT_SMALL)


def titled_panel(parent, title: str) -> tuple[tk.Frame, ttk.Frame, ttk.Frame]:
    """A flat card: title strip in TITLEBAR, body in PANEL, no outline."""
    outer = tk.Frame(parent, bg=PANEL, highlightthickness=0)
    strip = ttk.Frame(outer, style="Titlebar.TFrame")
    strip.pack(fill="x")
    ttk.Label(strip, text=title, style="Titlebar.TLabel", padding=(10, 4)).pack(side="left")
    body = ttk.Frame(outer, style="Panel.TFrame")
    body.pack(fill="both", expand=True)
    return outer, strip, body


def virtual_screen(widget: tk.Misc) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the whole desktop across all monitors (Tk's screenwidth is the primary only)."""
    try:
        import ctypes
        u = ctypes.windll.user32
        return u.GetSystemMetrics(76), u.GetSystemMetrics(77), u.GetSystemMetrics(78), u.GetSystemMetrics(79)
    except Exception:  # noqa: BLE001
        return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


def center_over(win: tk.Toplevel, parent: tk.Misc) -> None:
    """Centre a dialog over its parent, on whichever monitor the parent is on."""
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    vx, vy, vw, vh = virtual_screen(win)
    x = max(vx, min(x, vx + vw - w))
    y = max(vy, min(y, vy + vh - h))
    win.geometry(f"+{x}+{y}")


class PopupMenu(tk.Toplevel):
    """A borderless drop-down drawn by us (Tk's own menus get a thick native frame on Windows).

    items:  (label, callback) tuples, or None for a separator.
    anchor: callable returning the (x, y) screen position to hang from; re-evaluated whenever the owning
            window moves or resizes, so the popup travels with it. Minimising the owner closes it.
    key:    one popup per key; popup_menu() toggles it.
    ignore: widgets a click on which does NOT close the popup (the button that opened it, drag handles).
    The popup never takes keyboard focus. It closes on pick, Escape, a click anywhere else, minimise, or
    after IDLE_MS without the pointer over it."""

    IDLE_MS = 2000

    _open: dict[object, "PopupMenu"] = {}
    _owners: set[str] = set()
    _global_installed = False

    def __init__(self, parent: tk.Misc, items, anchor, min_width: int = 200, key: object = None, ignore=()) -> None:
        super().__init__(parent)
        self.key = key
        self.anchor = anchor
        self.ignore = tuple(ignore)
        self.owner = parent.winfo_toplevel()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=PANEL2)
        for item in items:
            if item is None:
                tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=6, pady=3)
                continue
            label, callback = item
            row = tk.Label(self, text=label, bg=PANEL2, fg=FG_BTN, font=FONT, anchor="w", padx=14, pady=5)
            row.pack(fill="x")
            row.bind("<Enter>", lambda e, r=row: r.configure(bg=BTN_ACTIVE, fg=SELECT_FG))
            row.bind("<Leave>", lambda e, r=row: r.configure(bg=PANEL2, fg=FG_BTN))
            row.bind("<ButtonRelease-1>", lambda e, cb=callback: self._pick(cb))
        self.update_idletasks()
        self._pw = max(min_width, self.winfo_reqwidth())
        self._ph = self.winfo_reqheight()
        self.place_at_anchor()
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.bind("<Motion>", lambda e: self._touch(), add="+")
        self.bind("<Enter>", lambda e: self._touch(), add="+")
        self._idle_job = self.after(self.IDLE_MS, self._idle_check)
        if key is not None:
            old = PopupMenu._open.get(key)
            if old is not None and old is not self and old.winfo_exists():
                old.destroy()
            PopupMenu._open[key] = self
        PopupMenu._install(self.owner)

    @classmethod
    def _install(cls, owner: tk.Misc) -> None:
        path = str(owner)
        if path not in cls._owners:
            cls._owners.add(path)
            owner.bind("<Configure>", lambda e: cls._owner_moved(owner) if e.widget is owner else None, add="+")
            owner.bind("<Unmap>", lambda e: cls._close_for(owner) if e.widget is owner else None, add="+")
            owner.bind("<Key-Escape>", lambda e: cls._close_for(owner), add="+")
        if not cls._global_installed:
            cls._global_installed = True
            owner.bind_all("<ButtonPress-1>", cls._clicked, add="+")

    @classmethod
    def _live(cls) -> list["PopupMenu"]:
        return [p for p in list(cls._open.values()) if p.winfo_exists()]

    @classmethod
    def _owner_moved(cls, owner) -> None:
        for p in cls._live():
            if p.owner is owner:
                p.place_at_anchor()

    @classmethod
    def _close_for(cls, owner) -> None:
        for p in cls._live():
            if p.owner is owner:
                p.destroy()

    @classmethod
    def close_all(cls) -> None:
        for p in cls._live():
            p.destroy()

    @classmethod
    def _clicked(cls, event) -> None:
        w = event.widget
        if not isinstance(w, tk.Misc):
            return
        for p in cls._live():
            try:
                if w.winfo_toplevel() is p or any(w is i for i in p.ignore):
                    continue
            except tk.TclError:
                continue
            p.destroy()

    def _touch(self) -> None:
        """Pointer activity over the popup: restart the idle timer."""
        if self._idle_job:
            self.after_cancel(self._idle_job)
        self._idle_job = self.after(self.IDLE_MS, self._idle_check)

    def _pointer_inside(self) -> bool:
        try:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
            return self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width() and \
                self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height()
        except tk.TclError:
            return False

    def _idle_check(self) -> None:
        self._idle_job = None
        if not self.winfo_exists():
            return
        if self._pointer_inside():
            self._idle_job = self.after(self.IDLE_MS, self._idle_check)
        else:
            self.destroy()

    def place_at_anchor(self) -> None:
        if not self.winfo_exists():
            return
        try:
            x, y = self.anchor()
        except tk.TclError:
            return
        vx, vy, vw, vh = virtual_screen(self)
        x = max(vx, min(int(x), vx + vw - self._pw))
        y = max(vy, min(int(y), vy + vh - self._ph))
        self.geometry(f"{self._pw}x{self._ph}+{x}+{y}")

    def _on_destroy(self, event) -> None:
        if event.widget is self and self.key is not None and PopupMenu._open.get(self.key) is self:
            del PopupMenu._open[self.key]

    def _pick(self, callback) -> None:
        self.destroy()
        callback()


def popup_menu(parent: tk.Misc, items, anchor, key: object, min_width: int = 200, ignore=()) -> PopupMenu | None:
    """Open a PopupMenu for key, or close the one already open for it (toggle). Returns the new popup or None."""
    existing = PopupMenu._open.get(key)
    if existing is not None:
        alive = existing.winfo_exists()
        try:
            existing.destroy()
        except tk.TclError:
            pass
        PopupMenu._open.pop(key, None)
        if alive:
            return None
    return PopupMenu(parent, items, anchor, min_width=min_width, key=key, ignore=ignore)


class Tooltip:
    """Hover text for a widget. text may be a callable returning the text (empty -> no tooltip)."""

    def __init__(self, widget: tk.Misc, text, delay: int = 350) -> None:
        self.widget, self.text, self.delay = widget, text, delay
        self._job = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None) -> None:
        self._cancel()
        self._job = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _show(self) -> None:
        text = self.text() if callable(self.text) else self.text
        if not text or self._tip:
            return
        tip = self._tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.configure(bg=BORDER)
        tk.Label(tip, text=text, bg=PANEL2, fg=FG, font=FONT_SMALL, justify="left", padx=8, pady=5).pack(padx=1, pady=1)
        tip.geometry(f"+{self.widget.winfo_rootx() + 12}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 4}")

    def _hide(self, _e=None) -> None:
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None
