"""Application bootstrap – builds the dependency graph and starts the app."""

import logging
import sys
from pathlib import Path
from typing import Optional

from quickip.events.bus import EventBus, get_event_bus
from quickip.shared.logging import setup_logging
from quickip.shared.paths import get_log_dir, get_profiles_file, get_history_file, get_settings_file

# Repositories
from quickip.infrastructure.storage.json_profile_repo import JsonProfileRepository
from quickip.infrastructure.storage.json_history_repo import JsonHistoryRepository
from quickip.infrastructure.storage.json_settings_repo import JsonSettingsRepository

# Infrastructure services
from quickip.infrastructure.system.process_runner import ProcessRunner
from quickip.infrastructure.system.netsh_client import NetshClient
from quickip.infrastructure.notify.toast_service import ToastService

# Domain services
from quickip.infrastructure.services.i18n_service import I18nService

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    Dependency-injection container.

    Build once at startup; pass to presenters via constructor injection.
    This is the single composition root – nothing else does 'new ServiceX()'.
    """

    def __init__(self, icon_path: Optional[str] = None):
        # ── Event bus ────────────────────────────────────────────
        self.event_bus: EventBus = get_event_bus()

        # ── Repositories ─────────────────────────────────────────
        self.profile_repo = JsonProfileRepository(get_profiles_file())
        self.history_repo = JsonHistoryRepository(get_history_file())
        self.settings_repo = JsonSettingsRepository(get_settings_file())

        # ── Infrastructure ───────────────────────────────────────
        self.process_runner = ProcessRunner()
        self.netsh = NetshClient(self.process_runner)
        self.toast = ToastService(icon_path=icon_path)

        # ── i18n ─────────────────────────────────────────────────
        _locales_dir = str(Path(__file__).resolve().parents[2] / "data" / "locales")
        _saved_locale = str(self.settings_repo.get("ui_locale", "ru"))
        self.i18n = I18nService(locales_dir=_locales_dir, default_locale=_saved_locale)

        # ── Security ─────────────────────────────────────────────
        try:
            import win32crypt  # noqa: F401
            self.vault_available: bool = True
        except ImportError:
            self.vault_available = False

        from quickip.core.security.keyring_vault import is_available as _kr_available
        self.keyring_available: bool = _kr_available()

        logger.debug("ServiceContainer initialised")

    def get_adapters(self):
        """Convenience: return current adapter list."""
        return self.netsh.list_adapters()


def bootstrap(
    log_level: str = "INFO",
    icon_path: Optional[str] = None,
) -> "ServiceContainer":
    """
    Initialise logging, then build and return the service container.

    Call this once at application startup before creating the Tk window.
    """
    setup_logging(log_dir=get_log_dir(), log_level=log_level)
    logger.info(f"Starting Quick IP Change – Python {sys.version}")
    return ServiceContainer(icon_path=icon_path)
