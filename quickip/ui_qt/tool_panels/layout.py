"""Shared layout rules for panels shown on the Tools page."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout


TOOL_PANEL_MARGINS = (16, 14, 16, 14)
TOOL_PANEL_SPACING = 10


def configure_tool_root(
    layout: QVBoxLayout,
    *,
    spacing: int = TOOL_PANEL_SPACING,
) -> None:
    """Apply the common outer geometry used by every tool panel."""

    layout.setContentsMargins(*TOOL_PANEL_MARGINS)
    layout.setSpacing(spacing)
