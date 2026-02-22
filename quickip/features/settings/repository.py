"""Settings repository — thin wrapper around the shared settings store."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer


class SettingsRepository:
    """Delegates to the shared JsonSettingsRepository stored in ServiceContainer.

    Provides typed accessors for language and theme so feature code
    never has to know the raw key strings.
    """

    def __init__(self, container: "ServiceContainer") -> None:
        self._repo = container.settings_repo

    def get_language(self) -> str:
        return self._repo.get("language", "ru")

    def set_language(self, lang: str) -> None:
        self._repo.set("language", lang)
        self._repo.save()

    def get_theme(self) -> str:
        return str(self._repo.get("ui_theme", "light")).lower()

    def set_theme(self, theme: str) -> None:
        self._repo.set("ui_theme", theme)
        self._repo.save()
