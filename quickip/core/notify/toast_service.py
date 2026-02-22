"""Windows toast notifications via winotify (graceful no-op fallback).

No dependencies on old infrastructure layers.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from winotify import Notification, audio
    _HAS_WINOTIFY = True
except ImportError:
    _HAS_WINOTIFY = False
    logger.debug("winotify not installed — toast notifications disabled")


class ToastService:
    """Thin wrapper around winotify for Windows 10/11 toast notifications.

    Silently does nothing when winotify is unavailable.
    """

    APP_ID = "Quick IP Change"

    def __init__(self, icon_path: Optional[str] = None) -> None:
        self._icon = icon_path
        self._available = _HAS_WINOTIFY

    @property
    def available(self) -> bool:
        return self._available

    def notify_profile_applied(self, profile_name: str, adapter: str = "") -> None:
        body = f"Профиль «{profile_name}» применён"
        if adapter:
            body += f" к {adapter}"
        self._show("Профиль применён ✅", body)

    def notify_profile_failed(self, profile_name: str, error: str = "") -> None:
        body = f"Не удалось применить «{profile_name}»"
        if error:
            body += f"\n{error}"
        self._show("Ошибка ❌", body)

    def notify_auto_switch(self, ssid: str, profile_name: str) -> None:
        self._show(
            "Авто-переключение 📶",
            f"Сеть «{ssid}» → профиль «{profile_name}»",
        )

    def notify_import(self, count: int) -> None:
        self._show("Импорт профилей 📥", f"Импортировано профилей: {count}")

    def notify_update_available(self, version: str) -> None:
        self._show("Доступно обновление 🔄", f"Версия {version} доступна для загрузки")

    def notify_generic(self, title: str, body: str) -> None:
        self._show(title, body)

    def _show(self, title: str, body: str) -> None:
        if not self._available:
            logger.debug("Toast skipped (winotify unavailable): %s", title)
            return
        try:
            toast = Notification(
                app_id=self.APP_ID, title=title, msg=body, icon=self._icon or "",
            )
            toast.set_audio(audio.Default, loop=False)
            toast.show()
        except Exception as exc:
            logger.warning("Failed to show toast: %s", exc)
