#!/usr/bin/env python3
"""Rosify: a Linux-first, experimental Spotify theme manager."""
from __future__ import annotations

import argparse
import json
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

from rosify_core import (
    apply_theme,
    discover_spotify_archive,
    get_status,
    get_themes,
    get_settings,
    save_settings,
    monitor_auto_apply,
    restore_spotify,
)

BG = "#17131d"
PANEL = "#241d2c"
PANEL_HI = "#2d2437"
TEXT = "#fff4fa"
MUTED = "#b8a9bc"
PINK = "#ff85b8"
PINK_DARK = "#d94f91"
GREEN = "#83ddb4"
RED = "#ff8e9f"
BORDER = "#40334b"


class RosifyApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Rosify · Spotify themes for Linux")
        self.geometry("1020x790")
        self.minsize(860, 690)
        self.configure(bg=BG)
        self.archive_path: Path | None = discover_spotify_archive()
        self.themes = get_themes()
        self.settings = get_settings()
        self.selected_theme = self.settings["selected_theme"]
        self.auto_apply_var = tk.BooleanVar(value=self.settings["auto_apply_on_startup"])
        self.busy = False
        self.theme_cards: dict[str, tk.Frame] = {}
        self.status_data: dict = {}

        self._configure_ttk()
        self._build_ui()
        self.refresh_status(log=False)
        self._log("Rosify is ready. Pick a theme, then apply it with Spotify closed.")

    def _configure_ttk(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Rosify.TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Rosify.TLabel", background=BG, foreground=TEXT, font=("Sans", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Sans", 9))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Sans", 10))
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=("Sans", 9))

    def _build_ui(self) -> None:
        outer = tk.Frame(self, bg=BG, padx=28, pady=22)
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x", pady=(0, 19))
        title_block = tk.Frame(header, bg=BG)
        title_block.pack(side="left", fill="x", expand=True)
        tk.Label(title_block, text="ROSIFY", bg=BG, fg=PINK, font=("Sans", 25, "bold")).pack(anchor="w")
        tk.Label(
            title_block,
            text="Give your Spotify desktop a different look.",
            bg=BG,
            fg=MUTED,
            font=("Sans", 11),
        ).pack(anchor="w", pady=(3, 0))
        tk.Label(
            header,
            text="LINUX FIRST  ·  EXPERIMENTAL",
            bg="#38263b",
            fg="#ffc2de",
            font=("Sans", 8, "bold"),
            padx=12,
            pady=8,
        ).pack(side="right", anchor="n", pady=7)

        tk.Label(outer, text="CHOOSE A THEME", bg=BG, fg=TEXT, font=("Sans", 10, "bold")).pack(anchor="w")
        tk.Label(
            outer,
            text="Three original themes are included. Cotton Candy is the cute pink option.",
            bg=BG,
            fg=MUTED,
            font=("Sans", 9),
        ).pack(anchor="w", pady=(4, 12))

        card_row = tk.Frame(outer, bg=BG)
        card_row.pack(fill="x", pady=(0, 18))
        for column, theme in enumerate(self.themes):
            card = tk.Frame(card_row, bg=PANEL, highlightthickness=2, highlightbackground=BORDER, padx=14, pady=14)
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0 if column == 2 else 8))
            card_row.columnconfigure(column, weight=1, uniform="theme-card")
            self.theme_cards[theme.id] = card

            swatch_row = tk.Frame(card, bg=PANEL)
            swatch_row.pack(fill="x")
            tk.Label(swatch_row, text="●", fg=theme.accent, bg=PANEL, font=("Sans", 19)).pack(side="left")
            tk.Label(swatch_row, text="●", fg=theme.background, bg=PANEL, font=("Sans", 19)).pack(side="left", padx=(3, 0))
            tk.Label(
                card,
                text=theme.name,
                bg=PANEL,
                fg=TEXT,
                font=("Sans", 12, "bold"),
                anchor="w",
                wraplength=240,
                justify="left",
            ).pack(fill="x", pady=(8, 5))
            tk.Label(
                card,
                text=theme.description,
                bg=PANEL,
                fg=MUTED,
                font=("Sans", 9),
                wraplength=240,
                justify="left",
                height=3,
                anchor="nw",
            ).pack(fill="x")
            self._bind_click_tree(card, lambda theme_id=theme.id: self.select_theme(theme_id))

        self._update_theme_cards()

        auto_apply_row = tk.Frame(outer, bg=BG)
        auto_apply_row.pack(fill="x", pady=(0, 12))
        self.auto_apply_check = tk.Checkbutton(
            auto_apply_row,
            text="Auto-apply selected theme in the background after login and Spotify updates",
            variable=self.auto_apply_var,
            command=self.on_auto_apply_changed,
            bg=BG,
            fg=TEXT,
            activebackground=BG,
            activeforeground=PINK,
            selectcolor=PANEL,
            font=("Sans", 9),
            cursor="hand2",
        )
        self.auto_apply_check.pack(anchor="w")
        tk.Label(
            auto_apply_row,
            text="Enable startup monitoring with ./install.sh. Spotify must be closed before its files are changed.",
            bg=BG,
            fg=MUTED,
            font=("Sans", 8),
        ).pack(anchor="w", padx=(24, 0), pady=(2, 0))

        status_panel = tk.Frame(outer, bg=PANEL, padx=16, pady=14)
        status_panel.pack(fill="x", pady=(0, 14))
        status_top = tk.Frame(status_panel, bg=PANEL)
        status_top.pack(fill="x")
        tk.Label(status_top, text="SPOTIFY STATUS", bg=PANEL, fg=TEXT, font=("Sans", 10, "bold")).pack(side="left")
        self.status_label = tk.Label(status_top, text="Checking…", bg=PANEL, fg=MUTED, font=("Sans", 9, "bold"))
        self.status_label.pack(side="right")
        self.path_label = tk.Label(
            status_panel,
            text="Searching for xpui.spa…",
            bg=PANEL,
            fg=MUTED,
            font=("Sans", 9),
            justify="left",
            anchor="w",
            wraplength=900,
        )
        self.path_label.pack(fill="x", pady=(9, 3))
        self.status_note = tk.Label(
            status_panel,
            text="Rosify backs up the Spotify archive before modifying it.",
            bg=PANEL,
            fg=MUTED,
            font=("Sans", 9),
            justify="left",
            anchor="w",
            wraplength=900,
        )
        self.status_note.pack(fill="x")

        actions = tk.Frame(outer, bg=BG)
        actions.pack(fill="x", pady=(0, 15))
        self.apply_button = self._button(actions, "Apply selected theme", self.on_apply, primary=True)
        self.apply_button.pack(side="left")
        self.restore_button = self._button(actions, "Restore backup", self.on_restore)
        self.restore_button.pack(side="left", padx=(8, 0))
        self.browse_button = self._button(actions, "Browse xpui.spa…", self.on_browse)
        self.browse_button.pack(side="right")
        self.refresh_button = self._button(actions, "Refresh", self.on_refresh)
        self.refresh_button.pack(side="right", padx=(0, 8))

        log_header = tk.Frame(outer, bg=BG)
        log_header.pack(fill="x", pady=(0, 6))
        tk.Label(log_header, text="ACTIVITY", bg=BG, fg=TEXT, font=("Sans", 10, "bold")).pack(side="left")
        tk.Label(log_header, text="Logs stay on this screen", bg=BG, fg=MUTED, font=("Sans", 8)).pack(side="right")
        self.log_box = tk.Text(
            outer,
            height=7,
            bg="#120f17",
            fg="#d8cbdc",
            insertbackground=PINK,
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            font=("Monospace", 9),
            wrap="word",
            state="disabled",
        )
        self.log_box.pack(fill="both", expand=True)

        footer = tk.Frame(outer, bg=BG)
        footer.pack(fill="x", pady=(10, 0))
        tk.Label(
            footer,
            text="Unofficial community project. Spotify updates might change its internal file layout.",
            bg=BG,
            fg="#8f8297",
            font=("Sans", 8),
        ).pack(anchor="w")

    def _button(self, parent: tk.Widget, text: str, command: Callable[[], None], primary: bool = False) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=PINK if primary else PANEL_HI,
            fg="#2a1724" if primary else TEXT,
            activebackground=PINK_DARK if primary else "#3c2d49",
            activeforeground="#ffffff",
            disabledforeground="#7c7184",
            relief="flat",
            bd=0,
            padx=16,
            pady=10,
            font=("Sans", 9, "bold" if primary else "normal"),
            cursor="hand2",
        )

    def _bind_click_tree(self, widget: tk.Widget, callback: Callable[[], None]) -> None:
        widget.bind("<Button-1>", lambda _event: callback(), add="+")
        for child in widget.winfo_children():
            self._bind_click_tree(child, callback)

    def _update_theme_cards(self) -> None:
        for theme in self.themes:
            card = self.theme_cards.get(theme.id)
            if card:
                selected = theme.id == self.selected_theme
                card.configure(highlightbackground=PINK if selected else BORDER, bg=PANEL_HI if selected else PANEL)
                self._recolor_tree(card, PANEL_HI if selected else PANEL)

    def _recolor_tree(self, widget: tk.Widget, color: str) -> None:
        try:
            widget.configure(bg=color)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._recolor_tree(child, color)

    def select_theme(self, theme_id: str) -> None:
        self.selected_theme = theme_id
        self._save_settings()
        self._update_theme_cards()
        theme_name = next(theme.name for theme in self.themes if theme.id == theme_id)
        self._log(f"Selected theme: {theme_name}.")

    def _save_settings(self) -> None:
        try:
            self.settings = save_settings(self.selected_theme, self.auto_apply_var.get())
        except Exception as exc:
            self._log(f"Could not save settings: {exc}")

    def on_auto_apply_changed(self) -> None:
        self._save_settings()
        enabled = self.auto_apply_var.get()
        self._log("Background auto-apply enabled." if enabled else "Background auto-apply disabled.")
        self._log("The setting takes effect when the startup monitor next checks it.")

    def _log(self, message: str) -> None:
        if not hasattr(self, "log_box"):
            return
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"• {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def refresh_status(self, log: bool = True) -> None:
        if self.archive_path and not self.archive_path.is_file():
            self.archive_path = None
        data = get_status(self.archive_path)
        self.status_data = data
        if data["found"]:
            self.archive_path = Path(data["path"])
            if data["running"]:
                label, color = "Spotify is running", RED
            elif data["patched"]:
                label, color = "Rosify theme applied", GREEN
            else:
                label, color = "Spotify detected", GREEN
            self.status_label.configure(text=f"●  {label}", fg=color)
            self.path_label.configure(text=f"Client archive: {data['path']}", fg=MUTED)
            self.status_note.configure(
                text="Close Spotify before applying or restoring. Protected install paths trigger a targeted permission prompt.",
                fg=MUTED,
            )
        else:
            self.status_label.configure(text="●  Spotify not found", fg=RED)
            self.path_label.configure(text=data["message"], fg=MUTED)
            self.status_note.configure(text="On Arch Linux, a native package often stores the archive at /opt/spotify/Apps/xpui.spa.", fg=MUTED)
        self._update_buttons()
        if log:
            self._log("Spotify status refreshed.")

    def _update_buttons(self) -> None:
        found = bool(self.status_data.get("found"))
        running = bool(self.status_data.get("running"))
        patched = bool(self.status_data.get("patched"))
        enabled = not self.busy
        self.apply_button.configure(state="normal" if enabled and found and not running else "disabled")
        self.restore_button.configure(state="normal" if enabled and found and patched and not running else "disabled")
        self.browse_button.configure(state="normal" if enabled else "disabled")
        self.refresh_button.configure(state="normal" if enabled else "disabled")

    def on_refresh(self) -> None:
        self.refresh_status()

    def on_browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Spotify's xpui.spa archive",
            filetypes=[("Spotify XPUI archive", "xpui.spa"), ("ZIP archives", "*.spa *.zip"), ("All files", "*.*")],
        )
        if not path:
            return
        selected = Path(path).expanduser()
        self.archive_path = selected
        self._log(f"Selected client archive: {selected}")
        self.refresh_status(log=False)

    def _run_task(self, label: str, worker: Callable[[], dict[str, str]], on_success: Callable[[dict[str, str]], None]) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_label.configure(text=f"●  {label}", fg=PINK)
        self._update_buttons()
        self._log(f"{label}…")

        def run() -> None:
            try:
                result = worker()
            except Exception as exc:  # Display normal operation errors in the GUI.
                message = str(exc)
                self.after(0, lambda message=message: self._task_failed(message))
            else:
                self.after(0, lambda result=result: self._task_succeeded(result, on_success))

        threading.Thread(target=run, daemon=True).start()

    def _task_failed(self, message: str) -> None:
        self.busy = False
        self._log(f"ERROR: {message}")
        self.status_label.configure(text="●  Action failed", fg=RED)
        self._update_buttons()

    def _task_succeeded(self, result: dict[str, str], callback: Callable[[dict[str, str]], None]) -> None:
        self.busy = False
        callback(result)
        self.refresh_status(log=False)
        self._update_buttons()

    def on_apply(self) -> None:
        self._save_settings()
        theme = next(theme for theme in self.themes if theme.id == self.selected_theme)
        path = str(self.archive_path) if self.archive_path else None

        def success(result: dict[str, str]) -> None:
            self._log(f"Applied {result['theme']} to {result['path']}.")
            self._log(f"Recovery backup saved at {result['backup']}.")
            self._log("Restart Spotify to see the theme. If the appearance looks wrong, use Restore backup.")

        self._run_task(f"Applying {theme.name}", lambda: apply_theme(theme.id, path), success)

    def on_restore(self) -> None:
        path = str(self.archive_path) if self.archive_path else None

        def success(result: dict[str, str]) -> None:
            self._log(f"Restored Spotify from {result['backup']}.")
            self._log("The Rosify stylesheet has been removed. Start Spotify normally.")

        self._run_task("Restoring Spotify", lambda: restore_spotify(path), success)


def run_gui() -> None:
    app = RosifyApp()
    app.mainloop()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rosify: experimental Linux Spotify theme manager")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("list-themes", help="list the three bundled themes")
    detect_parser = subparsers.add_parser("detect", help="detect Spotify's XPUI archive")
    detect_parser.add_argument("--path", help="explicit path to xpui.spa")
    apply_parser = subparsers.add_parser("apply", help="apply a bundled theme")
    apply_parser.add_argument("theme", help="theme id: cotton-candy, midnight-orchid, arctic-glass")
    apply_parser.add_argument("--path", help="explicit path to xpui.spa")
    restore_parser = subparsers.add_parser("restore", help="restore the most recent backup")
    restore_parser.add_argument("--path", help="explicit path to the same xpui.spa that was modified")
    subparsers.add_parser("monitor", help="run the background auto-apply monitor")
    return parser


def main() -> int:
    if len(sys.argv) == 1:
        run_gui()
        return 0
    args = _parser().parse_args()
    try:
        if args.command == "list-themes":
            for theme in get_themes():
                print(f"{theme.id:18} {theme.name:18} {theme.description}")
        elif args.command == "detect":
            print(json.dumps(get_status(args.path), indent=2))
            return 0 if get_status(args.path)["found"] else 1
        elif args.command == "apply":
            result = apply_theme(args.theme, args.path)
            print(f"Applied {result['theme']} to {result['path']}")
            print(f"Backup: {result['backup']}")
        elif args.command == "restore":
            result = restore_spotify(args.path)
            print(f"Restored: {result['path']}")
            print(f"Backup used: {result['backup']}")
        elif args.command == "monitor":
            monitor_auto_apply()
            return 0
        else:
            _parser().print_help()
            return 2
        return 0
    except Exception as exc:
        print(f"Rosify: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
