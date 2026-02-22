"""Domain models - Core business entities."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum


class IPMode(str, Enum):
    """IP address assignment mode."""
    DHCP = "dhcp"
    STATIC = "static"


class DNSMode(str, Enum):
    """DNS server assignment mode."""
    DHCP = "dhcp"
    STATIC = "static"


@dataclass
class Profile:
    """Network profile configuration."""
    id: str
    name: str
    adapter: str
    ip_mode: IPMode
    ipv4: str = ""
    mask: str = ""
    gateway: str = ""
    dns_mode: DNSMode = DNSMode.DHCP
    dns_primary: str = ""
    dns_secondary: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_dhcp_ip(self) -> bool:
        """Check if profile uses DHCP for IP."""
        return self.ip_mode == IPMode.DHCP

    @property
    def is_dhcp_dns(self) -> bool:
        """Check if profile uses DHCP for DNS."""
        return self.dns_mode == DNSMode.DHCP


@dataclass
class NetworkFingerprint:
    """Unique network identifier for auto-switching."""
    ssid: str = ""
    bssid: str = ""
    gateway_ip: str = ""
    gateway_mac: str = ""
    adapter_name: str = ""

    @property
    def primary_key(self) -> str:
        """Primary identification key (SSID preferred)."""
        return self.ssid or self.gateway_mac or self.gateway_ip

    @property
    def is_valid(self) -> bool:
        """Check if fingerprint has enough data to identify network."""
        return bool(self.ssid or self.gateway_mac or self.gateway_ip)


@dataclass
class AdapterConfig:
    """Current network adapter configuration snapshot."""
    adapter: str
    ip: str
    mask: str
    gateway: str
    dns_servers: List[str] = field(default_factory=list)
    dhcp_enabled: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ApplyResult:
    """Result of profile application."""
    success: bool
    message: str
    duration_ms: int
    profile_id: str
    profile_name: str
    adapter: str
    previous_config: Optional[AdapterConfig] = None
    new_config: Optional[AdapterConfig] = None
    commands_executed: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ProfileHistoryEntry:
    """Single profile application history record."""
    id: str
    timestamp: str
    profile_id: str
    profile_name: str
    adapter: str
    success: bool
    duration_ms: int
    previous_config: Optional[AdapterConfig] = None
    new_config: Optional[AdapterConfig] = None
    commands: List[str] = field(default_factory=list)
    output: List[str] = field(default_factory=list)
    error_message: str = ""


@dataclass
class HistoryStats:
    """Aggregated history statistics."""
    total_applies: int
    successful_applies: int
    failed_applies: int
    avg_duration_ms: float
    most_used_profile: Optional[str] = None
    most_used_adapter: Optional[str] = None


@dataclass
class NetworkMapping:
    """Auto-switch mapping between network and profile."""
    id: str
    network_key: str  # SSID or BSSID or gateway MAC
    profile_id: str
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CommandResult:
    """Result of system command execution."""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    command: str


@dataclass
class ImportConflict:
    """Profile import conflict information."""
    existing_profile: Profile
    imported_profile: Profile
    conflict_type: str  # "name", "id", "subnet"


@dataclass
class ImportReport:
    """Result of profile import operation."""
    total_imported: int
    successful: int
    skipped: int
    conflicts: List[ImportConflict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
