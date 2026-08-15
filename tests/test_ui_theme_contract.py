"""Regression checks for the centralised Qt theme contract."""

from __future__ import annotations

import re

import pytest

from quickip.ui_qt.theme import load_qss


_UNRESOLVED_COLOR_TOKEN = re.compile(r"\{(?:LIGHT|DARK)_[A-Z0-9_]+\}")


@pytest.mark.parametrize("theme_mode", ["light", "dark"])
def test_theme_has_no_unresolved_colour_tokens(theme_mode: str) -> None:
    qss = load_qss(theme_mode)

    assert not _UNRESOLVED_COLOR_TOKEN.search(qss)


@pytest.mark.parametrize("theme_mode", ["light", "dark"])
def test_theme_styles_transient_and_interactive_states(theme_mode: str) -> None:
    qss = load_qss(theme_mode)

    required_selectors = (
        "QComboBox QAbstractItemView",
        "QComboBox::drop-down",
        "QLineEdit:disabled",
        "QPushButton:disabled",
        "QScrollBar:vertical",
        "QScrollBar::handle:vertical:hover",
        "QTableWidget#NetstatTable::item:selected",
        "QTreeWidget#NetstatTable::item:selected",
    )

    missing = [selector for selector in required_selectors if selector not in qss]
    assert not missing, f"{theme_mode} theme misses selectors: {missing}"


@pytest.mark.parametrize("theme_mode", ["light", "dark"])
def test_adapter_tree_branch_uses_row_interaction_background(theme_mode: str) -> None:
    qss = load_qss(theme_mode)
    hover = re.search(
        r"QTreeWidget#IpconfigTree::branch:hover\s*\{([^}]*)\}",
        qss,
        flags=re.DOTALL,
    )
    selected = re.search(
        r"QTreeWidget#IpconfigTree::branch:selected,[^{]+\{([^}]*)\}",
        qss,
        flags=re.DOTALL,
    )

    assert hover and "background: transparent" not in hover.group(1)
    assert selected and "background: transparent" not in selected.group(1)
