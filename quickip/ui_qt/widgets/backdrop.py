"""BackdropWidget — solid colour background for the root window."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from quickip.ui_qt.palette import color

class BackdropWidget(QWidget):
    """Solid colour background matching the approved render."""

    def __init__(self) -> None:
        super().__init__()
        self._theme_mode = "dark"

    def set_theme_mode(self, mode: str) -> None:
        self._theme_mode = (mode or "dark").lower()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        if self._theme_mode == "light":
            painter.fillRect(self.rect(), QColor(color("light", "LIGHT_PANEL_BG")))
        else:
            painter.fillRect(self.rect(), QColor(color("dark", "DARK_CUSTOM_BACKDROP")))
