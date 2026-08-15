"""Table and tree views with clipboard-friendly selection."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QMenu,
    QTableWidget,
    QTreeWidget,
    QTreeWidgetItem,
)


from quickip.ui_qt.palette import color


_COPY_ACTION_FALLBACKS = {
    "ui_copy_cell": "Copy cell",
    "ui_copy_row": "Copy row",
    "ui_copy_selection": "Copy selection",
    "ui_copy_all": "Copy all",
}


def _copy_action_text(i18n, key: str) -> str:
    if i18n is None:
        return _COPY_ACTION_FALLBACKS[key]
    translated = i18n.get(key)
    return translated if translated != key else _COPY_ACTION_FALLBACKS[key]


def tree_selection_stylesheet(dark: bool) -> str:
    """Return hover and selection colors for copyable tree views."""
    if dark:
        hover = color("dark", "DARK_CUSTOM_TREE_HOVER")
        hover_text = color("dark", "DARK_CUSTOM_TREE_HOVER_TEXT")
        selected = color("dark", "DARK_CUSTOM_TREE_SELECTED")
        selected_text = color("dark", "DARK_CUSTOM_TREE_SELECTED_TEXT")
    else:
        hover = color("light", "LIGHT_STATE_ACTIVE_BG")
        hover_text = color("light", "LIGHT_TEXT_PRIMARY")
        selected = color("light", "LIGHT_RGBA_99_102_241_0_12")
        selected_text = color("light", "LIGHT_ACCENT")

    return f"""
QTreeWidget::item:hover {{
    background: {hover};
    color: {hover_text};
}}
QTreeWidget::item:selected,
QTreeWidget::item:selected:active,
QTreeWidget::item:selected:!active {{
    background: {selected};
    color: {selected_text};
}}
"""


class CopyableTree(QTreeWidget):
    """QTreeWidget with Ctrl+C copy and a right-click context menu."""

    def __init__(self, parent=None, i18n=None):
        super().__init__(parent)
        self._i18n = i18n
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)

    def keyPressEvent(self, event) -> None:
        modifiers = event.modifiers()
        key = event.key()
        if key == Qt.Key.Key_C and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._copy_selection()
        elif key == Qt.Key.Key_A and modifiers == Qt.KeyboardModifier.ControlModifier:
            self.selectAll()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is None:
            return

        menu = QMenu(self)
        column = self.currentColumn()
        copy_cell = menu.addAction(
            _copy_action_text(self._i18n, "ui_copy_cell")
        )
        copy_row = menu.addAction(
            _copy_action_text(self._i18n, "ui_copy_row")
        )
        copy_selection = menu.addAction(
            _copy_action_text(self._i18n, "ui_copy_selection")
        )
        copy_all = menu.addAction(
            _copy_action_text(self._i18n, "ui_copy_all")
        )
        chosen = menu.exec(event.globalPos())

        if chosen == copy_cell:
            QApplication.clipboard().setText(item.text(column if column >= 0 else 0))
        elif chosen == copy_row:
            texts = [item.text(index) for index in range(self.columnCount())]
            QApplication.clipboard().setText("\t".join(texts))
        elif chosen == copy_selection:
            self._copy_selection()
        elif chosen == copy_all:
            self.selectAll()
            self._copy_selection()

    def _copy_selection(self) -> None:
        items = self.selectedItems()
        if not items:
            return

        # selectedItems() can return multiple cells from the same row.
        rows: dict[int, QTreeWidgetItem] = {}
        for item in items:
            row = self.indexOfTopLevelItem(item)
            if row >= 0:
                rows[row] = item

        lines = [
            "\t".join(rows[row].text(column) for column in range(self.columnCount()))
            for row in sorted(rows)
        ]
        QApplication.clipboard().setText("\n".join(lines))


class CopyableTable(QTableWidget):
    """QTableWidget with Ctrl+C copy and a right-click context menu."""

    def __init__(self, *args, i18n=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._i18n = i18n
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)

    def keyPressEvent(self, event) -> None:
        modifiers = event.modifiers()
        key = event.key()
        if key == Qt.Key.Key_C and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._copy_selection()
        elif key == Qt.Key.Key_A and modifiers == Qt.KeyboardModifier.ControlModifier:
            self.selectAll()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        index = self.indexAt(event.pos())
        if not index.isValid():
            return

        menu = QMenu(self)
        copy_cell = menu.addAction(
            _copy_action_text(self._i18n, "ui_copy_cell")
        )
        copy_row = menu.addAction(
            _copy_action_text(self._i18n, "ui_copy_row")
        )
        copy_selection = menu.addAction(
            _copy_action_text(self._i18n, "ui_copy_selection")
        )
        copy_all = menu.addAction(
            _copy_action_text(self._i18n, "ui_copy_all")
        )
        chosen = menu.exec(event.globalPos())

        if chosen == copy_cell:
            item = self.item(index.row(), index.column())
            QApplication.clipboard().setText(item.text() if item else "")
        elif chosen == copy_row:
            texts = [
                self.item(index.row(), column).text()
                if self.item(index.row(), column)
                else ""
                for column in range(self.columnCount())
            ]
            QApplication.clipboard().setText("\t".join(texts))
        elif chosen == copy_selection:
            self._copy_selection()
        elif chosen == copy_all:
            self.selectAll()
            self._copy_selection()

    def _copy_selection(self) -> None:
        ranges = self.selectedRanges()
        if not ranges:
            return

        rows = sorted(
            {
                row
                for selected_range in ranges
                for row in range(selected_range.topRow(), selected_range.bottomRow() + 1)
            }
        )
        lines = []
        for row in rows:
            texts = []
            for column in range(self.columnCount()):
                item = self.item(row, column)
                texts.append(item.text() if item else "")
            lines.append("\t".join(texts))
        QApplication.clipboard().setText("\n".join(lines))
