"""Centralized theme palette – single source of truth for all UI colours."""

from __future__ import annotations


def get_palette(mode: str) -> dict[str, str]:
    """Return colour tokens for the given *mode* ('light' or 'dark')."""
    if mode == "dark":
        return {
            "primary": "#1E3A6A",
            "hover": "#2A4E85",
            "accent": "#4F86E8",
            "bg": "#111827",
            "card": "#1F2937",
            "border": "#374151",
            "text": "#E5E7EB",
            "text_secondary": "#94A3B8",
            "input_bg": "#1F2937",
            "list_bg": "#1F2937",
            "combo_button": "#475569",
            "combo_button_hover": "#64748B",
        }
    return {
        "primary": "#2F5D9F",
        "hover": "#3C6FC0",
        "accent": "#4F86E8",
        "bg": "#F4F6F9",
        "card": "#FFFFFF",
        "border": "#D9DEE7",
        "text": "#1F2937",
        "text_secondary": "#6B7280",
        "input_bg": "#FFFFFF",
        "list_bg": "#FFFFFF",
        "combo_button": "#CBD5E1",
        "combo_button_hover": "#94A3B8",
    }
