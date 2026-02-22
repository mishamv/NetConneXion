"""Main window – thin shell that wires views, presenters and ServiceContainer."""

from __future__ import annotations

import logging
import os
import sys
import tkinter as tk
from typing import Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

from quickip.app.bootstrap import bootstrap, ServiceContainer
from quickip.ui.theme import get_palette
from quickip.ui.profiles_view import ProfilesView
from quickip.ui.history_view import HistoryView
from quickip.ui.tools_view import ToolsView
from quickip.ui.auto_switch_view import AutoSwitchView
from quickip.ui.dashboard_view import DashboardView

from quickip.presenters.profiles_presenter import ProfilesPresenter
from quickip.presenters.history_presenter import HistoryPresenter
from quickip.presenters.tools_presenter import ToolsPresenter
from quickip.presenters.auto_switch_presenter import AutoSwitchPresenter
from quickip.presenters.settings_presenter import SettingsPresenter
from quickip.infrastructure.tray.tray_icon import TrayIcon

logger = logging.getLogger(__name__)


def _ensure_admin() -> None:
    """On Windows, restart elevated if not admin."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            sys.exit(0)
    except Exception:
        pass


class MainWindow(ctk.CTk if ctk is not None else tk.Tk):
    """
    Application shell.

    Responsibilities:
    - Build sidebar + topbar + content area
    - Instantiate views and presenters
    - Wire cross-view refresh callbacks
    - Manage theme switching
    """

    def __init__(self) -> None:
        _ensure_admin()
        super().__init__()

        # ── Bootstrap services ───────────────────────────────────
        icon_path = self._find_icon_path()
        self.container: ServiceContainer = bootstrap(icon_path=icon_path)

        # ── Theme ────────────────────────────────────────────────
        saved_theme = str(self.container.settings_repo.get("ui_theme", "light")).lower()
        self.theme_mode = saved_theme
        self.colors = get_palette(self.theme_mode)
        ctk.set_appearance_mode(self.theme_mode)
        ctk.set_default_color_theme("blue")

        # ── Window setup ─────────────────────────────────────────
        self.title(self.container.i18n.get("app_title"))
        self.geometry("1320x820")
        self.configure(fg_color=self.colors["bg"])

        # ── Build shell ──────────────────────────────────────────
        self._build_shell()

        # ── Create views ─────────────────────────────────────────
        # Settings view needs access to i18n + settings repo → pass ServiceContainer
        self.settings_view = DashboardView(self.section_frames["settings"], self.colors, self.container)
        self.profiles_view = ProfilesView(self.section_frames["network"], self.colors, self)
        self.wifi_view = AutoSwitchView(self.section_frames["wifi"], self.colors, self)
        self.history_view = HistoryView(self.section_frames["history"], self.colors, self)
        self.tools_view = ToolsView(self.section_frames["tools"], self.colors, self)

        # ── Create presenters ────────────────────────────────────
        self.profiles_presenter = ProfilesPresenter(self.container, self.profiles_view)
        self.history_presenter = HistoryPresenter(self.container, self.history_view)
        self.tools_presenter = ToolsPresenter(self.container, self.tools_view)
        self.auto_switch_presenter = AutoSwitchPresenter(
            self.container, self.wifi_view,
            get_profiles=self.profiles_presenter.get_profiles,
        )
        self.settings_presenter = SettingsPresenter(self.settings_view, self.container)

        # ── Bind presenters to views ─────────────────────────────
        self.profiles_view.bind_presenter(self.profiles_presenter)
        self.history_view.bind_presenter(self.history_presenter)
        self.tools_view.bind_presenter(self.tools_presenter)
        self.wifi_view.bind_presenter(self.auto_switch_presenter)
        self.settings_view.bind_presenter(self.settings_presenter)

        # ── Wire cross-view callbacks ────────────────────────────
        self._wire_cross_view()

        # ── Initial data load ────────────────────────────────────
        self._apply_theme_ui()
        self.profiles_presenter.load_initial()
        self.settings_presenter.refresh_home_snapshot()
        self.history_presenter.refresh()
        self.auto_switch_presenter.refresh_mappings()
        self.auto_switch_presenter.refresh_current_ssid()
        self.auto_switch_presenter.refresh_visible_networks()
        self.auto_switch_presenter.start_polling()

        # ── Tray icon ─────────────────────────────────────────────
        self._tray = TrayIcon(
            on_show=self._tray_show,
            on_exit=self._tray_exit,
            icon_path=self._find_icon_path(),
        )
        self._tray.start()

        # ── Minimize to tray on close ────────────────────────────
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._switch_section("network")

    # ── Shell layout ─────────────────────────────────────────────

    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=76, fg_color=self.colors["primary"], corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Topbar
        self.topbar = ctk.CTkFrame(self, fg_color=self.colors["primary"], corner_radius=0, height=56)
        self.topbar.grid(row=0, column=1, sticky="ew")
        self.topbar.grid_columnconfigure(0, weight=1)

        title_block = ctk.CTkFrame(self.topbar, fg_color="transparent")
        title_block.grid(row=0, column=0, padx=16, pady=8, sticky="w")
        self.section_title = ctk.CTkLabel(
            title_block, text="Сеть", text_color="white",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.section_title.grid(row=0, column=0, sticky="w")

        # Content area
        self.content = ctk.CTkFrame(self, fg_color=self.colors["bg"], corner_radius=0)
        self.content.grid(row=1, column=1, sticky="nsew", padx=12, pady=12)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # Section frames
        self.section_frames: dict[str, tk.Widget] = {}
        self.section_frames["settings"] = ctk.CTkFrame(self.content, fg_color=self.colors["card"], corner_radius=8)
        self.section_frames["network"] = ctk.CTkFrame(self.content, fg_color=self.colors["bg"], corner_radius=0)
        self.section_frames["wifi"] = ctk.CTkFrame(self.content, fg_color=self.colors["card"], corner_radius=8)
        self.section_frames["history"] = ctk.CTkFrame(self.content, fg_color=self.colors["card"], corner_radius=8)
        self.section_frames["tools"] = ctk.CTkFrame(self.content, fg_color=self.colors["card"], corner_radius=8)

        # Nav buttons
        self.nav_buttons: dict[str, tk.Widget] = {}
        nav = [
            ("network", "🌐"),
            ("wifi", "📶"),
            ("history", "📜"),
            ("tools", "🛠"),
            ("settings", "⚙️"),
        ]
        for idx, (key, icon) in enumerate(nav):
            btn = ctk.CTkButton(
                self.sidebar, text=icon, width=64, height=56,
                fg_color="transparent", hover_color=self.colors["hover"],
                corner_radius=0, command=lambda s=key: self._switch_section(s),
                font=ctk.CTkFont(size=22),
            )
            btn.grid(row=idx, column=0, padx=6, pady=2)
            self.nav_buttons[key] = btn

    # ── Section switching ────────────────────────────────────────

    _SECTION_TITLES = {
        "network": "Сеть / Network",
        "wifi": "Wi-Fi Auto-Switch",
        "history": "История / History",
        "tools": "Инструменты / Tools",
        "settings": "Настройки / Settings",
    }

    def _switch_section(self, section: str) -> None:
        for frame in self.section_frames.values():
            frame.grid_forget()
        self.section_frames[section].grid(row=0, column=0, sticky="nsew")
        self.section_title.configure(text=self._SECTION_TITLES.get(section, section))
        self._update_nav_state(section)

    def _update_nav_state(self, active: str) -> None:
        for key, btn in self.nav_buttons.items():
            btn.configure(fg_color=self.colors["hover"] if key == active else "transparent")

    # ── Cross-view wiring ────────────────────────────────────────

    def _wire_cross_view(self) -> None:
        """Connect refresh callbacks across views."""

        def _refresh_all() -> None:
            self.settings_presenter.refresh_home_snapshot()
            self.history_presenter.refresh()
            self.auto_switch_presenter.refresh_mappings()

        self.profiles_view.refresh_related_panels = _refresh_all
        self.history_view.refresh_related_panels = _refresh_all
        self.wifi_view.refresh_related_panels = _refresh_all

        # Sync wifi profile combo when profiles change
        def _update_wifi_combo(names):
            self.wifi_view.set_profile_values(names)

        self.profiles_view.update_wifi_profile_combo = _update_wifi_combo

        # Wire network info target
        self.settings_view.set_network_info_target(self.profiles_view.current_net_text)

        # Wire theme toggle
        self.settings_view.set_theme_toggle_callback(self._set_theme)

    # ── Theme ────────────────────────────────────────────────────

    def _set_theme(self, mode: str) -> None:
        self.theme_mode = mode
        self.colors = get_palette(mode)
        ctk.set_appearance_mode(mode)
        self._apply_theme_ui()

    def _apply_theme_ui(self) -> None:
        c = self.colors
        self.configure(fg_color=c["bg"])
        self.content.configure(fg_color=c["bg"])
        self.sidebar.configure(fg_color=c["primary"])
        self.topbar.configure(fg_color=c["primary"])

        # Update section frame backgrounds
        self.section_frames["settings"].configure(fg_color=c["card"])
        self.section_frames["network"].configure(fg_color=c["bg"])
        self.section_frames["wifi"].configure(fg_color=c["card"])
        self.section_frames["history"].configure(fg_color=c["card"])
        self.section_frames["tools"].configure(fg_color=c["card"])

        # Propagate to views
        for view in (self.settings_view, self.profiles_view, self.history_view,
                     self.tools_view, self.wifi_view):
            if hasattr(view, "update_colors"):
                view.update_colors(c)

        # Re-theme labels recursively
        self._retheme_labels_recursive(self, c["text"])

    def _retheme_labels_recursive(self, parent: tk.Widget, text_color: str) -> None:
        for child in parent.winfo_children():
            if ctk is not None and isinstance(child, ctk.CTkLabel):
                try:
                    child.configure(text_color=text_color)
                except Exception:
                    pass
            self._retheme_labels_recursive(child, text_color)


    # ── Tray helpers ─────────────────────────────────────────────

    @staticmethod
    def _find_icon_path() -> Optional[str]:
        """Locate app.ico relative to the project root."""
        import pathlib
        candidates = [
            pathlib.Path(__file__).resolve().parent.parent.parent / "app.ico",
            pathlib.Path("app.ico"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    def _on_close(self) -> None:
        """Minimize to tray instead of quitting."""
        if self._tray.available:
            self.withdraw()
        else:
            self._shutdown()

    def _tray_show(self) -> None:
        """Restore window from tray."""
        self.after(0, self.deiconify)

    def _tray_exit(self) -> None:
        """Full shutdown from tray menu."""
        self.after(0, self._shutdown)

    def _shutdown(self) -> None:
        """Clean shutdown: stop polling, tray, destroy window."""
        try:
            self.auto_switch_presenter.stop_polling()
        except Exception:
            pass
        try:
            self._tray.stop()
        except Exception:
            pass
        self.destroy()

    def notify_profile_applied(self, profile_name: str, success: bool = True) -> None:
        """Called after a profile is applied – update tray indicator + toast."""
        self._tray.update_profile(profile_name)
        self._tray.update_icon_color(success)
        if success:
            self.container.toast.notify_profile_applied(profile_name)
        else:
            self.container.toast.notify_profile_failed(profile_name)


def main() -> None:
    """Entry point."""
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        print("GUI cannot be started: no display is available.")
        sys.exit(1)
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
