"""Event types for application event bus."""

from dataclasses import dataclass
from typing import Optional
from quickip.domain.models import (
    NetworkFingerprint,
    ApplyResult,
    Profile,
)


@dataclass
class AppEvent:
    """Base event class."""
    pass


@dataclass
class NetworkChanged(AppEvent):
    """Network connection changed."""
    fingerprint: NetworkFingerprint


@dataclass
class ProfileApplied(AppEvent):
    """Profile was successfully applied."""
    profile_id: str
    profile_name: str
    adapter: str
    result: ApplyResult


@dataclass
class ProfileApplyFailed(AppEvent):
    """Profile application failed."""
    profile_id: str
    profile_name: str
    adapter: str
    error: str


@dataclass
class ProfileCreated(AppEvent):
    """New profile was created."""
    profile: Profile


@dataclass
class ProfileUpdated(AppEvent):
    """Profile was updated."""
    profile: Profile
    old_name: Optional[str] = None


@dataclass
class ProfileDeleted(AppEvent):
    """Profile was deleted."""
    profile_id: str
    profile_name: str


@dataclass
class ProfilesImported(AppEvent):
    """Profiles were imported."""
    count: int
    profile_ids: list


@dataclass
class HistoryUpdated(AppEvent):
    """History was updated."""
    entry_id: str


@dataclass
class ThemeChanged(AppEvent):
    """UI theme was changed."""
    theme: str  # "light" or "dark"


@dataclass
class SettingsChanged(AppEvent):
    """Application settings changed."""
    key: str
    value: any


@dataclass
class AutoSwitchTriggered(AppEvent):
    """Auto-switch was triggered."""
    network_key: str
    profile_id: str


@dataclass
class ApplicationStarted(AppEvent):
    """Application started."""
    pass


@dataclass
class ApplicationStopping(AppEvent):
    """Application is stopping."""
    pass
