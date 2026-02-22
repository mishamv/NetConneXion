"""Repository interfaces – contracts for data persistence."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Protocol

from quickip.core.models import (
    Profile,
    ProfileHistoryEntry,
    HistoryStats,
)


class ProfileRepository(ABC):
    """Interface for profile persistence."""

    @abstractmethod
    def list(self) -> List[Profile]:
        """Get all profiles."""

    @abstractmethod
    def get(self, profile_id: str) -> Optional[Profile]:
        """Get profile by ID."""

    @abstractmethod
    def save(self, profile: Profile) -> None:
        """Save or update profile."""

    @abstractmethod
    def delete(self, profile_id: str) -> None:
        """Delete profile by ID."""

    @abstractmethod
    def exists(self, profile_id: str) -> bool:
        """Check if profile exists."""

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Profile]:
        """Find profile by exact name."""


class HistoryRepository(ABC):
    """Interface for history persistence."""

    @abstractmethod
    def append(self, entry: ProfileHistoryEntry) -> None:
        """Add new history entry."""

    @abstractmethod
    def list(
        self,
        limit: Optional[int] = None,
        profile_id: Optional[str] = None,
        success_only: Optional[bool] = None,
    ) -> List[ProfileHistoryEntry]:
        """Query history entries with optional filters."""

    @abstractmethod
    def get(self, entry_id: str) -> Optional[ProfileHistoryEntry]:
        """Get specific history entry."""

    @abstractmethod
    def stats(self) -> HistoryStats:
        """Calculate aggregated statistics."""

    @abstractmethod
    def clear(self) -> None:
        """Clear all history."""


class SettingsRepository(ABC):
    """Interface for application settings persistence."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value."""

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set setting value."""

    @abstractmethod
    def get_all(self) -> Dict[str, Any]:
        """Get all settings."""

    @abstractmethod
    def save(self) -> None:
        """Persist settings to storage."""


class INotificationService(Protocol):
    def show(self, title: str, message: str, level: str = "info") -> None:
        ...


class II18nService(Protocol):
    def get(self, key: str, **kwargs) -> str:
        ...

    def set_locale(self, locale: str) -> None:
        ...

    def get_current_locale(self) -> str:
        ...
