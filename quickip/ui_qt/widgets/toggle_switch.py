"""ToggleSwitch — compact toggle widget, API-compatible with QCheckBox."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class ToggleSwitch(QWidget):
    """Компактный тумблер. API совместим с QCheckBox."""

    toggled = Signal(bool)

    _W, _H = 36, 20
    _M = 2

    def __init__(self, label: str = "", parent=None) -> None:
        super().__init__(parent)
        self._checked = False
        self._dark_mode = False
        self._label = label
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._H)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, state: bool) -> None:
        if self._checked == state:
            return
        self._checked = state
        self.update()

    def set_dark_mode(self, dark: bool) -> None:
        self._dark_mode = dark
        self.update()

    def mousePressEvent(self, _event) -> None:  # noqa: N802
        self._checked = not self._checked
        self.update()
        self.toggled.emit(self._checked)

    def sizeHint(self):  # noqa: N802
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self._label) + 8 if self._label else 0
        return QSize(self._W + text_w, self._H)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        on = self._checked
        m = self._M
        knob_d = self._H - m * 2

        if on:
            track_color = QColor(99, 102, 241)
            border_color = None
        else:
            if self._dark_mode:
                track_color = QColor(51, 65, 85)
                border_color = QColor(71, 85, 105)
            else:
                track_color = QColor(226, 232, 240)
                border_color = QColor(203, 213, 225)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(0, 0, self._W, self._H, self._H / 2, self._H / 2)

        if border_color:
            painter.setPen(QPen(border_color, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(0, 0, self._W, self._H, self._H / 2, self._H / 2)

        travel = self._W - self._H
        knob_x = (m + travel) if on else m
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(knob_x, m, knob_d, knob_d)

        if self._label:
            text_color = QColor(148, 163, 184) if self._dark_mode else QColor(100, 116, 139)
            painter.setPen(text_color)
            painter.setFont(self.font())
            painter.drawText(
                self._W + 8, 0,
                self.width() - self._W - 8, self._H,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._label,
            )
