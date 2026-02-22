"""Centralized theme palette – single source of truth for all UI colours."""

from __future__ import annotations


def get_palette(mode: str) -> dict[str, str]:
    """Return colour tokens for the given *mode* ('light' or 'dark')."""
    if mode == "dark":
        return {
            "primary":            "#1E3A6A",
            "hover":              "#2A4E85",
            "accent":             "#4F86E8",
            "bg":                 "#111827",
            "card":               "#1F2937",
            "card_inner":         "#243044",
            "border":             "#374151",
            "text":               "#E5E7EB",
            "text_secondary":     "#94A3B8",
            "input_bg":           "#1A2537",
            "list_bg":            "#1A2537",
            "list_text":          "#E5E7EB",
            "list_selected_bg":   "#4F86E8",
            "list_selected_text": "#FFFFFF",
            "combo_button":       "#475569",
            "combo_button_hover": "#64748B",
            "sidebar_bg":         "#162033",
            "sidebar_text":       "#CBD5E1",
            "sidebar_selected":   "#2060C8",
        }
    return {
        "primary":            "#2F5D9F",
        "hover":              "#3C6FC0",
        "accent":             "#4F86E8",
        "bg":                 "#F4F6F9",
        "card":               "#FFFFFF",
        "card_inner":         "#F8FAFC",
        "border":             "#D9DEE7",
        "text":               "#1F2937",
        "text_secondary":     "#6B7280",
        "input_bg":           "#FFFFFF",
        "list_bg":            "#F4F6F9",
        "list_text":          "#1F2937",
        "list_selected_bg":   "#4F86E8",
        "list_selected_text": "#FFFFFF",
        "combo_button":       "#CBD5E1",
        "combo_button_hover": "#94A3B8",
        "sidebar_bg":         "#EBF0F8",
        "sidebar_text":       "#374151",
        "sidebar_selected":   "#93C5FD",
    }
