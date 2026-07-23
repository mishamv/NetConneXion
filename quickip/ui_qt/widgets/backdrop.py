"""BackdropWidget — solid colour background for the root window."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class BackdropWidget(QWidget):
    """Solid color background. Dark: #0F172A slate. Light: #F1F5F9."""

    def __init__(self) -> None:
        super().__init__()
        self._theme_mode = "dark"

    def set_theme_mode(self, mode: str) -> None:
        self._theme_mode = (mode or "dark").lower()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        if self._theme_mode == "light":
            painter.fillRect(self.rect(), QColor("#F1F5F9"))  # light: slate-100
        else:
            painter.fillRect(self.rect(), QColor("#12141c"))  # dark: design bg
