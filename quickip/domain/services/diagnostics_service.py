"""Diagnostics service – ping, DNS, netstat, flush DNS, TCP reset."""

import logging
import platform
from typing import Optional

from quickip.domain.models import CommandResult
from quickip.infrastructure.system.process_runner import ProcessRunner

logger = logging.getLogger(__name__)


class DiagnosticsService:
    """Network diagnostic tools."""

    def __init__(self, process_runner: Optional[ProcessRunner] = None):
        self.runner = process_runner or ProcessRunner()

    # ── Ping ────────────────────────────────────────────────────

    def ping(self, host: str, count: int = 4, timeout_ms: int = 1000) -> CommandResult:
        """
        Ping a host.

        Args:
            host: IP address or hostname
            count: Number of echo requests
            timeout_ms: Timeout per request in milliseconds

        Returns:
            CommandResult with stdout output
        """
        if not host:
            host = "8.8.8.8"

        if platform.system().lower() == "windows":
            cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host]
        else:
            cmd = ["ping", "-c", str(count), host]

        result = self.runner.run(cmd, timeout=30)
        logger.debug(f"Ping {host}: {'ok' if result.success else 'failed'}")
        return result

    # ── DNS check ───────────────────────────────────────────────

    def dns_check(self, hostname: str, dns_server: Optional[str] = None) -> CommandResult:
        """
        Resolve a hostname (optionally against a specific DNS server).

        Args:
            hostname: Domain to resolve
            dns_server: Optional specific DNS server IP

        Returns:
            CommandResult with resolution details
        """
        if not hostname:
            hostname = "google.com"

        if platform.system().lower() == "windows":
            if dns_server:
                cmd = ["nslookup", hostname, dns_server]
            else:
                cmd = ["nslookup", hostname]
        else:
            cmd = ["nslookup", hostname] + ([dns_server] if dns_server else [])

        return self.runner.run(cmd, timeout=15)

    # ── Netstat ─────────────────────────────────────────────────

    def netstat(self, show_pids: bool = True) -> CommandResult:
        """
        Get active network connections snapshot.

        Args:
            show_pids: Include process IDs (Windows only)

        Returns:
            CommandResult with connections table
        """
        if platform.system().lower() == "windows":
            cmd = ["netstat", "-ano"] if show_pids else ["netstat", "-an"]
        else:
            cmd = ["netstat", "-an"]

        return self.runner.run(cmd, timeout=20)

    # ── Flush DNS ───────────────────────────────────────────────

    def flush_dns(self) -> CommandResult:
        """
        Flush the OS DNS resolver cache.

        Returns:
            CommandResult indicating success
        """
        if platform.system().lower() == "windows":
            cmd = ["ipconfig", "/flushdns"]
        elif platform.system().lower() == "darwin":
            cmd = ["dscacheutil", "-flushcache"]
        else:
            cmd = ["systemd-resolve", "--flush-caches"]

        return self.runner.run(cmd, timeout=15)

    # ── TCP/IP reset ─────────────────────────────────────────────

    def tcp_reset(self) -> CommandResult:
        """
        Reset the TCP/IP stack (Windows only, requires reboot).

        Returns:
            CommandResult with both commands combined
        """
        if platform.system().lower() != "windows":
            return CommandResult(
                success=False,
                stdout="",
                stderr="TCP/IP reset is only available on Windows.",
                exit_code=1,
                duration_ms=0,
                command="N/A",
            )

        parts = []
        ok = True

        for cmd in [
            ["netsh", "int", "ip", "reset"],
            ["netsh", "winsock", "reset"],
        ]:
            r = self.runner.run(cmd, timeout=30)
            parts.append(r.stdout)
            if not r.success:
                ok = False
                parts.append(f"[ERROR] {r.stderr}")

        return CommandResult(
            success=ok,
            stdout="\n".join(parts),
            stderr="" if ok else "One or more reset commands failed.",
            exit_code=0 if ok else 1,
            duration_ms=0,
            command="netsh int ip reset; netsh winsock reset",
        )


# ── IP Conflict check ────────────────────────────────────────────────────────

class ConflictCheckService:
    """Check whether an IP address is already occupied on the LAN."""

    def __init__(self, process_runner: Optional[ProcessRunner] = None):
        self.runner = process_runner or ProcessRunner()

    def is_ip_in_use(self, ip: str) -> bool:
        """
        Check if an IP is reachable (i.e. used by another host).

        Uses a single fast ping with short timeout.

        Args:
            ip: IPv4 address to probe

        Returns:
            True if the IP responded (conflict), False otherwise
        """
        if platform.system().lower() == "windows":
            cmd = ["ping", "-n", "1", "-w", "500", ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", ip]

        result = self.runner.run(cmd, timeout=5)
        in_use = result.success and self._parse_ping_success(result.stdout)

        logger.debug(f"IP conflict check {ip}: {'in_use' if in_use else 'free'}")
        return in_use

    @staticmethod
    def _parse_ping_success(output: str) -> bool:
        """Detect a successful ping reply inside stdout."""
        lower = output.lower()
        return "ttl=" in lower or "время" in lower or "time=" in lower
