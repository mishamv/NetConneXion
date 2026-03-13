"""Main window — thin shell that wires feature views, presenters and ServiceContainer."""

from __future__ import annotations

import logging
import os
import pathlib
import sys
import tkinter as tk
from typing import Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

from quickip.app.bootstrap import bootstrap, ServiceContainer
from quickip.core.ui.theme import get_palette
from quickip.core.tray.tray_icon import TrayIcon

# ── Feature views (stubs in Step 2, replaced in Steps 3–7) ───────────────────
from quickip.features.profiles.view import ProfilesView
from quickip.features.history.view import HistoryView
from quickip.features.tools.view.tools_view import ToolsView
from quickip.features.wifi.view.wifi_view import WifiView
from quickip.features.settings.view import SettingsView

# ── Feature presenters (stubs in Step 2, replaced in Steps 3–7) ──────────────
from quickip.features.profiles.presenter import ProfilesPresenter
from quickip.features.history.presenter import HistoryPresenter
from quickip.features.tools.presenter import ToolsPresenter
from quickip.features.wifi.presenter import WifiPresenter
from quickip.features.settings.presenter import SettingsPresenter

logger = logging.getLogger(__name__)


def _ensure_admin() -> None:
    """On Windows, restart elevated if not already running as administrator."""
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


_BASE = ctk.CTk if ctk is not None else tk.Tk


class MainWindow(_BASE):  # type: ignore[misc]
    """Application shell.

    Responsibilities:
    - Build sidebar + topbar + content area
    - Instantiate feature presenters and views
    - Manage theme switching
    - Manage tray icon lifecycle
    """

    _SECTION_I18N_KEYS = {
        "network":  "section_network",
        "wifi":     "section_wifi",
        "history":  "section_history",
        "tools":    "section_tools",
        "settings": "section_settings",
    }

    def __init__(self) -> None:
        _ensure_admin()
        super().__init__()

        # ── 1. Bootstrap services ─────────────────────────────────
        icon_path = self._find_icon_path()
        self.container: ServiceContainer = bootstrap(icon_path=icon_path)

        # ── 2. Theme ──────────────────────────────────────────────
        saved_theme = str(self.container.settings_repo.get("ui_theme", "light")).lower()
        self.theme_mode = saved_theme
        self.colors = get_palette(self.theme_mode)
        if ctk is not None:
            ctk.set_appearance_mode(self.theme_mode)
            ctk.set_default_color_theme("blue")

        # ── 3. Window setup ───────────────────────────────────────
        self.title(self.container.i18n.get("app_title"))
        self.geometry("1320x820")
        self.configure(fg_color=self.colors["bg"])

        # ── 4. Build shell (sidebar + topbar + content frames) ────
        self._build_shell()

        # ── 5. Create presenters first ────────────────────────────
        self.profiles_presenter = ProfilesPresenter(self.container)
        self.history_presenter  = HistoryPresenter(self.container)
        self.tools_presenter    = ToolsPresenter(self.container)
        self.wifi_presenter     = WifiPresenter(self.container)
        self.settings_presenter = SettingsPresenter(self.container)

        # ── 6. Create views, pass presenter ───────────────────────
        self.profiles_view = ProfilesView(self.section_frames["network"],  self.profiles_presenter)
        self.history_view  = HistoryView(self.section_frames["history"],   self.history_presenter)
        self.tools_view    = ToolsView(self.section_frames["tools"],       self.tools_presenter)
        self.wifi_view     = WifiView(self.section_frames["wifi"],         self.wifi_presenter)
        self.settings_view = SettingsView(self.section_frames["settings"], self.settings_presenter)

        # ── 7. Pack views ─────────────────────────────────────────
        for view in (self.profiles_view, self.history_view, self.tools_view,
                     self.wifi_view, self.settings_view):
            view.pack(fill="both", expand=True)

        # ── 8. Apply theme to all widgets ─────────────────────────
        self._apply_theme_ui()

        # ── 9. Tray icon ──────────────────────────────────────────
        self._tray = TrayIcon(
            on_show=self._tray_show,
            on_exit=self._tray_exit,
            icon_path=icon_path,
        )
        self._tray.start()

        # ── 10. Minimize to tray on window close ──────────────────
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── 11. Show initial section ──────────────────────────────
        self._switch_section("network")

    # ── Shell layout ──────────────────────────────────────────────────────────

    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(
            self, width=76, fg_color=self.colors["primary"], corner_radius=0
        )
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Topbar
        self.topbar = ctk.CTkFrame(
            self, fg_color=self.colors["primary"], corner_radius=0, height=56
        )
        self.topbar.grid(row=0, column=1, sticky="ew")
        self.topbar.grid_columnconfigure(0, weight=1)

        title_block = ctk.CTkFrame(self.topbar, fg_color="transparent")
        title_block.grid(row=0, column=0, padx=16, pady=8, sticky="w")
        self.section_title = ctk.CTkLabel(
            title_block,
            text="",
            text_color="white",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.section_title.grid(row=0, column=0, sticky="w")

        # Logo (right side of topbar)
        self._logo_label = self._load_logo(self.topbar)
        if self._logo_label:
            self._logo_label.grid(row=0, column=1, padx=16, pady=8, sticky="e")

        # Content area
        self.content = ctk.CTkFrame(self, fg_color=self.colors["bg"], corner_radius=0)
        self.content.grid(row=1, column=1, sticky="nsew", padx=12, pady=12)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # Section frames (one per nav tab)
        self.section_frames: dict[str, tk.Widget] = {
            "network":  ctk.CTkFrame(self.content, fg_color=self.colors["bg"],   corner_radius=0),
            "wifi":     ctk.CTkFrame(self.content, fg_color=self.colors["card"], corner_radius=8),
            "history":  ctk.CTkFrame(self.content, fg_color=self.colors["card"], corner_radius=8),
            "tools":    ctk.CTkFrame(self.content, fg_color=self.colors["card"], corner_radius=8),
            "settings": ctk.CTkFrame(self.content, fg_color=self.colors["card"], corner_radius=8),
        }

        # Sidebar nav buttons
        nav = [
            ("network",  "🌐"),
            ("wifi",     "📶"),
            ("history",  "📜"),
            ("tools",    "🛠"),
            ("settings", "⚙️"),
        ]
        self.nav_buttons: dict[str, tk.Widget] = {}
        for idx, (key, icon) in enumerate(nav):
            btn = ctk.CTkButton(
                self.sidebar,
                text=icon,
                width=64,
                height=56,
                fg_color="transparent",
                hover_color=self.colors["hover"],
                text_color=self.colors.get("sidebar_text", "#FFFFFF"),
                corner_radius=12,
                command=lambda s=key: self._switch_section(s),
                font=ctk.CTkFont(size=22),
            )
            btn.grid(row=idx, column=0, padx=6, pady=2)
            self.nav_buttons[key] = btn

    # ── Section switching ─────────────────────────────────────────────────────

    def _switch_section(self, section: str) -> None:
        for frame in self.section_frames.values():
            frame.grid_forget()
        self.section_frames[section].grid(row=0, column=0, sticky="nsew")
        i18n_key = self._SECTION_I18N_KEYS.get(section, section)
        self.section_title.configure(text=self.container.i18n.get(i18n_key))
        self._update_nav_state(section)
        if section == "wifi" and hasattr(self, "wifi_view"):
            self.wifi_view.on_tab_enter()

    def _update_nav_state(self, active: str) -> None:
        for key, btn in self.nav_buttons.items():
            btn.configure(
                fg_color=self.colors["hover"] if key == active else "transparent",
                hover_color=self.colors["hover"],
                text_color=self.colors.get("sidebar_text", "#FFFFFF"),
                corner_radius=12,
            )

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _set_theme(self, mode: str) -> None:
        self.theme_mode = mode
        self.colors = get_palette(mode)
        if ctk is not None:
            ctk.set_appearance_mode(mode)
        self._apply_theme_ui()

    def _apply_theme_ui(self) -> None:
        c = self.colors
        self.configure(fg_color=c["bg"])
        self.content.configure(fg_color=c["bg"])
        self.sidebar.configure(fg_color=c.get("sidebar_bg", c["primary"]))
        self.topbar.configure(fg_color=c.get("header_bg", c["primary"]))

        # Update section frame backgrounds
        self.section_frames["network"].configure(
            fg_color=c["card"],
            border_width=1,
            border_color=c.get("card_border", c["border"]),
            corner_radius=int(c.get("card_radius", 8)),
        )
        for key in ("wifi", "history", "tools", "settings"):
            self.section_frames[key].configure(
                fg_color=c["card"],
                border_width=1,
                border_color=c.get("card_border", c["border"]),
                corner_radius=int(c.get("card_radius", 8)),
            )

        self.section_title.configure(text_color=c.get("header_text", "#FFFFFF"))

        # Propagate to views that support color updates
        for view in (self.profiles_view, self.history_view,
                     self.tools_view, self.wifi_view, self.settings_view):
            if hasattr(view, "update_colors"):
                view.update_colors(c)

        self._retheme_labels_recursive(self.content, c["text"])

    def _retheme_labels_recursive(self, parent: tk.Widget, text_color: str) -> None:
        for child in parent.winfo_children():
            if ctk is not None and isinstance(child, ctk.CTkLabel):
                try:
                    child.configure(text_color=text_color)
                except Exception:
                    pass
            self._retheme_labels_recursive(child, text_color)

    # ── Tray helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _find_icon_path() -> Optional[str]:
        """Locate app.ico relative to the project root."""
        candidates = [
            pathlib.Path(__file__).resolve().parent.parent.parent / "app.ico",
            pathlib.Path("app.ico"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    @staticmethod
    def _find_logo_path() -> Optional[str]:
        """Locate Full_logo.png relative to the project root."""
        candidates = [
            pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "Full_logo.png",
            pathlib.Path(__file__).resolve().parent.parent.parent / "Full_logo.png",
            pathlib.Path("data") / "Full_logo.png",
            pathlib.Path("Full_logo.png"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    def _load_logo(self, parent: tk.Widget) -> Optional[tk.Widget]:
        """Load the app logo into a white card that stands out on the topbar."""
        logo_path = self._find_logo_path()
        if logo_path is None:
            return None
        try:
            from PIL import Image
            img = Image.open(logo_path).convert("RGBA")
            # Remove near-white background
            data = img.getdata()
            img.putdata([
                (r, g, b, 0) if (r > 230 and g > 230 and b > 230) else (r, g, b, a)
                for r, g, b, a in data
            ])
            # Crop to content bounds (removes transparent padding)
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
            # Scale to fit topbar height
            target_h = 34
            target_w = int(img.width * target_h / img.height)
            resample = getattr(Image, "Resampling", Image).LANCZOS
            img = img.resize((target_w, target_h), resample)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(target_w, target_h))
            # White card so logo is visible on any topbar color
            card = ctk.CTkFrame(parent, fg_color="#FFFFFF", corner_radius=8)
            ctk.CTkLabel(card, image=ctk_img, text="", fg_color="transparent").pack(
                padx=10, pady=6,
            )
            return card
        except Exception:
            logger.debug("Logo could not be loaded", exc_info=True)
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
        """Full shutdown triggered from tray menu."""
        self.after(0, self._shutdown)

    def _shutdown(self) -> None:
        """Clean shutdown: stop tray, destroy window."""
        try:
            self._tray.stop()
        except Exception:
            pass
        self.destroy()

    def notify_profile_applied(self, profile_name: str, success: bool = True) -> None:
        """Update tray indicator + send toast after a profile is applied."""
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
