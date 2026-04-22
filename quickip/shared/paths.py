"""Path utilities for application data storage."""

import sys
from pathlib import Path

def get_app_data_dir() -> Path:
    """
    Get application data directory.
    
    Returns portable mode path if portable.flag exists,
    otherwise returns system AppData path.
    """
    # Check if running as frozen exe
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).parent.parent.parent

    # Check for portable mode flag
    portable_flag = exe_dir / "portable.flag"
    if portable_flag.exists():
        # Portable mode: store data next to executable
        data_dir = exe_dir / "data"
        data_dir.mkdir(exist_ok=True)
        return data_dir

    # Standard installation mode: use ProgramData (shared, writable by elevated process)
    if sys.platform == "win32":
        import os
        programdata = Path(os.getenv('PROGRAMDATA', ''))
        if programdata:
            app_dir = programdata / "NetConneXion"
            app_dir.mkdir(parents=True, exist_ok=True)
            return app_dir

    # Fallback: current directory
    fallback = Path.cwd() / "data"
    fallback.mkdir(exist_ok=True)
    return fallback


def get_profiles_file() -> Path:
    """Get path to profiles.json."""
    return get_app_data_dir() / "profiles.json"


def get_history_file() -> Path:
    """Get path to history.json."""
    return get_app_data_dir() / "history.json"


def get_settings_file() -> Path:
    """Get path to settings.json."""
    return get_app_data_dir() / "settings.json"


def get_log_dir() -> Path:
    """Get directory for log files."""
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir


def is_portable_mode() -> bool:
    """Check if running in portable mode."""
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).parent.parent.parent

    return (exe_dir / "portable.flag").exists()

def get_wifi_profiles_file() -> Path:
    """Path to wifi_profiles.json."""
    return get_app_data_dir() / "wifi_profiles.json"

def get_wifi_options_file() -> Path:
    """Path to wifi_options.json."""
    return get_app_data_dir() / "wifi_options.json"

def get_tools_settings_file() -> Path:
    """Path to tools_settings.json."""
    return get_app_data_dir() / "tools_settings.json"
