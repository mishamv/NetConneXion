"""Application event types for the event bus."""

from dataclasses import dataclass, field
from typing import Optional, List

from quickip.core.models import ApplyResult, Profile


@dataclass
class AppEvent:
    """Base event class."""


# ── Profile events ────────────────────────────────────────────────

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
    """Existing profile was updated."""
    profile: Profile
    old_name: Optional[str] = None


@dataclass
class ProfileDeleted(AppEvent):
    """Profile was deleted."""
    profile_id: str
    profile_name: str


@dataclass
class ProfilesImported(AppEvent):
    """Profiles were imported from file."""
    count: int
    profile_ids: List[str] = field(default_factory=list)


@dataclass
class ProfilesChanged(AppEvent):
    """Profile list changed (create/update/delete/import).

    Subscribers (history, wifi, etc.) use this to refresh UI
    instead of being wired via direct callbacks.
    """
    profile_names: List[str] = field(default_factory=list)


# ── History events ────────────────────────────────────────────────

@dataclass
class HistoryUpdated(AppEvent):
    """A new history entry was recorded."""
    entry_id: str


# ── UI / App events ───────────────────────────────────────────────

@dataclass
class ThemeChanged(AppEvent):
    """UI theme was changed."""
    theme: str  # "light" or "dark"


@dataclass
class SettingsChanged(AppEvent):
    """Application settings key changed."""
    key: str
    value: object


@dataclass
class NetworkSnapshotReady(AppEvent):
    """Current network snapshot text is ready for display."""
    text: str


@dataclass
class ApplicationStarted(AppEvent):
    """Application finished startup."""


@dataclass
class ApplicationStopping(AppEvent):
    """Application is about to shut down."""


# ── Wi-Fi events ──────────────────────────────────────────────────

@dataclass
class WifiNetworksUpdated(AppEvent):
    """Visible Wi-Fi network list was refreshed."""
    network_count: int


@dataclass
class WifiStatusUpdated(AppEvent):
    """Wi-Fi interface connection status changed."""
    adapter: str
    ssid: str
    connected: bool


@dataclass
class WifiProfileSaved(AppEvent):
    """A Wi-Fi credential profile was saved."""
    profile_id: str
    ssid: str


@dataclass
class WifiProfileDeleted(AppEvent):
    """A Wi-Fi credential profile was deleted."""
    profile_id: str
