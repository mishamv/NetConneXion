"""Reusable controls and state rendering for Tools-page panels."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyleFactory,
)

from quickip.ui_qt.widgets.copyable_views import (
    TreeSelectionDelegate,
    tree_selection_stylesheet,
)

from quickip.ui_qt.palette import color, semantic_color


TOOL_BUTTON_HEIGHT = 40
TOOL_BUTTON_MIN_WIDTH = 90


class ToolStatusKind(str, Enum):
    """Semantic states shared by every tool panel."""

    NEUTRAL = "neutral"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


def create_tool_button(
    text: str,
    *,
    role: str = "action",
    min_width: int = TOOL_BUTTON_MIN_WIDTH,
    min_height: int = TOOL_BUTTON_HEIGHT,
) -> QPushButton:
    """Create a consistently sized action button for a tool panel."""

    button = QPushButton(text)
    button.setObjectName("ToolBtn")
    button.setProperty("role", role)
    button.setMinimumSize(min_width, min_height)
    button.setSizePolicy(
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Fixed,
    )
    font = QFont("Segoe UI", 10)
    font.setWeight(QFont.Weight.DemiBold)
    button.setFont(font)
    return button


def allow_horizontal_shrink(widget) -> None:
    """Let layouts shrink a control without changing its preferred size."""

    policy = widget.sizePolicy()
    widget.setSizePolicy(
        QSizePolicy.Policy.Ignored,
        policy.verticalPolicy(),
    )


def set_tool_status(
    label: QLabel,
    text: str,
    kind: ToolStatusKind = ToolStatusKind.NEUTRAL,
) -> None:
    """Render a status message using the shared semantic palette."""

    if not text:
        label.clear()
        label.setStyleSheet("")
        label.setProperty("statusKind", ToolStatusKind.NEUTRAL.value)
        return

    token = {
        ToolStatusKind.NEUTRAL: "TEXT_MUTED_STRONG",
        ToolStatusKind.RUNNING: "TEXT_MUTED_STRONG",
        ToolStatusKind.SUCCESS: "STATUS_SUCCESS",
        ToolStatusKind.ERROR: "STATUS_ERROR",
    }[kind]
    label.setProperty("statusKind", kind.value)
    label.setStyleSheet(
        f"color: {semantic_color(token)}; font-size: 12px;"
    )
    label.setText(text)


def set_tool_busy(
    run_button: QPushButton,
    busy: bool,
    *,
    stop_button: QPushButton | None = None,
) -> None:
    """Keep Run/Stop button states consistent across tool panels."""

    run_button.setEnabled(not busy)
    if stop_button is not None:
        stop_button.setEnabled(busy)


def configure_tool_tree(
    tree,
    *,
    dark: bool,
    object_name: str = "ToolTable",
    root_decorated: bool = False,
) -> None:
    """Apply shared interaction and selection behavior to result trees."""

    tree.setObjectName(object_name)
    tree.setStyle(QStyleFactory.create("Fusion"))
    tree.setStyleSheet(tree_selection_stylesheet(dark))
    theme = "dark" if dark else "light"
    selected_text = color(
        theme,
        "DARK_CUSTOM_TREE_SELECTED_TEXT" if dark else "LIGHT_ACCENT",
    )
    tree.setItemDelegate(TreeSelectionDelegate(selected_text, tree))
    tree.setRootIsDecorated(root_decorated)
    tree.setAlternatingRowColors(True)
    tree.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows
    )
    tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tree.setUniformRowHeights(True)
    tree.header().setDefaultAlignment(
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
    )


def center_tree_item(item) -> None:
    """Center every visible cell in a result-tree row."""

    alignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
    for column in range(item.columnCount()):
        item.setTextAlignment(column, alignment)


def configure_tool_table_alignment(table) -> None:
    """Use the same centered grid alignment in every flat result table."""

    table.horizontalHeader().setDefaultAlignment(
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
    )


def center_table_item(item) -> None:
    """Center a dynamically created flat-table cell."""

    item.setTextAlignment(
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
    )
