"""Tools feature — console service.

Runs whitelisted network diagnostic tools with optional preset targets.
Security: only tools in ALLOWED_TOOLS may be executed; targets are
validated against strict IPv4 / hostname regex before execution.
Extra args are validated against per-tool flag whitelists with numeric
bounds to prevent argument injection.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from quickip.infrastructure.system.process_runner import ProcessRunner

logger = logging.getLogger(__name__)

# ── Whitelist ──────────────────────────────────────────────────────────────────

ALLOWED_TOOLS: List[str] = [
    "ping", "tracert", "nslookup", "ipconfig", "netstat",
    "arp", "pathping", "route", "nbtstat",
]

# Tools that accept no target (run standalone)
_NO_TARGET: set = {"ipconfig", "netstat", "arp", "route"}

# Per-tool allowed flags (exact flag names only; no values included here)
_ALLOWED_FLAGS: Dict[str, FrozenSet[str]] = {
    "ping":     frozenset({"-n", "-w", "-l", "-t", "-4", "-6"}),
    "tracert":  frozenset({"-d", "-h", "-w", "-4", "-6"}),
    "nslookup": frozenset({"-type", "-querytype", "-timeout", "-port"}),
    "ipconfig": frozenset({"/all", "/release", "/renew", "/flushdns",
                           "/registerdns", "/displaydns"}),
    "netstat":  frozenset({"-a", "-b", "-e", "-f", "-n", "-o",
                           "-p", "-r", "-s", "-x", "-y"}),
    "arp":      frozenset({"-a", "-d", "-g", "-n", "-s", "-v"}),
    "pathping": frozenset({"-n", "-h", "-w", "-4", "-6", "-q"}),
    "route":    frozenset({"print", "add", "delete", "change", "-4", "-6"}),
    "nbtstat":  frozenset({"-a", "-A", "-c", "-n", "-r", "-R", "-S", "-s"}),
}

# Numeric bounds for flags that take integer values
_NUMERIC_FLAG_BOUNDS: Dict[str, Dict[str, tuple]] = {
    "ping":    {"-n": (1, 100), "-w": (1, 10000), "-l": (1, 65500)},
    "tracert": {"-h": (1, 255), "-w": (1, 10000)},
    "pathping": {"-h": (1, 255), "-w": (1, 10000), "-q": (1, 100)},
}

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


def _validate_extra_args(tool: str, args: List[str]) -> None:
    """Raise ValueError if any arg in *args* is not permitted for *tool*.

    Checks flag names against per-tool whitelist and validates numeric
    values against defined bounds to prevent argument injection.
    """
    allowed = _ALLOWED_FLAGS.get(tool, frozenset())
    bounds = _NUMERIC_FLAG_BOUNDS.get(tool, {})

    i = 0
    while i < len(args):
        arg = args[i]
        # Flags start with '-' or '/' on Windows
        if arg.startswith("-") or arg.startswith("/"):
            flag = arg.lower() if arg.startswith("-") else arg
            if flag not in allowed:
                raise ValueError(
                    f"Flag '{arg}' is not allowed for '{tool}'. "
                    f"Allowed: {sorted(allowed)}"
                )
            # Check if next token is the numeric value for this flag
            if flag in bounds and i + 1 < len(args):
                value_str = args[i + 1]
                if not value_str.startswith("-"):
                    try:
                        value = int(value_str)
                    except ValueError:
                        raise ValueError(
                            f"Expected an integer after '{arg}', got '{value_str}'"
                        )
                    lo, hi = bounds[flag]
                    if not (lo <= value <= hi):
                        raise ValueError(
                            f"Value {value} for '{arg}' is out of range [{lo}, {hi}]"
                        )
                    i += 1  # skip the value token
        else:
            # Bare words (e.g. "print" for route) must also be in the whitelist
            if arg not in allowed:
                raise ValueError(
                    f"Argument '{arg}' is not allowed for '{tool}'. "
                    f"Allowed: {sorted(allowed)}"
                )
        i += 1


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
            ValueError: if tool not in whitelist, target is invalid, or
                        extra_args contain disallowed flags/values.
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

        effective_args = extra_args or []
        if effective_args:
            _validate_extra_args(tool, effective_args)

        cmd = self._build_command(tool, target, effective_args)
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
