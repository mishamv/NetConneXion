"""Settings page — theme, language, update, autostart."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from quickip.app.bootstrap import ServiceContainer


class SettingsPage(QWidget):
    """Страница настроек. TODO: тема, язык, автозапуск, обновления."""

    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self._container = container
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("Settings — coming soon")
        lbl.setObjectName("PlaceholderLabel")
        lay.addWidget(lbl)

    def refresh_theme(self, dark_mode: bool) -> None:
        """Вызывается при смене темы из QtMainWindow."""
        pass
