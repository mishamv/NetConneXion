"""Qt QSS theming for the parallel PySide6 UI."""

from __future__ import annotations

from pathlib import Path


THEME_TOKENS = {
    "light": {
        "mode": "light",
        "background": "deep_blue_gradient",
        "card": "frost_light",
    },
    "dark": {
        "mode": "dark",
        "background": "deep_blue_gradient_dark",
        "card": "frost_dark",
    },
}


def load_qss(theme_mode: str) -> str:
    base = Path(__file__).with_name("qss") / "base.qss"
    dark = Path(__file__).with_name("qss") / "dark.qss"
    qss = base.read_text(encoding="utf-8")
    if theme_mode.lower() == "dark" and dark.exists():
        qss += "\n\n" + dark.read_text(encoding="utf-8")
    return qss
