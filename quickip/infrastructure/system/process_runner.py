"""Safe process execution with timeout and error handling."""

import re
import subprocess
import logging
import platform
import time
from typing import List, Optional
from quickip.domain.models import CommandResult


logger = logging.getLogger(__name__)

# Аргументы, содержащие эти ключевые слова, маскируются в логах
_SENSITIVE_ARG_PATTERNS = re.compile(
    r"(password|passwd|pwd|secret|token|key|credential|auth)",
    re.IGNORECASE,
)

# netsh аргументы вида name=<ssid> и ssid=<ssid> маскируются отдельно
_NETSH_SSID_PATTERN = re.compile(r"^(name|ssid|interface)=(.+)$", re.IGNORECASE)


def _redact_command(parts: List[str]) -> str:
    """Возвращает строку команды с маскировкой чувствительных аргументов."""
    result = []
    redact_next = False
    for part in parts:
        if redact_next:
            result.append("***")
            redact_next = False
        elif _NETSH_SSID_PATTERN.match(part):
            key = part.split("=", 1)[0]
            result.append(f"{key}=***")
        elif _SENSITIVE_ARG_PATTERNS.search(part):
            # Если аргумент содержит чувствительное слово и имеет вид --key=value
            if "=" in part:
                key, _ = part.split("=", 1)
                result.append(f"{key}=***")
            else:
                result.append(part)
                redact_next = True  # следующий аргумент — значение
        else:
            result.append(part)
    return " ".join(result)


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
    def _get_creation_flags():
        """Get Windows creation flags to prevent console windows."""
        if platform.system().lower() != "windows":
            return 0
        
        return subprocess.CREATE_NO_WINDOW

    @staticmethod
    def _decode_output(raw_bytes: bytes) -> str:
        """
        Decode command output handling multiple encodings.
        
        Tries UTF-16 (Windows netsh), UTF-8, CP866, CP1251.
        """
        if not raw_bytes:
            return ""

        # Check for UTF-16 BOM
        if raw_bytes.startswith(b'\xff\xfe') or raw_bytes.startswith(b'\xfe\xff'):
            try:
                return raw_bytes.decode('utf-16')
            except UnicodeDecodeError:
                pass

        # Detect UTF-16 by zero byte patterns
        if len(raw_bytes) > 4:
            odd_zeros = sum(1 for b in raw_bytes[1::2] if b == 0)
            half = max(1, len(raw_bytes) // 2)

            if odd_zeros / half > 0.35:
                try:
                    return raw_bytes.decode('utf-16-le')
                except UnicodeDecodeError:
                    pass

        # Try common encodings
        for encoding in ['utf-8', 'cp866', 'cp1251', 'latin-1']:
            try:
                return raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue

        # Fallback with replacement
        return raw_bytes.decode('utf-8', errors='replace')

    def run(
        self,
        command: List[str],
        timeout: Optional[int] = 30,
        check: bool = False,
        shell: bool = False
    ) -> CommandResult:
        """
        Execute command and return result.
        
        Args:
            command: Command and arguments as list
            timeout: Timeout in seconds (None = no timeout)
            check: Raise exception on non-zero exit code
            shell: Run command in shell
            
        Returns:
            CommandResult with stdout, stderr, exit code, duration
        """
        if shell:
            raise ValueError(
                "shell=True is forbidden in ProcessRunner. "
                "Pass the command as a list and set shell=False."
            )

        start_time = time.time()
        command_str = _redact_command(command) if isinstance(command, list) else command

        logger.debug(f"Executing command: {command_str}")

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

            logger.debug(
                f"Command completed: exit_code={result.returncode}, "
                f"duration={duration_ms}ms"
            )

            return CommandResult(
                success=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                command=command_str
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Command timed out after {timeout}s: {command_str}")
            
            return CommandResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                duration_ms=duration_ms,
                command=command_str
            )

        except subprocess.CalledProcessError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            stdout = self._decode_output(e.stdout) if e.stdout else ""
            stderr = self._decode_output(e.stderr) if e.stderr else ""
            
            logger.error(
                f"Command failed: exit_code={e.returncode}, "
                f"stderr={stderr[:100]}"
            )

            return CommandResult(
                success=False,
                stdout=stdout,
                stderr=stderr,
                exit_code=e.returncode,
                duration_ms=duration_ms,
                command=command_str
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Command execution error: {e}", exc_info=True)
            
            return CommandResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=duration_ms,
                command=command_str
            )
