"""Qt QSS theming for the parallel PySide6 UI."""

from __future__ import annotations

import sys
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


def _resource_root() -> Path:
    """Корень для поиска ресурсов.

    PyInstaller frozen: sys._MEIPASS (распакованные файлы).
    Dev-режим: три уровня выше theme.py (корень проекта).
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent.parent.parent


def load_qss(theme_mode: str) -> str:
    root = _resource_root()
    base = root / "quickip" / "ui_qt" / "qss" / "base.qss"
    dark = root / "quickip" / "ui_qt" / "qss" / "dark.qss"
    # Fallback: рядом с theme.py
    if not base.exists():
        base = Path(__file__).with_name("qss") / "base.qss"
        dark = Path(__file__).with_name("qss") / "dark.qss"
    qss = base.read_text(encoding="utf-8")
    if theme_mode.lower() == "dark" and dark.exists():
        qss += "\n\n" + dark.read_text(encoding="utf-8")
    # Inject absolute assets path for url() references
    assets_dir = str((root / "quickip" / "ui_qt" / "assets").resolve()).replace("\\", "/")
    qss = qss.replace("{ASSETS}", assets_dir)
    return qss
