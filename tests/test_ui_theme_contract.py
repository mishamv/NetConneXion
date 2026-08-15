"""Regression checks for the centralised Qt theme contract."""

from __future__ import annotations

import re

import pytest

from quickip.ui_qt.palette import color
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


@pytest.mark.parametrize(
    ("theme_mode", "text_token"),
    [("light", "LIGHT_TEXT_PRIMARY"), ("dark", "DARK_TEXT_PRIMARY")],
)
def test_adapter_tree_hover_keeps_readable_text(
    theme_mode: str,
    text_token: str,
) -> None:
    qss = load_qss(theme_mode)
    matches = re.findall(
        r"QTreeWidget#IpconfigTree::item:hover\s*\{([^}]*)\}",
        qss,
        flags=re.DOTALL,
    )

    assert matches
    expected_text = color(theme_mode, text_token)
    assert f"color: {expected_text};" in matches[-1]


@pytest.mark.parametrize(
    ("theme_mode", "selection_text_token"),
    [("light", "LIGHT_ACCENT"), ("dark", "DARK_ACCENT_TEXT")],
)
def test_adapter_tree_overrides_global_selection_text(
    theme_mode: str,
    selection_text_token: str,
) -> None:
    qss = load_qss(theme_mode)
    matches = re.findall(
        r"QTreeWidget#IpconfigTree\s*\{([^}]*)\}", qss, flags=re.DOTALL
    )

    assert matches
    expected_text = color(theme_mode, selection_text_token)
    assert any(f"selection-color: {expected_text};" in body for body in matches)
