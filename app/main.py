"""wauncher main window (Tk, frameless like woxo)."""
from __future__ import annotations

import copy
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import traceback
import uuid
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import APP_TITLE, REPO_URL, VERSION
from . import client as cl
from . import esi
from . import launcher_state as ls
from . import policy, profiles, sso, status as srv
from . import theme as T

try:  # imported here, before any window exists: loading them later would stall the visible UI
    import pystray
    from PIL import Image as _PILImage
except ImportError:  # pragma: no cover
    pystray = None
    _PILImage = None
from .frameless import Frameless
from .storage import Config, Data, Launched, TokenStore, backups_dir, bundle_dir, data_dir
from .theme import FONT, FONT_BOLD, FONT_SMALL, PopupMenu, Tooltip, apply_theme, brand_family, center_over, popup_menu, titled_panel

MIN_W, MIN_H = 760, 560


def open_url(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass


# ====================================================================== small dialogs
class TextPrompt(tk.Toplevel):
    """A one-line text prompt in the app's colours. .result is None when cancelled."""

    def __init__(self, parent: tk.Misc, title: str, label: str, initial: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=T.PANEL)
        self.transient(parent)
        self.resizable(False, False)
        self.result: str | None = None
        ttk.Label(self, text=label, style="Panel.TLabel").pack(anchor="w", padx=14, pady=(12, 4))
        self.var = tk.StringVar(value=initial)
        entry = ttk.Entry(self, textvariable=self.var, width=40)
        entry.pack(padx=14, pady=(0, 10), fill="x")
        row = ttk.Frame(self, style="Panel.TFrame")
        row.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(row, text="OK", style="Accent.TButton", command=self._ok).pack(side="right")
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 8))
        entry.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        center_over(self, parent)
        entry.focus_set()
        entry.select_range(0, "end")
        self.grab_set()
        self.wait_window()

    def _ok(self) -> None:
        text = self.var.get().strip()
        if text:
            self.result = text
        self.destroy()


class ConfirmDialog(tk.Toplevel):
    """A themed yes/no with custom button labels. .result is True when the first button was chosen."""

    def __init__(self, parent: tk.Misc, title: str, headline: str, details: str, note: str,
                 ok_label: str, cancel_label: str = "Cancel") -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=T.PANEL)
        self.transient(parent)
        self.resizable(False, False)
        self.result = False
        ttk.Label(self, text=headline, style="Head.TLabel").pack(anchor="w", padx=16, pady=(14, 4))
        if details:
            tk.Label(self, text=details, bg=T.ENTRY, fg=T.FG, font=FONT_SMALL, justify="left", anchor="w",
                     padx=10, pady=6).pack(fill="x", padx=16, pady=(0, 8))
        ttk.Label(self, text=note, style="Panel.TLabel", wraplength=440, justify="left").pack(anchor="w", padx=16, pady=(0, 12))
        row = ttk.Frame(self, style="Panel.TFrame")
        row.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(row, text=ok_label, style="Danger.TButton", command=self._ok).pack(side="right")
        ttk.Button(row, text=cancel_label, command=self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._ok())
        center_over(self, parent)
        self.grab_set()
        self.focus_set()
        self.wait_window()

    def _ok(self) -> None:
        self.result = True
        self.destroy()


# ====================================================================== search box
class SearchBox(ttk.Frame):
    """Entry with type-ahead (characters, accounts, groups) and a drop-down arrow that lists the groups
    alphabetically. on_pick(kind, key, label) with kind in {"character", "account", "group", "running"}."""

    MAX_ROWS = 14

    def __init__(self, master, on_pick, items_provider, groups_provider) -> None:
        super().__init__(master, style="Panel.TFrame")
        self.on_pick = on_pick
        self.items_provider = items_provider
        self.groups_provider = groups_provider
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, style="Search.TEntry", font=FONT_BOLD)
        self.entry.pack(side="left", fill="x", expand=True)
        # joined to the entry: no gap, same colour, stretched to the entry's height
        self.arrow = ttk.Button(self, text="▼", width=2, style="Arrow.TButton", command=self._toggle_groups)
        self.arrow.pack(side="left", fill="y")
        self._popup: tk.Toplevel | None = None
        self._list: tk.Listbox | None = None
        self._rows: list[tuple[str, str, object]] = []
        self._showing_groups = False
        self.entry.bind("<KeyRelease>", self._typed)
        self.entry.bind("<Down>", lambda e: self._move(1))
        self.entry.bind("<Up>", lambda e: self._move(-1))
        self.entry.bind("<Return>", lambda e: self._accept())
        self.entry.bind("<Escape>", lambda e: (self._close(), self.var.set("")))
        self.entry.bind("<FocusOut>", self._focus_out)
        self.entry.bind("<Button-1>", lambda e: self.after(10, self._typed))
        top = self.winfo_toplevel()
        top.bind("<Configure>", lambda e: self._place() if e.widget is top else None, add="+")
        top.bind("<Unmap>", lambda e: self._close() if e.widget is top else None, add="+")

    def _place(self) -> None:
        if self._popup is None or self._list is None:
            return
        try:
            x, y = self.entry.winfo_rootx(), self.entry.winfo_rooty() + self.entry.winfo_height() + 2
            self._popup.geometry(f"{self.winfo_width()}x{self._list.winfo_reqheight() + 2}+{x}+{y}")
        except tk.TclError:
            pass

    def _open(self, rows: list[tuple[str, str, object]]) -> None:
        self._rows = rows
        if not rows:
            self._close()
            return
        if self._popup is None:
            self._popup = tk.Toplevel(self)
            self._popup.overrideredirect(True)
            self._popup.attributes("-topmost", True)
            self._popup.configure(bg=T.BORDER)
            self._list = tk.Listbox(self._popup, bg=T.PANEL2, fg=T.FG_BTN, selectbackground=T.SELECT,
                                    selectforeground=T.SELECT_FG, font=FONT, relief="flat", activestyle="none",
                                    highlightthickness=0, borderwidth=0)
            self._list.pack(fill="both", expand=True, padx=1, pady=1)
            self._list.bind("<ButtonRelease-1>", lambda e: self._accept())
            self._list.bind("<Motion>", self._hover)
        self._list.delete(0, "end")
        for label, kind, _key in rows:
            self._list.insert("end", f"{kind}: {label}")
        self._list.configure(height=min(len(rows), self.MAX_ROWS))
        self._list.selection_set(0)
        self.update_idletasks()
        self._place()
        self._popup.deiconify()
        self._popup.lift()

    def _close(self) -> None:
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
            self._list = None
        self._rows = []
        self._showing_groups = False

    def _hover(self, event) -> None:
        if self._list is None:
            return
        idx = self._list.nearest(event.y)
        self._list.selection_clear(0, "end")
        self._list.selection_set(idx)

    def _move(self, delta: int) -> str:
        if self._list is None:
            self._typed()
            return "break"
        cur = self._list.curselection()
        idx = max(0, min((cur[0] if cur else -1) + delta, self._list.size() - 1))
        self._list.selection_clear(0, "end")
        self._list.selection_set(idx)
        self._list.see(idx)
        return "break"

    def _accept(self) -> str:
        if self._list is None or not self._rows:
            return "break"
        cur = self._list.curselection()
        if not cur:
            return "break"
        label, kind, key = self._rows[cur[0]]
        self._close()
        self.var.set(label)
        self.entry.icursor("end")
        self.on_pick(kind, key, label)
        return "break"

    def _focus_out(self, _e=None) -> None:
        self.after(150, self._maybe_close)

    def _maybe_close(self) -> None:
        try:
            focused = self.focus_get()
        except (KeyError, tk.TclError):
            focused = None
        if focused is not self.entry and focused is not self._list:
            self._close()

    def _typed(self, event=None) -> None:
        if event is not None and event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        text = self.var.get().strip().lower()
        if not text:
            self._close()
            return
        starts, contains = [], []
        for label, kind, key in self.items_provider():
            low = label.lower()
            if low.startswith(text):
                starts.append((label, kind, key))
            elif text in low:
                contains.append((label, kind, key))
        self._showing_groups = False
        self._open((starts + contains)[:60])

    def _toggle_groups(self) -> None:
        if self._popup is not None and self._showing_groups:
            self._close()
            return
        self.entry.focus_set()
        self._open(self.groups_provider())
        self._showing_groups = True


# ====================================================================== info dialog
class InfoDialog(tk.Toplevel):
    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.title(f"{APP_TITLE} - Info")
        self.configure(bg=T.PANEL)
        self.transient(app)
        text = tk.Text(self, bg=T.PANEL, fg=T.FG, font=FONT, wrap="word", relief="flat", padx=16, pady=12,
                       highlightthickness=0, width=92, height=36, cursor="arrow", selectbackground=T.SELECT)
        vsb = ttk.Scrollbar(self, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=vsb.set)
        text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        text.tag_configure("h", foreground=T.HEAD, font=FONT_BOLD, spacing1=10, spacing3=4)
        text.tag_configure("p", spacing3=8)
        text.tag_configure("muted", foreground=T.MUTED, font=FONT_SMALL, spacing3=6)
        text.tag_configure("link", foreground=T.ACCENT, underline=True, spacing3=4)
        text.tag_bind("link", "<Enter>", lambda e: text.configure(cursor="hand2"))
        text.tag_bind("link", "<Leave>", lambda e: text.configure(cursor="arrow"))
        text.insert("end", f"{APP_TITLE} v{VERSION}\n", "h")
        text.insert("end", "Project: ", "muted")
        text.insert("end", REPO_URL + "\n", ("link", "repo"))
        text.tag_bind("repo", "<Button-1>", lambda e: open_url(REPO_URL))
        text.insert("end", policy.SUMMARY + "\n", "p")
        for heading, paragraphs in policy.SECTIONS:
            text.insert("end", heading + "\n", "h")
            for para in paragraphs:
                text.insert("end", para + "\n", "p")
        for i, (label, url) in enumerate(policy.SOURCES):
            tag = f"link{i}"
            text.insert("end", "• " + label + "\n", ("link", tag))
            text.tag_bind(tag, "<Button-1>", lambda e, u=url: open_url(u))
        text.insert("end", "\n" + policy.DISCLAIMER + "\n", "muted")
        text.insert("end", f"\nData folder: {data_dir()}\n", "muted")
        text.configure(state="disabled")
        self.bind("<Escape>", lambda e: self.destroy())
        center_over(self, app)


# ====================================================================== launch group editor
class GroupEditor(tk.Toplevel):
    """Create / copy / rename / delete launch groups and choose which accounts (and which character) belong
    to each. Works on a copy of the groups; Save writes them to data.json."""

    NONE_LABEL = "(login screen)"
    NO_PROFILE = "(defer to launcher, or Default)"

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.app = app
        self.title(f"{APP_TITLE} - Launch group editor")
        self.configure(bg=T.BG)
        self.transient(app)
        self.minsize(720, 460)
        self.groups: list[dict] = copy.deepcopy(app.data.groups)
        self.current: dict | None = None
        self._build()
        self._fill_groups()
        center_over(self, app)
        self.bind("<Escape>", lambda e: self.destroy())

    def _build(self) -> None:
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)
        left_outer, left_strip, left = titled_panel(paned, "Groups")
        paned.add(left_outer, weight=1)
        ttk.Button(left_strip, text="New", style="Strip.TButton", command=self._new).pack(side="right", padx=(2, 6), pady=3)
        ttk.Button(left_strip, text="Copy", style="Strip.TButton", command=self._copy).pack(side="right", padx=2, pady=3)
        ttk.Button(left_strip, text="Rename", style="Strip.TButton", command=self._rename).pack(side="right", padx=2, pady=3)
        ttk.Button(left_strip, text="Delete", style="Strip.TButton", command=self._delete).pack(side="right", padx=2, pady=3)
        clients_btn = ttk.Button(left_strip, text="From clients", style="Strip.TButton", command=self._from_clients)
        clients_btn.pack(side="right", padx=(2, 8), pady=3)
        Tooltip(clients_btn, "Save the currently running clients as a new launch group "
                             "(the logged-in character of each; login-screen clients join at the login screen).")
        self.listbox = tk.Listbox(left, bg=T.PANEL, fg=T.FG_BTN, selectbackground=T.SELECT, selectforeground=T.SELECT_FG,
                                  font=FONT, relief="flat", activestyle="none", highlightthickness=0, borderwidth=0,
                                  exportselection=False)
        self.listbox.pack(fill="both", expand=True, padx=6, pady=6)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._select_group())

        right_outer, right_strip, right = titled_panel(paned, "Members")
        paned.add(right_outer, weight=3)
        self.members_title = ttk.Label(right_strip, text="", style="Titlebar.TLabel", font=FONT_SMALL)
        self.members_title.pack(side="left", padx=(0, 8))
        ttk.Button(right_strip, text="None", style="Strip.TButton", command=lambda: self._set_all(False)).pack(side="right", padx=(2, 6), pady=3)
        ttk.Button(right_strip, text="All", style="Strip.TButton", command=lambda: self._set_all(True)).pack(side="right", padx=2, pady=3)
        self.profile_var = tk.StringVar(value=self.NO_PROFILE)
        self.profile_box = ttk.Combobox(right_strip, textvariable=self.profile_var, state="readonly", width=20,
                                        values=[self.NO_PROFILE] + profiles.list_profiles(self.app._shared_cache()))
        self.profile_box.pack(side="right", padx=(2, 10), pady=3)
        self.profile_box.bind("<<ComboboxSelected>>", lambda e: self._profile_changed())
        ttk.Label(right_strip, text="Settings profile", style="Titlebar.TLabel", font=FONT_SMALL).pack(side="right", padx=(8, 4))
        Tooltip(self.profile_box, "Client settings profile for this group: used when the group is launched here\n"
                                  "(unless the main window forces one) and written to the official launcher on copy.\n"
                                  "Deferring keeps whatever the official launcher has, and launches here with Default.")
        ttk.Label(right, text="Click the first column to add or remove an account (new members start at the login "
                  "screen); click the character column to choose which character auto-selects.", style="Muted.TLabel",
                  wraplength=520, justify="left").pack(anchor="w", padx=8, pady=(6, 4))
        self.tree = ttk.Treeview(right, columns=("in", "account", "character"), show="headings", selectmode="none")
        self.tree.heading("in", text="In group")
        self.tree.heading("account", text="Account", anchor="w")
        self.tree.heading("character", text="Character", anchor="w")
        self.tree.column("in", width=80, anchor="center", stretch=False)
        self.tree.column("account", width=180)
        self.tree.column("character", width=260)
        vsb = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        vsb.pack(side="right", fill="y", pady=(0, 8), padx=(0, 8))
        self.tree.tag_configure("in", foreground=T.GREEN)
        self.tree.tag_configure("out", foreground=T.MUTED)
        self.tree.bind("<Button-1>", self._tree_click)

        row = ttk.Frame(self)
        row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(row, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 8))
        b1 = ttk.Button(row, text="Copy this group to EVE launcher", command=lambda: self._copy_to_launcher(False))
        b1.pack(side="left")
        b2 = ttk.Button(row, text="Copy all groups to EVE launcher", command=lambda: self._copy_to_launcher(True))
        b2.pack(side="left", padx=(6, 0))
        Tooltip(b1, "Writes the selected group into the official launcher's launch groups (adds or updates it).\n"
                    "The launcher must be closed; you will be asked.")
        Tooltip(b2, "Writes every group here into the official launcher (adds or updates; launcher groups that\n"
                    "do not exist here are left alone). The launcher must be closed; you will be asked.")

    def _sorted_groups(self) -> list[dict]:
        return sorted(self.groups, key=lambda g: g["name"].lower())

    def _fill_groups(self, select: dict | None = None) -> None:
        self.listbox.delete(0, "end")
        for g in self._sorted_groups():
            self.listbox.insert("end", f"{g['name']}   ({len(g.get('members', []))})")
        if self.groups:
            target = select or self.current or self._sorted_groups()[0]
            idx = self._sorted_groups().index(target) if target in self.groups else 0
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(idx)
            self.listbox.see(idx)
        self._select_group()

    def _select_group(self) -> None:
        sel = self.listbox.curselection()
        self.current = self._sorted_groups()[sel[0]] if sel and self.groups else None
        self.profile_var.set((self.current or {}).get("profile") or self.NO_PROFILE)
        self.profile_box.configure(state="readonly" if self.current else "disabled")
        self._fill_members()

    def _profile_changed(self) -> None:
        if not self.current:
            return
        value = self.profile_var.get()
        self.current["profile"] = "" if value == self.NO_PROFILE else value

    def _new(self) -> None:
        name = TextPrompt(self, "New launch group", "Name of the new group:").result
        if not name:
            return
        g = {"groupId": f"local-{uuid.uuid4()}", "name": name, "local": True, "members": []}
        self.groups.append(g)
        self._fill_groups(select=g)

    def _copy(self) -> None:
        if not self.current:
            return
        name = TextPrompt(self, "Copy launch group", "Name of the copy:", f"{self.current['name']} copy").result
        if not name:
            return
        g = {"groupId": f"local-{uuid.uuid4()}", "name": name, "local": True,
             "members": copy.deepcopy(self.current.get("members", []))}
        self.groups.append(g)
        self._fill_groups(select=g)

    def _from_clients(self) -> None:
        """New group from whatever is running right now: one member per account with a client."""
        self.app.refresh_running_now()
        members = []
        for acc in self.app._ordered_accounts(all_accounts=True):
            runs = self.app._running_for_account(acc)
            if not runs:
                continue
            r = next((x for x in runs if x.character_name), runs[0])
            members.append({"userId": int(acc["userId"]), "characterId": self.app._client_character_id(r, acc)})
        if not members:
            messagebox.showinfo(APP_TITLE, "No EVE clients are running.", parent=self)
            return
        name = TextPrompt(self, "Save current clients as launch group", f"Name for the {len(members)} running client(s):",
                          time.strftime("clients %Y-%m-%d %H:%M")).result
        if not name:
            return
        g = {"groupId": f"local-{uuid.uuid4()}", "name": name, "local": True, "members": members}
        self.groups.append(g)
        self._fill_groups(select=g)

    def _rename(self) -> None:
        if not self.current:
            return
        name = TextPrompt(self, "Rename launch group", "New name:", self.current["name"]).result
        if name:
            self.current["name"] = name
            self._fill_groups(select=self.current)

    def _delete(self) -> None:
        if not self.current:
            return
        if not messagebox.askyesno(APP_TITLE, f"Delete the launch group '{self.current['name']}'?", parent=self):
            return
        self.groups.remove(self.current)
        self.current = None
        self._fill_groups()

    def _member(self, user_id: int) -> dict | None:
        if not self.current:
            return None
        return next((m for m in self.current.get("members", []) if int(m["userId"]) == user_id), None)

    def _fill_members(self) -> None:
        self.tree.delete(*self.tree.get_children(""))
        if not self.current:
            self.members_title.configure(text="no group selected")
            return
        self.members_title.configure(text=self.current["name"])
        for acc in self.app._ordered_accounts(all_accounts=True):
            uid = int(acc["userId"])
            m = self._member(uid)
            char = ""
            if m:
                found = self.app.data.character(m["characterId"]) if m.get("characterId") else None
                char = found[1]["name"] if found else self.NONE_LABEL
            self.tree.insert("", "end", iid=f"u{uid}", values=("☑" if m else "☐", self.app.acc_name(acc), char),
                             tags=("in" if m else "out",))

    def _tree_click(self, event) -> str | None:
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid or not self.current:
            return None
        uid = int(iid[1:])
        acc = self.app.data.account(uid)
        if col == "#1":
            m = self._member(uid)
            if m:
                self.current["members"].remove(m)
            else:
                self.current["members"].append({"userId": uid, "characterId": None})
            self._fill_members()
            self._refresh_counts()
        elif col == "#3" and acc:
            items = [(ch["name"], (lambda c=ch["characterId"]: self._set_character(uid, c))) for ch in acc.get("characters", [])]
            items += [None, (self.NONE_LABEL, lambda: self._set_character(uid, None))]

            def anchor(iid=iid):
                box = self.tree.bbox(iid, "#3")
                if box:
                    return self.tree.winfo_rootx() + box[0], self.tree.winfo_rooty() + box[1] + box[3]
                return event.x_root, event.y_root
            popup_menu(self, items, anchor, key=("character", id(self)))
        return "break"

    def _set_character(self, uid: int, character_id: int | None) -> None:
        m = self._member(uid)
        if not m:
            self.current["members"].append({"userId": uid, "characterId": character_id})
        else:
            m["characterId"] = character_id
        self._fill_members()
        self._refresh_counts()

    def _set_all(self, on: bool) -> None:
        if not self.current:
            return
        if on:
            for acc in self.app.data.accounts:
                if not self._member(int(acc["userId"])):
                    self.current["members"].append({"userId": int(acc["userId"]), "characterId": None})
        else:
            self.current["members"] = []
        self._fill_members()
        self._refresh_counts()

    def _refresh_counts(self) -> None:
        sel = self.listbox.curselection()
        for i, g in enumerate(self._sorted_groups()):
            self.listbox.delete(i)
            self.listbox.insert(i, f"{g['name']}   ({len(g.get('members', []))})")
        if sel:
            self.listbox.selection_set(sel[0])

    def _persist(self) -> None:
        self.app.data.d["groups"] = self.groups
        self.app.data.save()
        self.app.groups_changed()

    def _save(self) -> None:
        self._persist()
        self.app.log(f"Launch groups saved ({len(self.groups)} groups).", "ok")
        self.destroy()

    # ---- copy to the official launcher
    def _copy_to_launcher(self, all_groups: bool) -> None:
        groups = self.groups if all_groups else ([self.current] if self.current else [])
        if not groups:
            return
        pids = ls.launcher_pids()
        if pids:
            dlg = ConfirmDialog(self, APP_TITLE, "The EVE launcher is running",
                                f"eve-online.exe   {len(pids)} process(es)",
                                "It keeps its launch groups in memory and would overwrite the copy when it exits, so it "
                                "has to be closed first.", "Close it, proceed")
            if not dlg.result:
                return
            n = ls.kill_launcher()
            self.app.log(f"Closed the EVE launcher ({n} processes).", "warn")
            time.sleep(1.0)
        # groups made here get a real UUID in the launcher; remembered so a later copy updates the same group
        for g in groups:
            if not g.get("launcherGroupId"):
                g["launcherGroupId"] = g["groupId"] if not g.get("local") else str(uuid.uuid4())
        self._persist()
        payload = [{"launcherGroupId": g["launcherGroupId"], "name": g["name"], "profile": g.get("profile") or "",
                    "members": [{"userId": m["userId"], "characterId": m.get("characterId")} for m in g.get("members", [])]}
                   for g in groups]
        try:
            added, updated, kept = ls.write_groups(payload, backups_dir())
        except Exception as exc:  # noqa: BLE001
            self.app.log(f"Copy to the EVE launcher failed: {exc}", "err")
            messagebox.showerror(APP_TITLE, f"Copy to the EVE launcher failed:\n{exc}", parent=self)
            return
        what = "all launch groups" if all_groups else f"launch group '{groups[0]['name']}'"
        self.app.log(f"Copied {what} to the EVE launcher: {added} added, {updated} updated. "
                     f"Its previous state.json was kept at {kept}.", "ok")


# ====================================================================== main window
class App(tk.Tk):
    REFRESH_MS = 3000

    def __init__(self, config: Config, data: Data, tokens: TokenStore, launched: Launched,
                 selftest: bool = False) -> None:
        super().__init__()
        self.config_ = config
        self.data = data
        self.tokens = tokens
        self.launched = launched
        self.selftest = selftest
        self._frameless_hook = None
        self.title(f"{APP_TITLE}  v{VERSION}")
        self._set_window_icon()
        # appear where we were last time right away; _frameless() only trims the invisible caption later
        w0, h0, x0, y0 = self._saved_geometry()
        self.geometry(f"{w0}x{h0}" + (f"+{x0}+{y0}" if x0 is not None else ""))
        self._revealed = False
        self._saved_pos = (x0, y0)
        self.withdraw()  # hidden until the whole UI is assembled and the frame is set up (see _reveal)
        self.minsize(MIN_W, MIN_H)
        T.set_palette(str(config.get("theme") or T.DEFAULT_THEME))
        apply_theme(self)
        self.events: "queue.Queue[tuple[str, dict]]" = queue.Queue()
        self.running: list[cl.RunningClient] = []
        self.server_status: dict = {}
        self._log_lines: list[tuple[str, str | None]] = []
        self._frameless_hook: Frameless | None = None
        self._geometry_ready = False
        self._launch_thread: threading.Thread | None = None
        self._status_job = None
        self._drag_iid: str | None = None
        self._drag_moved = False
        self._picked_group: str | None = None
        self._filter: set[int] | None = None
        self.opt_kill = tk.BooleanVar(value=bool(config.get("kill_conflicting")))
        self.opt_login = tk.BooleanVar(value=bool(config.get("login_screen")))
        self.opt_streamer = tk.BooleanVar(value=bool(config.get("streamer_mode")))
        self.profile_mode_var = tk.StringVar(value="")
        self.opt_tray = tk.BooleanVar(value=bool(config.get("exit_to_tray")))
        self.tray = None
        self.opt_delay = tk.IntVar(value=int(config.get("startup_delay") or 0))
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._frameless)
        self.after(200, self._drain_events)
        self.after(1500, self._reveal)  # safety net: never stay invisible if something above fails
        self.after(800, self._tick)
        self.after(1200, self._poll_status)
        self.after(600, self._start_tray)
        if selftest:
            self.after(3500, self._selftest_done)

    # ------------------------------------------------------------------ startup
    def _startup(self) -> None:
        self._started = True
        self.log(f"v{VERSION} started. Data: {data_dir()}", "sys")
        if self.tokens.load_error:
            self.log(f"Token store could not be read ({self.tokens.load_error}); import from the launcher again.", "warn")
        if not self.data.accounts:
            self.log("No accounts yet: importing from the official EVE launcher.", "sys")
            self.import_from_launcher(quiet=True)
        else:
            self.rebuild_tree()
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.data.d.get("imported_at", 0)))
            self.log(f"{len(self.data.accounts)} accounts, {len(self.data.groups)} groups, "
                     f"{len(self.tokens)} token sets (imported {when}).")
        self._refresh_profiles()

    def _selftest_done(self) -> None:
        print("SELFTEST OK: window built, accounts:", len(self.data.accounts), "groups:", len(self.data.groups),
              "tree rows:", len(self.tree.get_children("")), "profiles:", len(self.profile_box.cget("values")),
              "server:", self.status_server_var.get(), "theme:", T.current_theme,
              "tray:", bool(self.tray and self.tray.visible))
        self.quit_app()

    # ------------------------------------------------------------------ tray icon
    def _start_tray(self) -> None:
        """A notification-area icon that is always there: show / reset position / exit. pystray runs its own
        message loop in a thread, so every menu action is marshalled back onto the Tk thread."""
        ui = lambda fn: (lambda *_: self.events.put(("call", {"fn": fn})))  # noqa: E731

        if pystray is None or _PILImage is None:
            self.log("Tray icon unavailable (pystray / Pillow missing).", "warn")
            return

        def work() -> None:
            png = os.path.join(bundle_dir(), "assets", "icon.png")
            try:
                image = _PILImage.open(png).convert("RGBA")
            except OSError:
                image = _PILImage.new("RGBA", (64, 64), (136, 204, 255, 255))
            menu = pystray.Menu(
                pystray.MenuItem("Show wauncher", ui(self.show_window), default=True),
                pystray.MenuItem("Reset position", ui(self.reset_position)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit wauncher", ui(self.quit_app)),
            )
            self.tray = pystray.Icon(APP_TITLE, image, APP_TITLE, menu)
            self.tray.run()
        threading.Thread(target=work, daemon=True, name="tray").start()

    def show_window(self) -> None:
        try:
            if self.state() in ("withdrawn", "iconic"):
                self.deiconify()
            self.lift()
            cl.focus(self._hwnd())
            self.focus_force()
        except tk.TclError:
            pass

    def reset_position(self) -> None:
        """Back to the default size at the top-left of the primary monitor (for a window lost off-screen)."""
        self.show_window()
        if self.state() == "zoomed":
            self.state("normal")
        self.geometry("980x760+78+78")
        if self._frameless_hook is not None:
            self._converge(980, 760, "+78+78")
        self.config_.update(window_geometry="980x760+78+78", window_zoomed=False)
        self.log("Window position reset.", "sys")

    def quit_app(self) -> None:
        self._remember_geometry()
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:  # noqa: BLE001
                pass
            self.tray = None
        self.destroy()

    def _set_window_icon(self) -> None:
        ico = os.path.join(bundle_dir(), "assets", "icon.ico")
        png = os.path.join(bundle_dir(), "assets", "icon.png")
        try:
            if os.path.exists(ico):
                self.iconbitmap(default=ico)
            if os.path.exists(png):
                self._icon_photo = tk.PhotoImage(file=png)
                self.iconphoto(True, self._icon_photo)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ frameless window (woxo)
    def _hwnd(self) -> int:
        try:
            import ctypes
            return int(ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id())
        except Exception:  # noqa: BLE001
            return 0

    def _reveal(self) -> None:
        """Fill the tree, place the sash, lay everything out, then show the window in one step."""
        if self._revealed:
            return
        self._revealed = True
        try:
            if not getattr(self, "_started", False):
                self._startup()
            self._place_sash()
            self.update_idletasks()
        finally:
            self.deiconify()
            x, y = self._saved_pos
            if x is not None:
                self.geometry(f"+{x}+{y}")  # Windows may hand a freshly shown window its own spot; insist
            if self._frameless_hook is not None and getattr(self, "_want", None):
                want_w, want_h, pos = self._want
                req_w, req_h = self._converge(want_w, want_h, pos)
                self.minsize(max(MIN_W - 40, MIN_W - (want_w - req_w)), max(MIN_H - 40, MIN_H - (want_h - req_h)))
            self._place_sash()

    def _frameless(self) -> None:
        if os.name != "nt" or self._frameless_hook is not None:
            self._reveal()
            return
        try:
            self._frameless_hook = Frameless(self)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Could not remove the window frame: {exc}", "warn")
            self._reveal()
            return
        self.bind("<Configure>", lambda e: self._frameless_hook.refresh() if e.widget is self else None, add="+")
        self.bind("<Map>", lambda e: self._frameless_hook.refresh(force=True) if e.widget is self else None, add="+")
        self.bind("<Configure>", lambda e: self._schedule_remember() if e.widget is self else None, add="+")
        want_w, want_h, x, y = self._saved_geometry()
        pos = f"+{x}+{y}" if x is not None else ""
        self.geometry(f"{want_w}x{want_h}{pos}")
        self._want = (want_w, want_h, pos)
        self._reveal()
        if self.config_.get("window_zoomed", False):
            self.state("zoomed")
        self._geometry_ready = True

    def _converge(self, want_w: int, want_h: int, pos: str = "") -> tuple[int, int]:
        """Ask Tk for a size until the window's real outer size is want_w x want_h. Tk adds its idea of the
        (now invisible) frame to whatever geometry it is asked for, so the request has to be corrected by
        the measured difference. The frame is re-reclaimed before every measurement so the caption never
        counts. Returns the geometry actually requested."""
        req_w, req_h = want_w, want_h
        for _ in range(4):
            self.update_idletasks()
            self._frameless_hook.refresh(force=True)
            w, h = self._frameless_hook.window_size()
            if (w, h) == (want_w, want_h):
                break
            if abs(w - want_w) > 60 or abs(h - want_h) > 60:
                # not laid out yet (a fresh Tk reports a placeholder size): re-ask for the wanted size and stop
                req_w, req_h = want_w, want_h
                self.geometry(f"{req_w}x{req_h}{pos}")
                break
            req_w, req_h = req_w - (w - want_w), req_h - (h - want_h)
            self.geometry(f"{req_w}x{req_h}{pos}")
        return req_w, req_h

    def _saved_geometry(self) -> tuple[int, int, int | None, int | None]:
        w, h, x, y = 980, 760, None, None
        m = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", (self.config_.get("window_geometry") or "").strip())
        if m:
            w, h, x, y = (int(m.group(i)) for i in range(1, 5))
        if x is not None:
            vx, vy, vw, vh = T.virtual_screen(self)
            w, h = max(MIN_W, min(w, vw)), max(MIN_H, min(h, vh))
            x = max(vx, min(x, vx + vw - w))
            y = max(vy, min(y, vy + vh - h))
        return w, h, x, y

    def _schedule_remember(self) -> None:
        job = getattr(self, "_remember_job", None)
        if job:
            self.after_cancel(job)
        self._remember_job = self.after(1500, self._remember_geometry)

    def _remember_geometry(self) -> None:
        if not self._geometry_ready or self._frameless_hook is None:
            return
        zoomed = self.state() == "zoomed"
        changes: dict = {}
        if zoomed != bool(self.config_.get("window_zoomed", False)):
            changes["window_zoomed"] = zoomed
        if not zoomed and self.state() == "normal":
            w, h = self._frameless_hook.window_size()
            m = re.search(r"([+-]\d+)([+-]\d+)$", self.geometry())
            geom = f"{w}x{h}{m.group(1)}{m.group(2)}" if m else ""
            if geom and w >= MIN_W - 40 and h >= MIN_H - 40 and geom != self.config_.get("window_geometry"):
                changes["window_geometry"] = geom  # never remember a squeezed / half-built size
        if changes:
            self.config_.update(**changes)

    def _titlebar_press(self, event) -> str | None:
        if self._frameless_hook is None or self.state() == "zoomed":
            return None
        if event.y_root - self.winfo_rooty() < 4:
            self._frameless_hook.start_resize_top()
        else:
            self._frameless_hook.start_move()
        return "break"

    def _toggle_zoom(self, _event=None) -> None:
        self.state("normal" if self.state() == "zoomed" else "zoomed")

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        self.configure(bg=T.TOOLBAR)  # 2 px frame in the title / status bar colour
        # Windows draws its 1 px frame line on the left / right / bottom of a frameless window but the top
        # edge is ours (the caption was reclaimed), so draw the same hairline there
        self.top_edge = tk.Frame(self, bg=T.WINDOW_BORDER, height=1, highlightthickness=0)
        self.top_edge.pack(side="top", fill="x")
        body = self.body = tk.Frame(self, bg=T.BG, highlightthickness=0)
        body.pack(fill="both", expand=True, padx=2, pady=(1, 2))

        # title strip
        top = self.titlebar = ttk.Frame(body, style="Toolbar.TFrame", padding=(8, 4, 4, 4))
        top.pack(fill="x")
        brand = ttk.Label(top, text=APP_TITLE, style="Brand.TLabel", font=(brand_family(self), 17, "bold"))
        brand.pack(side="left", padx=(0, 16), pady=(0, 4))  # sits 2 px up and 2 px left of centred
        ttk.Button(top, text="✕", style="Toolbar.TButton", width=3, command=self._on_close).pack(side="right")
        ttk.Button(top, text="☐", style="Toolbar.TButton", width=3, command=self._toggle_zoom).pack(side="right", padx=2)
        ttk.Button(top, text="—", style="Toolbar.TButton", width=3, command=self.iconify).pack(side="right")
        ttk.Button(top, text="Info", style="Toolbar.TButton", command=self.show_info).pack(side="right", padx=(2, 16))
        self.tools_btn = ttk.Button(top, text="Tools ▾", style="Toolbar.TButton", command=self._show_tools)
        self.tools_btn.pack(side="right", padx=(2, 1))
        self.theme_btn = ttk.Button(top, text="Theme ▾", style="Toolbar.TButton", command=self._show_themes)
        self.theme_btn.pack(side="right", padx=(2, 1))
        self._drag_handles = (top, brand)
        for w in self._drag_handles:
            w.bind("<ButtonPress-1>", self._titlebar_press)
            w.bind("<Double-Button-1>", self._toggle_zoom)

        # status bar: clients + group on the left, version + TQ status on the right
        status = ttk.Frame(body, style="Status.TFrame", padding=(10, 5, 10, 5))
        status.pack(side="bottom", fill="x")
        self.status_clients_var = tk.StringVar(value="")
        ttk.Label(status, textvariable=self.status_clients_var, style="StatusOn.TLabel").pack(side="left")
        self.status_group_var = tk.StringVar(value="")
        ttk.Label(status, textvariable=self.status_group_var, style="Status.TLabel").pack(side="left", padx=(14, 0))
        self.status_server_var = tk.StringVar(value="TQ status…")
        self.status_server_lbl = ttk.Label(status, textvariable=self.status_server_var, style="Status.TLabel")
        self.status_server_lbl.pack(side="right")
        Tooltip(self.status_server_lbl, self._server_tooltip)
        ttk.Label(status, text="  |  ", style="StatusSep.TLabel").pack(side="right")
        ttk.Label(status, text=f"{APP_TITLE} v{VERSION}", style="Status.TLabel").pack(side="right")

        # main panel
        self.paned = ttk.Panedwindow(body, orient="vertical")
        self.paned.pack(fill="both", expand=True, padx=8, pady=(6, 6))
        main = ttk.Frame(self.paned, style="Panel.TFrame")
        self.paned.add(main, weight=4)

        self.search = SearchBox(main, self._search_picked, self._search_items, self._group_items)
        self.search.pack(fill="x", padx=8, pady=(8, 6))
        Tooltip(self.search.arrow, "Launch groups (alphabetical)")

        tree_box = ttk.Frame(main, style="Panel.TFrame")
        tree_box.pack(fill="both", expand=True, padx=8)
        cols = ("corp", "status", "launched")
        self.tree = ttk.Treeview(tree_box, columns=cols, show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="Character / account", anchor="w")
        self.tree.heading("corp", text="Corporation", anchor="w")
        self.tree.heading("status", text="Client", anchor="w")
        self.tree.heading("launched", text="Started", anchor="w")
        for col in ("#0",) + cols:  # four equal columns; equal stretch keeps them equal on resize
            self.tree.column(col, width=220, minwidth=80, stretch=True, anchor="w")
        vsb = ttk.Scrollbar(tree_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("account", foreground=T.HEAD, font=FONT_BOLD)
        self.tree.tag_configure("running", foreground=T.GREEN)
        self.tree.tag_configure("login", foreground=T.YELLOW)
        self.tree.tag_configure("member", background=T.MEMBER_BG)
        self.tree.bind("<ButtonPress-1>", self._tree_press)
        self.tree.bind("<B1-Motion>", self._tree_drag)
        self.tree.bind("<ButtonRelease-1>", self._tree_release)
        self.tree.bind("<Double-1>", self._tree_double)
        self.tree.bind("<Button-3>", self._tree_context)
        self.tree.bind("<Return>", lambda e: self.launch_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_launch_button())

        # options row
        opts = ttk.Frame(main, style="Panel.TFrame", padding=(8, 8, 8, 4))
        opts.pack(fill="x")
        self.kill_check = ttk.Checkbutton(opts, text="Kill conflicting clients", variable=self.opt_kill,
                                          command=self._save_options)
        self.kill_check.pack(side="left", padx=(0, 14))
        Tooltip(self.kill_check, self._conflict_text)
        ttk.Checkbutton(opts, text="Login screen", variable=self.opt_login,
                        command=self._save_options).pack(side="left", padx=(0, 14))
        self.profile_box = ttk.Combobox(opts, textvariable=self.profile_mode_var, state="readonly", width=40)
        self.profile_box.pack(side="left", padx=(0, 14))
        self.profile_box.bind("<<ComboboxSelected>>", lambda e: self._save_options())
        Tooltip(self.profile_box, lambda: "Settings profile for launched clients. Profiles found in\n"
                                          + (profiles.settings_dir(self._shared_cache()) or "(no settings folder found)"))
        ttk.Label(opts, text="Delay", style="Muted.TLabel").pack(side="left", padx=(6, 4))
        sp = ttk.Spinbox(opts, from_=0, to=120, width=4, textvariable=self.opt_delay, command=self._save_options)
        sp.pack(side="left")
        sp.bind("<FocusOut>", lambda e: self._save_options())
        Tooltip(sp, "Seconds between clients when launching several. 0 = the official launcher's setting.")
        ttk.Label(opts, text="s", style="Muted.TLabel").pack(side="left", padx=(3, 0))

        # actions row
        actions = ttk.Frame(main, style="Panel.TFrame", padding=(8, 4, 8, 8))
        actions.pack(fill="x")
        self.launch_btn = ttk.Button(actions, text="Launch", style="Launch.TButton", width=14, command=self.launch_selected)
        self.launch_btn.pack(side="right")
        self.close_btn = ttk.Button(actions, text="Close selected", style="DangerBig.TButton", width=14,
                                    command=self.close_selected_clients)
        self.close_btn.pack(side="right", padx=(0, 8))
        Tooltip(self.close_btn, "Close the running clients that belong to the selected accounts.")
        ttk.Button(actions, text="Deselect all", command=self.deselect_all).pack(side="left")
        self.show_all_btn = ttk.Button(actions, text="Show all", command=self.show_all, state="disabled")
        self.show_all_btn.pack(side="left", padx=(6, 12))
        self.selection_var = tk.StringVar(value="")
        self.selection_lbl = ttk.Label(actions, textvariable=self.selection_var, style="Muted.TLabel")
        self.selection_lbl.pack(side="left")
        Tooltip(self.selection_lbl, self._selection_text)

        # log
        bottom = ttk.Frame(self.paned)
        self.paned.add(bottom, weight=1)
        log_outer, log_strip, log_frame = titled_panel(bottom, "Log")
        log_outer.pack(fill="both", expand=True)
        ttk.Button(log_strip, text="Clear", style="Strip.TButton", command=self._clear_log).pack(side="right", padx=6, pady=3)
        self.logbox = tk.Text(log_frame, height=5, bg=T.TOOLBAR, fg=T.LOG_FG, insertbackground=T.FG, relief="flat",
                              font=FONT_SMALL, state="disabled", wrap="word", padx=8, pady=5,
                              highlightthickness=0, selectbackground=T.SELECT)
        log_vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=log_vsb.set)
        self.logbox.pack(side="left", fill="both", expand=True)
        log_vsb.pack(side="right", fill="y")
        for tag, colour in (("warn", T.YELLOW), ("ok", T.GREEN), ("err", T.RED), ("sys", T.HEAD)):
            self.logbox.tag_configure(tag, foreground=colour)
        for line, tag in self._log_lines:  # replay after a theme rebuild
            self._log_insert(line, tag)
        self.after(400, self._place_sash)
        self._refresh_profiles()
        # a click on anything that is not a text field takes the keyboard focus away from it (so the delay
        # spinbox commits and the search dropdown closes)
        self.bind_all("<ButtonPress-1>", self._unfocus_fields, add="+")

    def _unfocus_fields(self, event) -> None:
        w = event.widget
        if not isinstance(w, tk.Misc):
            return
        try:
            if w.winfo_toplevel() is not self:
                return
            if isinstance(w, (ttk.Entry, ttk.Spinbox, ttk.Combobox, tk.Entry, tk.Text, tk.Listbox, tk.Spinbox)):
                return
            focused = self.focus_get()
            if isinstance(focused, (ttk.Entry, ttk.Spinbox, ttk.Combobox, tk.Entry, tk.Spinbox)):
                self.focus_set()
        except (KeyError, tk.TclError):
            pass

    def _place_sash(self) -> None:
        """Log pane at the bottom ~22%: retried until the paned window actually has a height."""
        try:
            self.update_idletasks()
            height = self.paned.winfo_height()
            if height < 100:
                self.after(100, self._place_sash)
                return
            self.paned.sashpos(0, int(height * 0.78))
        except tk.TclError:
            pass

    def show_info(self) -> None:
        """One Info window at a time: a second click brings the existing one forward."""
        win = getattr(self, "_info", None)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.focus_force()
            return
        self._info = InfoDialog(self)

    def _show_tools(self) -> None:
        mark = lambda on: "\u2611" if on else "\u2610"  # noqa: E731
        items = [("Launch group editor…", lambda: GroupEditor(self)), None,
                 ("Import from launcher…", self.import_from_launcher),
                 ("Backup launcher…", self.backup_launcher),
                 ("Restore launcher…", self.restore_launcher), None,
                 (f"{mark(self.opt_streamer.get())}  Streamer mode", self._toggle_streamer),
                 (f"{mark(self.opt_tray.get())}  Exit to tray", self._toggle_exit_to_tray)]
        popup_menu(self, items, lambda: (self.tools_btn.winfo_rootx(),
                                         self.tools_btn.winfo_rooty() + self.tools_btn.winfo_height()),
                   key="tools", ignore=(self.tools_btn, *self._drag_handles))

    def _toggle_streamer(self) -> None:
        self.opt_streamer.set(not self.opt_streamer.get())
        self._streamer_toggled()
        self.log("Streamer mode " + ("on: account names and ids are hidden." if self.opt_streamer.get() else "off."), "sys")

    def _toggle_exit_to_tray(self) -> None:
        self.opt_tray.set(not self.opt_tray.get())
        self._save_options()
        self.log("Exit to tray " + ("on: the close button hides wauncher to the tray icon." if self.opt_tray.get() else "off."), "sys")

    def _show_themes(self) -> None:
        items = [(("● " if name == T.current_theme else "   ") + name, (lambda n=name: self.set_theme(n)))
                 for name in T.THEME_NAMES]
        popup_menu(self, items, lambda: (self.theme_btn.winfo_rootx(),
                                         self.theme_btn.winfo_rooty() + self.theme_btn.winfo_height()),
                   key="theme", ignore=(self.theme_btn, *self._drag_handles))

    def set_theme(self, name: str) -> None:
        """Switch palette and rebuild the whole window content (explicit-colour widgets do not restyle)."""
        name = T.set_palette(name)
        self.config_.update(theme=name)
        PopupMenu.close_all()
        selection = list(self.tree.selection())
        apply_theme(self)
        outer = self._frameless_hook.window_size() if self._frameless_hook else None
        self.body.destroy()
        self.top_edge.destroy()
        self._build()
        if outer and self.state() == "normal":
            self._converge(*outer)  # keep the exact outer size the window had before the rebuild
        self.rebuild_tree()
        for iid in selection:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)
        self._refresh_profiles()
        if self.server_status:
            self._apply_status(self.server_status, reschedule=False)
        self.log(f"Theme: {name}.", "sys")

    # ------------------------------------------------------------------ log / status
    def _log_insert(self, line: str, tag: str | None) -> None:
        self.logbox.configure(state="normal")
        self.logbox.insert("end", line + "\n", tag or "")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def log(self, message: str, tag: str | None = None) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        self._log_lines.append((line, tag))
        del self._log_lines[:-500]
        self._log_insert(line, tag)

    def _clear_log(self) -> None:
        self._log_lines.clear()
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")

    def _drain_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "log":
                    self.log(payload["text"], payload.get("tag"))
                elif event == "refresh":
                    self._tick(now=True)
                elif event == "launch_done":
                    self._launch_thread = None
                    self._update_launch_button()
                elif event == "status":
                    self._apply_status(payload)
                elif event == "corp":
                    self._corp_result(payload)
                elif event == "call":
                    payload["fn"]()
                elif event == "scan":
                    self._apply_scan(payload)
        except queue.Empty:
            pass
        self.after(150, self._drain_events)

    # ------------------------------------------------------------------ server status
    def _poll_status(self) -> None:
        if self._status_job:
            self.after_cancel(self._status_job)
            self._status_job = None
        threading.Thread(target=lambda: self.events.put(("status", srv.fetch())), daemon=True).start()

    def _apply_status(self, status: dict, reschedule: bool = True) -> None:
        was_online = self.server_status.get("online")
        self.server_status = status
        text, kind = srv.describe(status)
        self.status_server_var.set(text)
        self.status_server_lbl.configure(style={"ok": "StatusOn.TLabel", "vip": "StatusVip.TLabel"}.get(kind, "Status.TLabel"))
        if reschedule:
            if was_online is not None and status.get("online") is not None and was_online != status.get("online"):
                self.log("Tranquility is " + ("back online." if status["online"] else "offline."), "ok" if status["online"] else "warn")
            self._status_job = self.after(srv.next_interval(status) * 1000, self._poll_status)

    def _server_tooltip(self) -> str:
        s = self.server_status
        if not s:
            return "not checked yet"
        lines = [f"checked: {s.get('checked_at', '?')}", f"version: {s.get('server_version', '?')}",
                 f"up since: {s.get('start_time', '?')}", f"next poll: every {srv.next_interval(s)} s"]
        if s.get("error"):
            lines.append(f"error: {s['error']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ profiles / options
    def _shared_cache(self) -> str:
        return self.config_.get("shared_cache") or (self.data.d.get("launcher_settings") or {}).get("shared_cache") or r"C:\CCP\EVE"

    PROFILE_GROUP = "Use launch group's profile, otherwise Default"
    PROFILE_DEFAULT = "Use Default settings profile"
    PROFILE_FORCE = "Force "

    def _refresh_profiles(self) -> None:
        names = [n for n in profiles.list_profiles(self._shared_cache()) if n != "Default"]
        self.profile_box.configure(values=[self.PROFILE_GROUP, self.PROFILE_DEFAULT] + [self.PROFILE_FORCE + n for n in names])
        mode, name = self.config_.get("profile_mode") or "group", self.config_.get("profile") or ""
        if mode == "force" and name in names:
            self.profile_mode_var.set(self.PROFILE_FORCE + name)
        elif mode == "default":
            self.profile_mode_var.set(self.PROFILE_DEFAULT)
        else:
            self.profile_mode_var.set(self.PROFILE_GROUP)

    def _profile_choice(self) -> tuple[str, str]:
        """(mode, forced name) from the dropdown text."""
        text = self.profile_mode_var.get()
        if text.startswith(self.PROFILE_FORCE) and len(text) > len(self.PROFILE_FORCE):
            return "force", text[len(self.PROFILE_FORCE):]
        if text == self.PROFILE_DEFAULT:
            return "default", ""
        return "group", ""

    def _profile_for_launch(self, group: dict | None) -> str:
        mode, name = self._profile_choice()
        if mode == "force":
            return name
        if mode == "group" and group and group.get("profile"):
            return group["profile"]
        return "Default"

    def _streamer_toggled(self) -> None:
        self._save_options()
        self.search.var.set("")
        self.rebuild_tree()

    def _save_options(self) -> None:
        try:
            delay = int(self.opt_delay.get())
        except (tk.TclError, ValueError):
            delay = 0
        mode, name = self._profile_choice()
        self.config_.update(kill_conflicting=bool(self.opt_kill.get()), login_screen=bool(self.opt_login.get()),
                            profile_mode=mode, profile=name or self.config_.get("profile") or "",
                            startup_delay=max(0, delay), streamer_mode=bool(self.opt_streamer.get()),
                            exit_to_tray=bool(self.opt_tray.get()))

    # ------------------------------------------------------------------ streamer mode
    @property
    def streamer(self) -> bool:
        return bool(self.opt_streamer.get())

    def acc_name(self, account: dict) -> str:
        """Account name for display: obfuscated in streamer mode (stable number per account)."""
        if not self.streamer:
            return account.get("name") or str(account.get("userId"))
        ids = [int(a["userId"]) for a in self.data.accounts]
        try:
            n = ids.index(int(account["userId"])) + 1
        except ValueError:
            n = 0
        return f"account {n:02d}"

    def acc_id(self, account: dict) -> str:
        return "••••••••" if self.streamer else str(account.get("userId"))

    # ------------------------------------------------------------------ data -> tree
    def _ordered_accounts(self, all_accounts: bool = False) -> list[dict]:
        order = [int(u) for u in self.config_.get("account_order") or []]
        by_id = {int(a["userId"]): a for a in self.data.accounts}
        out = [by_id[u] for u in order if u in by_id]
        out += [a for a in self.data.accounts if int(a["userId"]) not in set(order)]
        if self._filter is not None and not all_accounts:
            out = [a for a in out if int(a["userId"]) in self._filter]
        return out

    def _ordered_characters(self, account: dict) -> list[dict]:
        order = [int(c) for c in (self.config_.get("character_order") or {}).get(str(account["userId"]), [])]
        by_id = {int(c["characterId"]): c for c in account.get("characters", [])}
        out = [by_id[c] for c in order if c in by_id]
        out += [c for c in account.get("characters", []) if int(c["characterId"]) not in set(order)]
        return out

    @staticmethod
    def _corp_text(ch: dict) -> str:
        corp = ch.get("corporation") or ""
        if ch.get("alliance"):
            corp += f"  [{ch['alliance']}]"
        return corp

    def rebuild_tree(self) -> None:
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children(""))
        for acc in self._ordered_accounts():
            uid = f"u{acc['userId']}"
            self.tree.insert("", "end", iid=uid, text=f"{self.acc_name(acc)}   ·   {self.acc_id(acc)}",
                             values=("", "", ""), tags=("account",), open=True)
            for ch in self._ordered_characters(acc):
                self.tree.insert(uid, "end", iid=f"c{ch['characterId']}", text=ch["name"],
                                 values=(self._corp_text(ch), "", ""))
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)
        self.show_all_btn.configure(state="normal" if self._filter is not None else "disabled")
        self._apply_running()
        self._update_launch_button()

    def groups_changed(self) -> None:
        if self._picked_group and not self.data.group(self._picked_group):
            self._picked_group = None
            self._filter = None
            self.status_group_var.set("")
        self.rebuild_tree()

    def _persist_order(self) -> None:
        visible = [int(iid[1:]) for iid in self.tree.get_children("")]
        if self._filter is None:
            account_order = visible
        else:
            old = [int(a["userId"]) for a in self._ordered_accounts(all_accounts=True)]
            it = iter(visible)
            account_order = [next(it) if u in self._filter else u for u in old]
        character_order = dict(self.config_.get("character_order") or {})
        for uid in visible:
            character_order[str(uid)] = [int(c[1:]) for c in self.tree.get_children(f"u{uid}")]
        self.config_.update(account_order=account_order, character_order=character_order)

    # ------------------------------------------------------------------ tree mouse handling
    def _tree_press(self, event) -> None:
        self._drag_iid = self.tree.identify_row(event.y) or None
        self._drag_moved = False
        self._drag_y = event.y

    def _tree_drag(self, event) -> str | None:
        if not self._drag_iid:
            return None
        if abs(event.y - self._drag_y) < 6 and not self._drag_moved:
            return None
        self._drag_moved = True
        self.tree.configure(cursor="fleur")
        target = self.tree.identify_row(event.y)
        if not target or target == self._drag_iid:
            return "break"
        src_parent = self.tree.parent(self._drag_iid)
        if src_parent:
            if self.tree.parent(target) == src_parent:
                self.tree.move(self._drag_iid, src_parent, self.tree.index(target))
        else:
            tgt = target if not self.tree.parent(target) else self.tree.parent(target)
            if tgt != self._drag_iid:
                self.tree.move(self._drag_iid, "", self.tree.index(tgt))
        return "break"

    def _tree_release(self, _event) -> None:
        self.tree.configure(cursor="")
        if self._drag_iid and self._drag_moved:
            self._persist_order()
            self.tree.selection_set(self._drag_iid)
        self._drag_iid = None
        self._drag_moved = False

    def _tree_double(self, event) -> str | None:
        iid = self.tree.identify_row(event.y)
        if not iid or not self.tree.parent(iid):
            return None
        found = self.data.character(int(iid[1:]))
        if not found:
            return "break"
        account, character = found
        self.refresh_running_now()
        running = self._running_for_account(account)
        same = [r for r in running if r.character_name == character["name"]]
        if same:
            cl.focus(same[0].hwnd)
            self.log(f"{character['name']} is already logged in (pid {same[0].pid}); brought its window to the front.")
            return "break"
        force_kill = False
        if running:
            lines = []
            for r in running:
                if r.character_name:
                    who = f"EVE - {r.character_name}"
                else:
                    cid = self._client_character_id(r, account)
                    found = self.data.character(cid) if cid else None
                    name = found[1]["name"] if found else self.acc_name(account)
                    who = f"{name}  ({'login screen' if r.hwnd else 'starting'})"
                when = f"   started {time.strftime('%H:%M:%S', time.localtime(r.create_time))}" if r.create_time else ""
                lines.append(f"{who}   pid {r.pid}{when}")
            dlg = ConfirmDialog(self, APP_TITLE,
                                f"This account ({self.acc_name(account)}) is running already",
                                "\n".join(lines),
                                f"Proceeding to launch {character['name']} would require the existing client to be closed.",
                                "Close it, proceed")
            if not dlg.result:
                return "break"
            force_kill = True
        self.tree.selection_set(iid)
        self.launch_selected(force_kill=force_kill)
        return "break"

    def _tree_context(self, event) -> str | None:
        """Right-click on a character row."""
        iid = self.tree.identify_row(event.y)
        if not iid or not self.tree.parent(iid):
            return None
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        character_id = int(iid[1:])
        if not self.data.character(character_id):
            return "break"
        items = [("Wrong corp?", lambda: self.check_corporation(character_id))]
        x_root, y_root = event.x_root, event.y_root

        def anchor(iid=iid, dx=event.x):
            box = self.tree.bbox(iid, "#0")
            if box:
                return self.tree.winfo_rootx() + dx, self.tree.winfo_rooty() + box[1] + box[3]
            return x_root, y_root
        popup_menu(self, items, anchor, key="context", min_width=160)
        return "break"

    # ------------------------------------------------------------------ "Wrong corp?" (ESI)
    def check_corporation(self, character_id: int) -> None:
        found = self.data.character(character_id)
        if not found:
            return
        _acc, ch = found
        self.log(f"{ch['name']}: asking ESI for the current corporation…")

        def work() -> None:
            try:
                self.events.put(("corp", {"characterId": character_id, "result": esi.affiliation(character_id)}))
            except esi.EsiError as exc:
                self.events.put(("log", {"text": f"{ch['name']}: ESI lookup failed: {exc}", "tag": "err"}))
        threading.Thread(target=work, daemon=True).start()

    def _corp_result(self, payload: dict) -> None:
        found = self.data.character(int(payload["characterId"]))
        if not found:
            return
        _acc, ch = found
        res = payload["result"]
        before = self._corp_text(ch)
        changed = (res["corporation"] != (ch.get("corporation") or "")) or (res["alliance"] != (ch.get("alliance") or ""))
        if res.get("name") and res["name"] != ch["name"]:
            self.log(f"{ch['name']}: ESI knows this character as '{res['name']}' (renamed?)", "warn")
        if not changed:
            self.log(f"{ch['name']}: corporation confirmed by ESI: {before or '(none)'}", "ok")
            return
        ch["corporation"] = res["corporation"]
        ch["alliance"] = res["alliance"]
        ch["corporationId"] = res["corporation_id"]
        ch["allianceId"] = res["alliance_id"]
        self.data.save()
        iid = f"c{ch['characterId']}"
        if self.tree.exists(iid):
            self.tree.set(iid, "corp", self._corp_text(ch))
        self.log(f"{ch['name']}: corporation changed: {before or '(none)'}  →  {self._corp_text(ch)} (updated)", "warn")

    # ------------------------------------------------------------------ search / selection
    def _search_items(self) -> list[tuple[str, str, object]]:
        items: list[tuple[str, str, object]] = []
        for acc in self.data.accounts:
            for ch in acc.get("characters", []):
                items.append((ch["name"], "character", int(ch["characterId"])))
        for acc in self.data.accounts:
            items.append((self.acc_name(acc), "account", int(acc["userId"])))
        for g in self.data.groups:
            items.append((g["name"], "group", g["groupId"]))
        return items

    def _group_items(self) -> list[tuple[str, str, object]]:
        groups = sorted(((g["name"], "group", g["groupId"]) for g in self.data.groups), key=lambda r: r[0].lower())
        return [(f"clients ({len(self.running)})", "running", None)] + groups

    def _running_rows(self) -> list[str]:
        rows: list[str] = []
        for acc in self.data.accounts:
            for r in self._running_for_account(acc):
                cid = self._client_character_id(r, acc)
                iid = f"c{cid}" if cid else f"u{acc['userId']}"
                if self.tree.exists(iid) and iid not in rows:
                    rows.append(iid)
        return rows

    def _clear_member_tags(self) -> None:
        for iid in self.tree.get_children(""):
            self.tree.item(iid, tags=("account",))
            for c in self.tree.get_children(iid):
                self.tree.item(c, tags=())

    def _search_picked(self, kind: str, key, label: str) -> None:
        self.tree.selection_remove(*self.tree.selection())
        if kind == "running":
            if self._filter is not None:
                self.show_all()
            self._clear_member_tags()
            self._picked_group = None
            rows = self._running_rows()
            for iid in rows:
                self.tree.selection_add(iid)
            if rows:
                self.tree.see(rows[0])
            self.status_group_var.set(f"running clients: {len(rows)}")
            self.search.var.set("")
        elif kind == "group":
            g = self.data.group(key)
            if not g:
                return
            self._picked_group = g["groupId"]
            self._filter = {int(m["userId"]) for m in g.get("members", [])}
            self.rebuild_tree()
            first = None
            for m in g.get("members", []):
                iid = f"c{m['characterId']}" if m.get("characterId") else f"u{m['userId']}"
                if self.tree.exists(iid):
                    self.tree.selection_add(iid)
                    self.tree.item(iid, tags=list(self.tree.item(iid, "tags")) + ["member"])
                    first = first or iid
            if first:
                self.tree.see(first)
            self.status_group_var.set(f"group: {g['name']} ({len(g.get('members', []))} accounts)")
        else:
            self._clear_member_tags()
            iid = f"c{key}" if kind == "character" else f"u{key}"
            if not self.tree.exists(iid) and self._filter is not None:
                self.show_all()
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)
        self._apply_running()
        self._update_launch_button()
        self.tree.focus_set()

    def deselect_all(self) -> None:
        self.tree.selection_remove(*self.tree.selection())
        self._clear_member_tags()
        self._picked_group = None
        self.status_group_var.set("")
        self.search.var.set("")
        self._apply_running()
        self._update_launch_button()

    def show_all(self) -> None:
        self._filter = None
        self._picked_group = None
        self.status_group_var.set("")
        self.rebuild_tree()

    # ------------------------------------------------------------------ running clients
    def _tick(self, now: bool = False) -> None:
        """Scan running clients off the UI thread; _apply_scan() takes the result."""
        if not getattr(self, "_scan_busy", False):
            self._scan_busy = True

            def work() -> None:
                try:
                    running = cl.list_running()
                    gone = self.launched.prune(cl.is_alive)
                    self.events.put(("scan", {"running": running, "gone": gone}))
                except Exception as exc:  # noqa: BLE001
                    self.events.put(("scan", {"error": str(exc)}))
            threading.Thread(target=work, daemon=True, name="scan").start()
        if not now:
            self.after(self.REFRESH_MS, self._tick)

    def refresh_running_now(self) -> None:
        """Synchronous scan for decisions that must see the current state (a launch click, the editor's
        From clients). Cheap once psutil is warm; the periodic scan stays on its worker thread."""
        try:
            self.running = cl.list_running()
            self.launched.prune(cl.is_alive)
            self._apply_running()
        except Exception as exc:  # noqa: BLE001
            self.log(f"Client scan failed: {exc}", "warn")

    def _apply_scan(self, payload: dict) -> None:
        self._scan_busy = False
        if "error" in payload:
            self.log(f"Client scan failed: {payload['error']}", "warn")
            return
        self.running = payload["running"]
        for c in payload["gone"]:
            acc = self.data.account(c.get("userId", -1))
            who = c.get("characterName") or (self.acc_name(acc) if acc else "?")
            self.log(f"Client for {who} (pid {c.get('pid')}) has exited.")
        self._apply_running()
        self._update_launch_button()

    def _running_for_account(self, account: dict) -> list[cl.RunningClient]:
        """Clients of this account: by the user id on their command line (works for clients the official
        launcher started), else ones we started (pid + creation time), else by the logged-in window title."""
        uid = int(account["userId"])
        names = {c["name"] for c in account.get("characters", [])}
        ours = {(int(c["pid"]), round(float(c.get("creationTime") or 0))) for c in self.launched.for_user(uid)}
        out = []
        for r in self.running:
            if r.user_id is not None:
                if r.user_id == uid:
                    out.append(r)
            elif (r.pid, round(r.create_time)) in ours or (r.character_name and r.character_name in names):
                out.append(r)
        return out

    def _client_character_id(self, r: cl.RunningClient, account: dict) -> int | None:
        """Which character a client is about: the logged-in one from the title, else the one it was told to
        auto-select (command line), else what we recorded when we started it."""
        if r.character_name:
            return next((c["characterId"] for c in account.get("characters", []) if c["name"] == r.character_name), None)
        if r.character_id:
            return r.character_id
        mine = next((c for c in self.launched.clients if int(c["pid"]) == r.pid), None)
        return mine.get("characterId") if mine else None

    def _apply_running(self) -> None:
        by_pid = {int(c["pid"]): c for c in self.launched.clients}
        for acc in self.data.accounts:
            uid = f"u{acc['userId']}"
            if not self.tree.exists(uid):
                continue
            run = self._running_for_account(acc)
            self.tree.set(uid, "status", f"{len(run)} running" if run else "")
            for ch in acc.get("characters", []):
                cid = f"c{ch['characterId']}"
                if not self.tree.exists(cid):
                    continue
                mine = [r for r in run if self._client_character_id(r, acc) == ch["characterId"]]
                tags = [t for t in self.tree.item(cid, "tags") if t not in ("running", "login")]
                if mine:
                    r = mine[0]
                    where = "logged in" if r.character_name else ("login screen" if r.hwnd else "starting")
                    self.tree.set(cid, "status", f"{where} · pid {r.pid}" + ("" if r.pid in by_pid else " · external"))
                    self.tree.set(cid, "launched", time.strftime("%H:%M:%S", time.localtime(r.create_time)) if r.create_time else "")
                    tags.append("running" if r.character_name else "login")
                else:
                    self.tree.set(cid, "status", "")
                    self.tree.set(cid, "launched", "")
                self.tree.item(cid, tags=tags)
        self.status_clients_var.set(f"{len(self.running)} clients running, {len(self.launched.clients)} started here")

    # ------------------------------------------------------------------ selection -> launch targets
    def _targets(self) -> list[dict]:
        out, seen = [], set()
        for iid in self.tree.selection():
            if iid.startswith("c"):
                found = self.data.character(int(iid[1:]))
                if found and found[1]["characterId"] not in seen:
                    seen.add(found[1]["characterId"])
                    out.append({"account": found[0], "character": found[1]})
        for iid in self.tree.selection():
            if iid.startswith("u"):
                acc = self.data.account(int(iid[1:]))
                if not acc or any(t["account"] is acc for t in out):
                    continue
                chars = acc.get("characters", [])
                active = next((c for c in chars if c["characterId"] == acc.get("activeCharacterId")), None)
                out.append({"account": acc, "character": active or (chars[0] if chars else None)})
        return out

    def _conflicts_for(self, targets: list[dict]) -> dict[int, list[cl.RunningClient]]:
        return {int(t["account"]["userId"]): run for t in targets if (run := self._running_for_account(t["account"]))}

    def _conflict_text(self) -> str:
        targets = self._targets()
        if not targets:
            return "Closes a client that is already running for an account before launching it again.\n(select rows to see conflicts)"
        conflicts = self._conflicts_for(targets)
        if not conflicts:
            return "No conflicting clients for the current selection."
        lines = ["Already running for the selection (would be closed first):"]
        for t in targets:
            for r in conflicts.get(int(t["account"]["userId"]), []):
                lines.append(f"  {self.acc_name(t['account'])}: {r.title}  (pid {r.pid})")
        return "\n".join(lines)

    def _update_launch_button(self) -> None:
        targets = self._targets()
        n = len(targets)
        busy = self._launch_thread is not None and self._launch_thread.is_alive()
        self.launch_btn.configure(text=f"Launch {n}" if n else "Launch", state="disabled" if busy or not n else "normal")
        self.close_btn.configure(state="normal" if n and self._conflicts_for(targets) else "disabled")
        if busy:
            self.selection_var.set("launching…")
        elif not n:
            self.selection_var.set("select characters, an account or a group")
        else:
            self.selection_var.set(f"{n} selected")

    def _selection_text(self) -> str:
        targets = self._targets()
        if not targets:
            return ""
        conflicts = self._conflicts_for(targets)
        lines = []
        for t in targets:
            acc = self.acc_name(t["account"])
            who = t["character"]["name"] if t["character"] else f"{acc} (account)"
            lines.append(f"{who}  ({acc})" + ("   · running" if conflicts.get(int(t["account"]["userId"])) else ""))
        return "\n".join(lines)

    # ------------------------------------------------------------------ launch
    def launch_selected(self, force_kill: bool = False) -> None:
        if self._launch_thread is not None and self._launch_thread.is_alive():
            self.log("A launch is already in progress.", "warn")
            return
        targets = self._targets()
        if not targets:
            self.log("Nothing selected: pick characters, an account or a group first.", "warn")
            return
        self._save_options()
        settings = dict(self.data.d.get("launcher_settings") or {})
        settings.update({k: v for k, v in (("dx", self.config_.get("dx")), ("language", self.config_.get("language")),
                                           ("shared_cache", self.config_.get("shared_cache"))) if v})
        delay = int(self.config_.get("startup_delay") or 0) or int(settings.get("startup_delay") or 2)
        group = self.data.group(self._picked_group) if self._picked_group else None
        profile = self._profile_for_launch(group)
        if not force_kill:
            # the exact character already logged in (per the client window title): nothing to do, whatever
            # the kill option says; a forced relaunch from the double-click dialog is the only exception
            self.refresh_running_now()
            kept = []
            for t in targets:
                ch = t["character"]
                same = [r for r in self._running_for_account(t["account"]) if ch and r.character_name == ch["name"]] if ch else []
                if same:
                    self.log(f"{ch['name']} is already logged in (pid {same[0].pid}); not relaunched.", "warn")
                else:
                    kept.append(t)
            targets = kept
            if not targets:
                return
        if not force_kill and not self.opt_kill.get():
            # an account whose client is still alive is left alone; a dead one (gone from the process list)
            # no longer counts as running, so it gets started again
            self.refresh_running_now()
            kept = []
            for t in targets:
                running = self._running_for_account(t["account"])
                if running:
                    who = t["character"]["name"] if t["character"] else self.acc_name(t["account"])
                    pids = ", ".join(str(r.pid) for r in running)
                    self.log(f"{who}: account {self.acc_name(t['account'])} already has a running client (pid {pids}); "
                             "not launched again. Tick 'Kill conflicting clients' to replace it.", "warn")
                else:
                    kept.append(t)
            targets = kept
            if not targets:
                return
        jobs = []
        for t in targets:
            acc, ch = t["account"], t["character"]
            jobs.append({"userId": int(acc["userId"]), "accountName": acc["name"], "accountLabel": self.acc_name(acc),
                         "characterId": None if self.opt_login.get() or not ch else int(ch["characterId"]),
                         "characterName": ch["name"] if ch else "", "profile": profile,
                         "conflicts": self._running_for_account(acc) if (force_kill or self.opt_kill.get()) else []})
        exe = cl.client_exe(settings.get("shared_cache") or r"C:\CCP\EVE")
        if not os.path.isfile(exe):
            self.log(f"Game client not found: {exe} (set shared_cache in config.json)", "err")
            return
        if not self._version_ok(settings.get("shared_cache") or r"C:\CCP\EVE"):
            return
        device_id, journey_id = cl.registry_ids()
        self._launch_thread = threading.Thread(target=self._launch_worker, daemon=True,
                                               args=(jobs, exe, settings, delay, device_id, journey_id))
        self._launch_thread.start()
        self._update_launch_button()

    def _version_ok(self, shared_cache: str) -> bool:
        """Compare the installed client build (tq/start.ini) with Tranquility's server_version from ESI.
        A mismatch means the client needs the official launcher to update it; ask before launching anyway."""
        local = cl.installed_build(shared_cache)
        status = self.server_status if self.server_status.get("server_version") else srv.fetch(timeout=5.0)
        server = str(status.get("server_version") or "")
        if not local or not server:
            self.log(f"Version check skipped (client build {local or 'unknown'}, server {server or 'unknown'}).", "warn")
            return True
        if local == server:
            return True
        self.log(f"Client build {local} does not match Tranquility {server}: the client probably needs updating.", "warn")
        dlg = ConfirmDialog(self, APP_TITLE, "EVE client version mismatch",
                            f"installed client build   {local}\nTranquility server        {server}",
                            "The client is probably out of date. Run the official EVE launcher once to update it, "
                            "or launch anyway (the client may refuse to connect).", "Launch anyway")
        return bool(dlg.result)

    def _emit(self, text: str, tag: str | None = None) -> None:
        self.events.put(("log", {"text": text, "tag": tag}))

    def _launch_worker(self, jobs: list[dict], exe: str, settings: dict, delay: int, device_id: str, journey_id: str) -> None:
        try:
            for i, job in enumerate(jobs):
                if i:
                    time.sleep(delay)
                who = job["characterName"] or job["accountLabel"]
                for r in job["conflicts"]:
                    if cl.kill(r.pid, r.create_time):
                        self._emit(f"Closed running client {r.title} (pid {r.pid}) for {job['accountLabel']}.", "warn")
                if job["conflicts"]:
                    time.sleep(1.0)
                tok = self.tokens.get(job["userId"])
                if not tok or not tok.get("refreshToken"):
                    self._emit(f"{who}: no refresh token stored for account {job['accountLabel']}; import from the launcher.", "err")
                    continue
                access = tok.get("accessToken") or ""
                if sso.token_valid_for(access) <= 0:
                    try:
                        res = sso.refresh(tok.get("clientId") or "eveLauncherTQ", tok["refreshToken"])
                    except sso.SsoError as exc:
                        self._emit(f"{who}: SSO refresh failed: {exc}", "err")
                        continue
                    access = res["access_token"]
                    fields = {"accessToken": access, "expiresAt": int(time.time()) + int(res.get("expires_in") or 0)}
                    if res.get("refresh_token") and res["refresh_token"] != tok["refreshToken"]:
                        fields["refreshToken"] = res["refresh_token"]
                        self._emit(f"{who}: SSO returned a new refresh token (CCP started rotating tokens); stored.", "warn")
                    self.tokens.set(job["userId"], **fields)
                    tok = self.tokens.get(job["userId"])
                args = cl.build_args(job["userId"], job["characterId"], access, tok["refreshToken"], job["profile"],
                                     settings.get("language") or "en", settings.get("dx") or "dx11", device_id, journey_id)
                try:
                    pid, ctime = cl.spawn(exe, args)
                except OSError as exc:
                    self._emit(f"{who}: could not start the client: {exc}", "err")
                    continue
                self.launched.add(pid=pid, creationTime=ctime, userId=job["userId"], characterId=job["characterId"],
                                  characterName=job["characterName"], accountName=job["accountName"],
                                  profile=job["profile"], launchedAt=time.time())
                mode = "login screen" if job["characterId"] is None else "auto-select"
                self._emit(f"Started {who} (account {job['accountLabel']}, profile {job['profile']}, {mode}) pid {pid}.", "ok")
                self.events.put(("refresh", {}))
        except Exception:  # noqa: BLE001
            self._emit("Launch failed:\n" + traceback.format_exc(), "err")
        finally:
            self.events.put(("launch_done", {}))

    def close_selected_clients(self) -> None:
        conflicts = self._conflicts_for(self._targets())
        if not conflicts:
            self.log("No running clients for the selection.")
            return
        n = 0
        for runs in conflicts.values():
            for r in runs:
                if cl.kill(r.pid, r.create_time):
                    n += 1
                    self.log(f"Closed {r.title} (pid {r.pid}).", "warn")
        self.log(f"Closed {n} client(s).")
        self.after(500, lambda: self._tick(now=True))

    # ------------------------------------------------------------------ official launcher: import / backup / restore
    def import_from_launcher(self, quiet: bool = False) -> None:
        try:
            snap = ls.snapshot()
        except FileNotFoundError as exc:
            self.log(f"Official launcher data not found ({exc}). Is the EVE launcher installed and logged in?", "err")
            return
        except Exception as exc:  # noqa: BLE001
            self.log(f"Could not read the official launcher state: {exc}", "err")
            return
        if not snap.accounts:
            self.log("The official launcher has no accounts to import (log in there first).", "warn")
            return
        if not quiet and self.data.accounts:
            if not messagebox.askyesno(APP_TITLE, f"Import {len(snap.accounts)} accounts and {len(snap.tokens)} token sets "
                                       "from the official launcher?\n\nYour ordering is kept. Launch groups you already have "
                                       "are never changed; only launcher groups new to wauncher are added.", parent=self):
                return
        old_chars = {c["characterId"]: c for a in self.data.accounts for c in a.get("characters", [])}
        self.data.d["accounts"] = [
            {"userId": a.user_id, "name": a.name, "activeCharacterId": a.active_character_id,
             "characters": [{"characterId": c.character_id, "name": c.name,
                             "corporation": c.corporation or old_chars.get(c.character_id, {}).get("corporation", ""),
                             "alliance": c.alliance or old_chars.get(c.character_id, {}).get("alliance", "")}
                            for c in a.characters]} for a in snap.accounts]
        known = {g["groupId"] for g in self.data.groups}
        added = [{"groupId": g.group_id, "name": g.name, "local": False,
                  "members": [{"userId": m.user_id, "characterId": m.character_id} for m in g.members]}
                 for g in snap.groups if g.group_id not in known]
        self.data.d["groups"] = list(self.data.groups) + added
        self.data.d["active_group_id"] = snap.active_group_id
        self.data.d["launcher_settings"] = snap.settings
        self.data.d["imported_at"] = time.time()
        self.data.save()
        try:
            self.tokens.replace_all(snap.tokens)
        except OSError as exc:
            self.log(f"Could not write the token store: {exc}", "err")
        self.groups_changed()
        self._refresh_profiles()
        self.log(f"Imported {len(snap.accounts)} accounts, {sum(len(a.characters) for a in snap.accounts)} characters, "
                 f"{len(snap.tokens)} token sets from the official launcher; {len(added)} new launch groups added, "
                 f"{len(known)} existing groups left as they were.", "ok")

    BACKUP_WARNING = ("The backup feature exports your official EVE launcher data to a file that can be imported using "
                      "this same tool on another computer. Treat this file as extremely sensitive: it contains tokens "
                      "which allow access to your accounts.")
    RESTORE_WARNING = ("The restore feature will overwrite your official EVE launcher data with data from a backup file. "
                       "If you restore the wrong file you may have to reset your EVE launcher and log into everything "
                       "again. Make sure you back up the launcher on the target PC first if restoring from a different "
                       "source PC!")

    def backup_launcher(self) -> None:
        if not ConfirmDialog(self, APP_TITLE, "Backup the official EVE launcher data", "", self.BACKUP_WARNING,
                             "Continue").result:
            return
        default = time.strftime("launcher-state-%Y%m%d-%H%M%S.json")
        path = filedialog.asksaveasfilename(parent=self, title="Backup the official launcher state",
                                            initialdir=backups_dir(), initialfile=default, defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            state = ls.backup_to(path)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Backup failed: {exc}", "err")
            return
        users = state.get("v2.1/users", {}).get("eve-online", {}).get("tranquility", {}).get("ids", [])
        self.log(f"Backed up the launcher state ({len(users)} accounts) to {path}. Treat it like a password: "
                 "it contains refresh tokens.", "ok")

    def restore_launcher(self) -> None:
        if not ConfirmDialog(self, APP_TITLE, "Restore the official EVE launcher data", "", self.RESTORE_WARNING,
                             "Continue").result:
            return
        path = filedialog.askopenfilename(parent=self, title="Restore the official launcher state from a backup",
                                          initialdir=backups_dir(), filetypes=[("JSON", "*.json")])
        if not path:
            return
        if ls.launcher_pids():
            if not messagebox.askyesno(APP_TITLE, "The EVE launcher (eve-online.exe) is running and would overwrite the "
                                       "restored file.\n\nClose it now and continue?", parent=self):
                return
            n = ls.kill_launcher()
            self.log(f"Closed the EVE launcher ({n} processes).", "warn")
            time.sleep(1.0)
        try:
            kept = ls.restore_from(path, backups_dir())
        except Exception as exc:  # noqa: BLE001
            self.log(f"Restore failed: {exc}", "err")
            return
        self.log(f"Restored the launcher state from {path}. The previous state.json was kept at {kept}.", "ok")

    # ------------------------------------------------------------------ close
    def _on_close(self) -> None:
        if self.opt_tray.get() and self.tray is not None:
            self._remember_geometry()
            PopupMenu.close_all()
            self.withdraw()
            return
        self.quit_app()


def main() -> None:
    selftest = "--selftest" in sys.argv
    config, data, tokens, launched = Config(), Data(), TokenStore(), Launched()
    app = App(config, data, tokens, launched, selftest=selftest)
    app.mainloop()
