"""Repository interfaces - contracts for data persistence."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Protocol
from quickip.domain.models import (
    Profile,
    ProfileHistoryEntry,
    HistoryStats,
    NetworkMapping,
)


class ProfileRepository(ABC):
    """Interface for profile persistence."""

    @abstractmethod
    def list(self) -> List[Profile]:
        """Get all profiles."""
        pass

    @abstractmethod
    def get(self, profile_id: str) -> Optional[Profile]:
        """Get profile by ID."""
        pass

    @abstractmethod
    def save(self, profile: Profile) -> None:
        """Save or update profile."""
        pass

    @abstractmethod
    def delete(self, profile_id: str) -> None:
        """Delete profile by ID."""
        pass

    @abstractmethod
    def exists(self, profile_id: str) -> bool:
        """Check if profile exists."""
        pass

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Profile]:
        """Find profile by exact name."""
        pass


class HistoryRepository(ABC):
    """Interface for history persistence."""

    @abstractmethod
    def append(self, entry: ProfileHistoryEntry) -> None:
        """Add new history entry."""
        pass

    @abstractmethod
    def list(
        self, 
        limit: Optional[int] = None,
        profile_id: Optional[str] = None,
        success_only: Optional[bool] = None
    ) -> List[ProfileHistoryEntry]:
        """Query history entries with filters."""
        pass

    @abstractmethod
    def get(self, entry_id: str) -> Optional[ProfileHistoryEntry]:
        """Get specific history entry."""
        pass

    @abstractmethod
    def stats(self) -> HistoryStats:
        """Calculate aggregated statistics."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all history."""
        pass


class SettingsRepository(ABC):
    """Interface for application settings persistence."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set setting value."""
        pass

    @abstractmethod
    def get_all(self) -> Dict[str, Any]:
        """Get all settings."""
        pass

    @abstractmethod
    def save(self) -> None:
        """Persist settings to storage."""
        pass


class NetworkMappingRepository(ABC):
    """Interface for network-to-profile mappings persistence."""

    @abstractmethod
    def list(self) -> List[NetworkMapping]:
        """Get all network mappings."""
        pass

    @abstractmethod
    def get(self, mapping_id: str) -> Optional[NetworkMapping]:
        """Get mapping by ID."""
        pass

    @abstractmethod
    def find_by_network(self, network_key: str) -> Optional[NetworkMapping]:
        """Find mapping by network identifier."""
        pass

    @abstractmethod
    def save(self, mapping: NetworkMapping) -> None:
        """Save or update mapping."""
        pass

    @abstractmethod
    def delete(self, mapping_id: str) -> None:
        """Delete mapping."""
        pass

    @abstractmethod
    def get_enabled(self) -> List[NetworkMapping]:
        """Get only enabled mappings."""
        pass


class INotificationService(Protocol):
    def show(self, title: str, message: str, level: str = 'info') -> None:
        ...


class II18nService(Protocol):
    def get(self, key: str, **kwargs) -> str:
        ...
    def set_locale(self, locale: str) -> None:
        ...
    def get_current_locale(self) -> str:
        ...
