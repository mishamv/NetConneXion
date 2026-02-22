"""Tools feature — console service.

Runs whitelisted network diagnostic tools with optional preset targets.
Security: only tools in ALLOWED_TOOLS may be executed; targets are
validated against strict IPv4 / hostname regex before execution.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from quickip.core.system.process_runner import ProcessRunner

logger = logging.getLogger(__name__)

# ── Whitelist ──────────────────────────────────────────────────────────────────

ALLOWED_TOOLS: List[str] = [
    "ping", "tracert", "nslookup", "ipconfig", "netstat",
    "arp", "pathping", "route", "nbtstat",
]

# Tools that accept no target (run standalone)
_NO_TARGET: set = {"ipconfig", "netstat", "arp", "route"}

# ── Presets ────────────────────────────────────────────────────────────────────

PRESETS: Dict[str, Dict[str, str]] = {
    "ping": {
        "Google DNS":     "8.8.8.8",
        "Cloudflare DNS": "1.1.1.1",
        "Yandex DNS":     "77.88.8.8",
    },
    "tracert": {
        "Google":     "google.com",
        "Cloudflare": "1.1.1.1",
    },
    "nslookup": {
        "Google": "google.com",
        "Yandex": "ya.ru",
    },
    "pathping": {
        "Google DNS": "8.8.8.8",
    },
}

# ── Validation ────────────────────────────────────────────────────────────────

_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9\-\.]{0,253}[A-Za-z0-9])?$")


def _validate_target(target: str) -> bool:
    """Return True for a valid IPv4 address or safe hostname."""
    if not target:
        return False
    if _IP_RE.match(target):
        return all(0 <= int(p) <= 255 for p in target.split("."))
    return bool(_HOSTNAME_RE.match(target))


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ConsoleResult:
    tool: str
    target: str
    output: str
    success: bool
    error: str = ""


# ── Service ───────────────────────────────────────────────────────────────────

class ConsoleService:
    """Execute whitelisted diagnostic tools and return their output."""

    def __init__(self, process_runner: "ProcessRunner") -> None:
        self._runner = process_runner

    # ── Public API ────────────────────────────────────────────────

    def get_tools(self) -> List[str]:
        return list(ALLOWED_TOOLS)

    def get_presets(self, tool: str) -> Dict[str, str]:
        return dict(PRESETS.get(tool, {}))

    def run(
        self,
        tool: str,
        target: str = "",
        extra_args: Optional[List[str]] = None,
    ) -> ConsoleResult:
        """Run *tool* (optionally with *target*).

        Raises:
            ValueError: if tool not in whitelist or target is invalid.
        """
        tool = tool.strip().lower()
        if tool not in ALLOWED_TOOLS:
            raise ValueError(f"Tool '{tool}' is not in the allowed list")

        needs_target = tool not in _NO_TARGET
        if needs_target:
            if not target:
                raise ValueError(f"Tool '{tool}' requires a target address or hostname")
            if not _validate_target(target):
                raise ValueError(f"Invalid target: '{target}' — use a valid IP or hostname")

        cmd = self._build_command(tool, target, extra_args or [])
        logger.debug("ConsoleService running: %s", " ".join(cmd))
        result = self._runner.run(cmd, timeout=45)
        output = result.stdout or result.stderr
        return ConsoleResult(
            tool=tool,
            target=target,
            output=output,
            success=result.success,
            error=result.stderr if not result.success else "",
        )

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_command(tool: str, target: str, extra_args: List[str]) -> List[str]:
        cmd: List[str] = [tool]

        if tool == "ping":
            cmd += ["-n", "4"]
        elif tool == "tracert":
            cmd += ["-d"]      # skip DNS during trace for speed
        elif tool == "ipconfig":
            cmd += ["/all"]
        elif tool == "netstat":
            cmd += ["-ano"]
        elif tool == "arp":
            cmd += ["-a"]
        elif tool == "pathping":
            cmd += ["-n"]

        if extra_args:
            cmd += extra_args
        if target:
            cmd.append(target)
        return cmd
