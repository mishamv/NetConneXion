"""Safe process execution with timeout and error handling.

This is the ONLY allowed subprocess wrapper in the entire application.
No direct subprocess calls are permitted anywhere else.
"""

import subprocess
import logging
import platform
import time
from typing import List, Optional

from quickip.core.models import CommandResult


logger = logging.getLogger(__name__)


class ProcessRunner:
    """Execute system commands safely with proper error handling."""

    @staticmethod
    def _get_startupinfo():
        """Get Windows startupinfo to hide console windows."""
        if platform.system().lower() != "windows":
            return None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        return startupinfo

    @staticmethod
    def _get_creation_flags() -> int:
        """Get Windows creation flags to prevent console windows."""
        if platform.system().lower() != "windows":
            return 0
        return subprocess.CREATE_NO_WINDOW

    @staticmethod
    def _decode_output(raw_bytes: bytes) -> str:
        """Decode command output handling multiple encodings.

        Tries UTF-16 (Windows netsh), UTF-8, CP866, CP1251.
        """
        if not raw_bytes:
            return ""

        # Check for UTF-16 BOM
        if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
            try:
                return raw_bytes.decode("utf-16")
            except UnicodeDecodeError:
                pass

        # Detect UTF-16 by zero-byte pattern
        if len(raw_bytes) > 4:
            odd_zeros = sum(1 for b in raw_bytes[1::2] if b == 0)
            half = max(1, len(raw_bytes) // 2)
            if odd_zeros / half > 0.35:
                try:
                    return raw_bytes.decode("utf-16-le")
                except UnicodeDecodeError:
                    pass

        for encoding in ("utf-8", "cp866", "cp1251", "latin-1"):
            try:
                return raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue

        return raw_bytes.decode("utf-8", errors="replace")

    def run(
        self,
        command: List[str],
        timeout: Optional[int] = 30,
        check: bool = False,
        shell: bool = False,
    ) -> CommandResult:
        """Execute command and return result.

        Args:
            command: Command and arguments as a list.
            timeout: Timeout in seconds (None = no timeout).
            check: Raise exception on non-zero exit code.
            shell: Run command in shell.

        Returns:
            CommandResult with stdout, stderr, exit code, duration.
        """
        start_time = time.time()
        command_str = " ".join(command) if isinstance(command, list) else command
        logger.debug(f"Executing: {command_str}")

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=timeout,
                check=check,
                shell=shell,
                startupinfo=self._get_startupinfo(),
                creationflags=self._get_creation_flags(),
            )
            duration_ms = int((time.time() - start_time) * 1000)
            stdout = self._decode_output(result.stdout)
            stderr = self._decode_output(result.stderr)
            logger.debug(f"Done: exit={result.returncode}, {duration_ms}ms")
            return CommandResult(
                success=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                command=command_str,
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Timed out after {timeout}s: {command_str}")
            return CommandResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                duration_ms=duration_ms,
                command=command_str,
            )

        except subprocess.CalledProcessError as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            stdout = self._decode_output(exc.stdout) if exc.stdout else ""
            stderr = self._decode_output(exc.stderr) if exc.stderr else ""
            logger.error(f"Failed: exit={exc.returncode}, stderr={stderr[:100]}")
            return CommandResult(
                success=False,
                stdout=stdout,
                stderr=stderr,
                exit_code=exc.returncode,
                duration_ms=duration_ms,
                command=command_str,
            )

        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Execution error: {exc}", exc_info=True)
            return CommandResult(
                success=False,
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                duration_ms=duration_ms,
                command=command_str,
            )

    def run_shell(self, command: str, timeout: Optional[int] = 30) -> CommandResult:
        """Execute shell command as string."""
        return self.run([command], timeout=timeout, shell=True)
