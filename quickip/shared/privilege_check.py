"""Windows privilege and elevation detection utilities.

Used at startup to detect whether the process has the elevated token needed
for netsh interface/wlan operations, and to provide actionable error messages
when running with a filtered (non-elevated) admin token.

Background — Windows UAC split token:
  When an administrator logs in, Windows creates TWO tokens:
    1. Filtered token  — non-elevated, standard user rights.
    2. Full token      — elevated, administrative rights.

  "Run as different user" (Shift+right-click) hands the program the FILTERED
  token of the target account — even if that account is an Administrator.
  Netsh operations that modify network configuration (interface ip set address,
  wlan add profile, etc.) require the FULL elevated token.

  "Run as administrator" with credentials creates a new elevated session and
  gives the FULL token.  This is what NetConneXion requires for full functionality.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def is_elevated() -> bool:
    """Return True if the current process has a full elevated token (Windows).

    Returns True on non-Windows platforms (no concept of elevation).
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        logger.debug("Could not check elevation status", exc_info=True)
        return False


def get_current_username() -> str:
    """Return the username of the account running this process."""
    if sys.platform != "win32":
        import os
        return os.environ.get("USER", "unknown")
    try:
        import os
        return os.environ.get("USERNAME", "unknown")
    except Exception:
        return "unknown"


def check_elevation_warning() -> str | None:
    """Return a warning string if running without elevation, else None.

    Intended to be shown at startup in the UI status bar or as a dialog.
    """
    if sys.platform != "win32":
        return None
    if is_elevated():
        return None

    username = get_current_username()
    return (
        f"⚠  Программа запущена без прав администратора (пользователь: {username}).\n"
        "Функции изменения IP и Wi-Fi-профилей требуют повышенных прав.\n"
        "\n"
        "Для полного функционала:\n"
        "  ПКМ на ярлыке → «Запуск от имени администратора» → введите пароль admin-аккаунта.\n"
        "\n"
        "  ⚡ «Запуск от имени другого пользователя» (Shift+ПКМ) НЕ даёт прав администратора —\n"
        "  даже если выбранный аккаунт является администратором."
    )


def is_access_denied_error(stdout: str, stderr: str) -> bool:
    """Detect 'Access is denied' in netsh output (EN + RU locales)."""
    combined = (stdout + stderr).lower()
    return (
        "access is denied" in combined
        or "отказано в доступе" in combined
        or "access denied" in combined
    )


def make_access_denied_message(operation: str) -> str:
    """Return a user-friendly message for netsh Access Denied errors."""
    return (
        f"Отказано в доступе при выполнении операции «{operation}».\n"
        "\n"
        "Причина: программа запущена без прав администратора.\n"
        "Решение: перезапустите через ПКМ → «Запуск от имени администратора»\n"
        "и введите пароль admin-аккаунта."
    )
