"""System tray icon – minimize to tray, show/exit, active profile indicator.

Requires: pystray, Pillow (optional – falls back to a generated icon).
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import pystray
    from pystray import MenuItem as Item
    _HAS_PYSTRAY = True
except ImportError:
    _HAS_PYSTRAY = False
    pystray = None  # type: ignore

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False
    Image = ImageDraw = ImageFont = None  # type: ignore


def _generate_icon(text: str = "IP", size: int = 64) -> "Image.Image":
    """Create a simple coloured icon with text overlay."""
    if not _HAS_PIL:
        raise RuntimeError("Pillow is required for tray icon generation")

    img = Image.new("RGBA", (size, size), (30, 136, 229, 255))  # blue
    draw = ImageDraw.Draw(img)

    # Try to use a built-in font; fall back to default
    try:
        font = ImageFont.truetype("arial.ttf", size // 3)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2), text, fill="white", font=font)
    return img


def _load_icon_file(path: str) -> "Image.Image":
    """Load an .ico / .png file as a PIL Image."""
    if not _HAS_PIL:
        raise RuntimeError("Pillow is required to load icon files")
    return Image.open(path)


class TrayIcon:
    """
    Manages the system-tray icon lifecycle.

    Usage::

        tray = TrayIcon(
            on_show=lambda: root.deiconify(),
            on_exit=lambda: root.destroy(),
        )
        tray.start()
        tray.update_profile("Office")
        ...
        tray.stop()
    """

    def __init__(
        self,
        on_show: Callable[[], None],
        on_exit: Callable[[], None],
        icon_path: Optional[str] = None,
        app_name: str = "Quick IP Change",
    ) -> None:
        if not _HAS_PYSTRAY:
            logger.warning("pystray not installed – tray icon disabled")
            self._icon = None
            return

        self._on_show = on_show
        self._on_exit = on_exit
        self._app_name = app_name
        self._current_profile: str = ""
        self._thread: Optional[threading.Thread] = None

        # Build icon image
        try:
            if icon_path:
                image = _load_icon_file(icon_path)
            else:
                image = _generate_icon("IP")
        except Exception:
            logger.warning("Failed to load tray icon image, generating fallback")
            image = _generate_icon("IP")

        self._icon = pystray.Icon(
            name="quickip",
            icon=image,
            title=f"{app_name}",
            menu=self._build_menu(),
        )

    # ── Menu ─────────────────────────────────────────────────────

    def _build_menu(self) -> "pystray.Menu":
        return pystray.Menu(
            Item("Показать", self._handle_show, default=True),
            pystray.Menu.SEPARATOR,
            Item(
                lambda _: f"Профиль: {self._current_profile}" if self._current_profile else "Нет активного профиля",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            Item("Выход", self._handle_exit),
        )

    # ── Handlers ─────────────────────────────────────────────────

    def _handle_show(self, icon=None, item=None) -> None:
        self._on_show()

    def _handle_exit(self, icon=None, item=None) -> None:
        self.stop()
        self._on_exit()

    # ── Public API ───────────────────────────────────────────────

    def start(self) -> None:
        """Start the tray icon in a background daemon thread."""
        if self._icon is None:
            return
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        logger.info("Tray icon started")

    def stop(self) -> None:
        """Remove the tray icon."""
        if self._icon is None:
            return
        try:
            self._icon.stop()
        except Exception:
            pass
        logger.info("Tray icon stopped")

    def update_profile(self, profile_name: str) -> None:
        """Update the displayed active profile name in the tray tooltip."""
        self._current_profile = profile_name
        if self._icon is not None:
            self._icon.title = f"{self._app_name} – {profile_name}" if profile_name else self._app_name
            # Rebuild menu to reflect new profile name
            self._icon.menu = self._build_menu()

    def update_icon_color(self, success: bool = True) -> None:
        """Change icon colour to indicate apply success/failure."""
        if self._icon is None or not _HAS_PIL:
            return
        color = (76, 175, 80, 255) if success else (244, 67, 54, 255)  # green / red
        text = self._current_profile[:2].upper() if self._current_profile else "IP"
        img = Image.new("RGBA", (64, 64), color)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((64 - tw) / 2, (64 - th) / 2), text, fill="white", font=font)
        self._icon.icon = img

    @property
    def available(self) -> bool:
        return self._icon is not None
