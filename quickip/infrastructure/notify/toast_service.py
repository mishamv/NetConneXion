"""Windows toast notifications via winotify (or fallback to no-op)."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import winotify; gracefully degrade if not installed.
try:
    from winotify import Notification, audio
    _HAS_WINOTIFY = True
except ImportError:
    _HAS_WINOTIFY = False
    logger.debug("winotify not installed – toast notifications disabled")


class ToastService:
    """
    Thin wrapper around winotify for Windows 10/11 toast notifications.

    If winotify is not installed the service silently does nothing,
    so the rest of the app keeps working.
    """

    APP_ID = "Quick IP Change"

    def __init__(self, icon_path: Optional[str] = None) -> None:
        self._icon = icon_path
        self._available = _HAS_WINOTIFY

    @property
    def available(self) -> bool:
        return self._available

    # ── Public API ───────────────────────────────────────────────

    def notify_profile_applied(self, profile_name: str, adapter: str = "") -> None:
        """Show a success toast after a profile is applied."""
        body = f"Профиль «{profile_name}» применён"
        if adapter:
            body += f" к {adapter}"
        self._show("Профиль применён ✅", body)

    def notify_profile_failed(self, profile_name: str, error: str = "") -> None:
        """Show an error toast when profile apply fails."""
        body = f"Не удалось применить «{profile_name}»"
        if error:
            body += f"\n{error}"
        self._show("Ошибка ❌", body)

    def notify_auto_switch(self, ssid: str, profile_name: str) -> None:
        """Notify user about automatic profile switch."""
        self._show(
            "Авто-переключение 📶",
            f"Сеть «{ssid}» → профиль «{profile_name}»",
        )

    def notify_import(self, count: int) -> None:
        """Notify about successful profile import."""
        self._show("Импорт профилей 📥", f"Импортировано профилей: {count}")

    def notify_update_available(self, version: str) -> None:
        """Notify about a new version available on GitHub."""
        self._show(
            "Доступно обновление 🔄",
            f"Версия {version} доступна для загрузки",
        )

    def notify_generic(self, title: str, body: str) -> None:
        """Show a generic toast notification."""
        self._show(title, body)

    # ── Internal ─────────────────────────────────────────────────

    def _show(self, title: str, body: str) -> None:
        if not self._available:
            logger.debug("Toast skipped (winotify unavailable): %s", title)
            return
        try:
            toast = Notification(  # type: ignore[possibly-undefined]
                app_id=self.APP_ID,
                title=title,
                msg=body,
                icon=self._icon or "",
            )
            toast.set_audio(audio.Default, loop=False)  # type: ignore[possibly-undefined]
            toast.show()
            logger.debug("Toast shown: %s", title)
        except Exception as exc:
            logger.warning("Failed to show toast: %s", exc)
