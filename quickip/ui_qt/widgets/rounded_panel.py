"""RoundedPanel — QFrame with per-corner radius mask for proper child clipping."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath, QRegion
from PySide6.QtWidgets import QFrame


class RoundedPanel(QFrame):
    """QFrame который клиппирует дочерние виджеты по скруглённым углам через QPainterPath."""

    def __init__(
        self,
        radius_tl: int = 14,
        radius_tr: int = 0,
        radius_br: int = 14,
        radius_bl: int = 14,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._r = (radius_tl, radius_tr, radius_br, radius_bl)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_mask()

    def _update_mask(self) -> None:
        tl, tr, br, bl = self._r
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        path = QPainterPath()
        path.moveTo(tl, 0)
        path.lineTo(w - tr, 0)
        if tr > 0:
            path.arcTo(QRectF(w - tr * 2, 0, tr * 2, tr * 2), 90, -90)
        else:
            path.lineTo(w, 0)
        path.lineTo(w, h - br)
        if br > 0:
            path.arcTo(QRectF(w - br * 2, h - br * 2, br * 2, br * 2), 0, -90)
        else:
            path.lineTo(w, h)
        path.lineTo(bl, h)
        if bl > 0:
            path.arcTo(QRectF(0, h - bl * 2, bl * 2, bl * 2), 270, -90)
        else:
            path.lineTo(0, h)
        path.lineTo(0, tl)
        if tl > 0:
            path.arcTo(QRectF(0, 0, tl * 2, tl * 2), 180, -90)
        else:
            path.lineTo(0, 0)
        path.closeSubpath()
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
