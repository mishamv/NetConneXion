"""Path utilities for application data storage.

Supports portable mode (portable.flag next to executable) and
standard AppData installation.
"""

import sys
from pathlib import Path


def get_app_data_dir() -> Path:
    """Return the application data directory.

    Portable mode: ``<exe_dir>/data/``
    Standard mode: ``%APPDATA%/QuickIPChange/``
    Fallback:      ``<cwd>/data/``
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
    else:
        # quickip/core/paths.py → parents[1] = quickip/ → parents[2] = project root
        exe_dir = Path(__file__).resolve().parents[2]

    if (exe_dir / "portable.flag").exists():
        data_dir = exe_dir / "data"
        data_dir.mkdir(exist_ok=True)
        return data_dir

    if sys.platform == "win32":
        import os
        appdata = Path(os.getenv("APPDATA", ""))
        if appdata:
            app_dir = appdata / "QuickIPChange"
            app_dir.mkdir(parents=True, exist_ok=True)
            return app_dir

    fallback = Path.cwd() / "data"
    fallback.mkdir(exist_ok=True)
    return fallback


def get_profiles_file() -> Path:
    """Path to profiles.json."""
    return get_app_data_dir() / "profiles.json"


def get_history_file() -> Path:
    """Path to history.json."""
    return get_app_data_dir() / "history.json"


def get_settings_file() -> Path:
    """Path to settings.json."""
    return get_app_data_dir() / "settings.json"


def get_mappings_file() -> Path:
    """Path to network_mappings.json (legacy – kept for migration)."""
    return get_app_data_dir() / "network_mappings.json"


def get_wifi_profiles_file() -> Path:
    """Path to wifi_profiles.json."""
    return get_app_data_dir() / "wifi_profiles.json"


def get_wifi_options_file() -> Path:
    """Path to wifi_options.json."""
    return get_app_data_dir() / "wifi_options.json"


def get_tools_settings_file() -> Path:
    """Path to tools_settings.json."""
    return get_app_data_dir() / "tools_settings.json"


def get_log_dir() -> Path:
    """Directory for rotating log files."""
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir


def is_portable_mode() -> bool:
    """Return True when running in portable mode."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).resolve().parents[2]
    return (exe_dir / "portable.flag").exists()
