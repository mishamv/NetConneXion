"""Settings presenter — handles theme, language, and dashboard network snapshot.

Updated for hybrid migration: now also handles dashboard network info display.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Protocol

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer


class ISettingsView(Protocol):
    """View interface for settings/dashboard presenter."""
    
    def show_message(self, title: str, message: str) -> None: ...
    def show_error(self, message: str) -> None: ...
    def set_network_snapshot(self, text: str) -> None: ...  # For dashboard


class SettingsPresenter:
    """Presenter for settings/dashboard view.
    
    Responsibilities:
    - Theme changes (persisted to settings)
    - Language changes (persisted + requires app restart)
    - Network snapshot display (ipconfig + netsh output)
    """

    def __init__(self, view: ISettingsView, container: ServiceContainer) -> None:
        self.view = view
        self.container = container

    def change_theme(self, theme: str) -> None:
        """Handle theme change request."""
        theme_norm = str(theme).strip().lower()
        mode = "dark" if theme_norm in {"dark", "тёмная", "темная"} else "light"

        # Persist preference
        try:
            self.container.settings_repo.set("ui_theme", mode)
            self.container.settings_repo.save()
        except Exception:
            pass

        # Note: actual UI re-theming is handled by MainWindow/AppHybrid
        # because it requires full widget tree rebuild

    def change_language(self, locale_code: str) -> None:
        """Handle language change request."""
        self.container.i18n.set_locale(locale_code)
        
        # Persist preference
        self.container.settings_repo.set("language", locale_code)
        self.container.settings_repo.save()
        
        # Notify user that restart is needed for full effect
        msg = self.container.i18n.get("msg_restart_lang")
        success_title = self.container.i18n.get("success")
        try:
            self.view.show_message(success_title, msg)
        except Exception:
            pass

    def refresh_home_snapshot(self) -> None:
        """Load and display current network configuration (ipconfig + netsh)."""
        # Import ip_changer's snapshot function
        try:
            from ip_changer import get_network_snapshot
            snapshot_text = get_network_snapshot()
            self.view.set_network_snapshot(snapshot_text)
        except Exception as e:
            error_text = f"Failed to load network snapshot: {e}"
            self.view.set_network_snapshot(error_text)
