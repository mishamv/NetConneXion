"""Windows netsh client for network configuration."""

import logging
import ipaddress
import re
from typing import List, Optional
from quickip.domain.models import Profile, CommandResult, AdapterConfig
from quickip.infrastructure.system.process_runner import ProcessRunner
from quickip.shared.privilege_check import is_access_denied_error, make_access_denied_message


logger = logging.getLogger(__name__)


class NetshClient:
    """Client for Windows netsh network operations."""

    def __init__(self, process_runner: Optional[ProcessRunner] = None):
        """
        Initialize netsh client.
        
        Args:
            process_runner: ProcessRunner instance (None = create new)
        """
        self.runner = process_runner or ProcessRunner()

    def list_adapters(self) -> List[str]:
        """
        Get list of network adapter names.
        
        Returns:
            List of adapter names
        """
        result = self.runner.run(["netsh", "interface", "show", "interface"])
        
        if not result.success:
            logger.error(f"Failed to list adapters: {result.stderr}")
            return []

        adapters = self._parse_adapter_list(result.stdout)
        logger.debug(f"Found {len(adapters)} network adapters")
        return adapters

    def _parse_adapter_list(self, output: str) -> List[str]:
        """Parse netsh interface list output."""
        adapters = []
        
        for line in output.splitlines():
            line = line.strip()
            if not line or set(line) == {'-'}:
                continue

            lowered = line.lower()
            # Skip headers
            if "interface name" in lowered or "имя интерфейса" in lowered:
                continue
            if lowered.startswith("admin state") or lowered.startswith("состояние"):
                continue

            # Parse line with multiple spaces as separator
            parts = re.split(r'\s{2,}', line)
            if len(parts) >= 4 and parts[-1]:
                adapters.append(parts[-1])

        # Remove duplicates while preserving order
        seen = set()
        unique_adapters = []
        for adapter in adapters:
            if adapter.lower() not in seen:
                seen.add(adapter.lower())
                unique_adapters.append(adapter)

        return unique_adapters

    def get_adapter_config(self, adapter: str) -> Optional[AdapterConfig]:
        """
        Get current configuration for adapter.
        
        Args:
            adapter: Adapter name
            
        Returns:
            AdapterConfig or None if failed
        """
        result = self.runner.run(
            ["netsh", "interface", "ipv4", "show", "config", f'name="{adapter}"']
        )

        if not result.success:
            logger.error(f"Failed to get adapter config: {result.stderr}")
            return None

        return self._parse_adapter_config(adapter, result.stdout)

    def _parse_adapter_config(self, adapter: str, output: str) -> Optional[AdapterConfig]:
        """Parse adapter configuration from netsh output."""
        config = AdapterConfig(adapter=adapter, ip="", mask="", gateway="")

        collecting_dns = False
        for raw_line in output.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                collecting_dns = False
                continue

            label, separator, value = stripped.partition(":")
            lowered_label = label.casefold()
            value = value.strip() if separator else ""

            if "dhcp" in lowered_label and (
                "enabled" in lowered_label or "включ" in lowered_label
            ):
                config.dhcp_enabled = value.casefold() in {
                    "yes", "true", "enabled", "да", "включено", "включен",
                }
                collecting_dns = False
                continue

            if "ip address" in lowered_label or "ip-адрес" in lowered_label:
                config.ip = self._first_ipv4(value)
                collecting_dns = False
                continue

            if any(marker in lowered_label for marker in (
                "subnet prefix", "subnet mask", "префикс подсети", "маска подсети",
            )):
                config.mask = self._parse_subnet_mask(value)
                collecting_dns = False
                continue

            if "default gateway" in lowered_label or "основной шлюз" in lowered_label:
                config.gateway = self._first_ipv4(value)
                collecting_dns = False
                continue

            is_dns_label = "dns" in lowered_label and (
                "server" in lowered_label or "сервер" in lowered_label
            )
            if is_dns_label:
                self._append_ipv4(config.dns_servers, value)
                collecting_dns = True
                continue

            if collecting_dns and not separator:
                if self._append_ipv4(config.dns_servers, stripped):
                    continue
            collecting_dns = False

        return config

    @staticmethod
    def _first_ipv4(value: str) -> str:
        match = re.search(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", value)
        if not match:
            return ""
        candidate = match.group(0)
        try:
            return str(ipaddress.IPv4Address(candidate))
        except ipaddress.AddressValueError:
            return ""

    @classmethod
    def _append_ipv4(cls, values: List[str], text: str) -> bool:
        address = cls._first_ipv4(text)
        if not address:
            return False
        if address not in values:
            values.append(address)
        return True

    @classmethod
    def _parse_subnet_mask(cls, value: str) -> str:
        explicit = re.search(
            r"(?:mask|маска)\s+((?:\d{1,3}\.){3}\d{1,3})",
            value,
            flags=re.IGNORECASE,
        )
        if explicit:
            return cls._first_ipv4(explicit.group(1))

        prefix = re.search(r"/(\d{1,2})(?:\D|$)", value)
        if prefix:
            try:
                return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix.group(1)}").netmask)
            except (ValueError, ipaddress.NetmaskValueError):
                return ""

        return cls._first_ipv4(value)

    # Символы запрещённые в имени адаптера — защита от command injection в netsh
    _ADAPTER_FORBIDDEN = set('"\'&|;<>(){}$`\\\n\r\t')
    _ADAPTER_MAX_LEN = 64

    @classmethod
    def _validate_adapter_name(cls, adapter: str) -> str:
        """Валидирует имя адаптера перед передачей в netsh.

        Разрешает только безопасные символы — буквы, цифры, пробелы,
        дефис, подчёркивание, точка, скобки [] (нужны для ZeroTier и др.).
        Raises ValueError если имя содержит потенциально опасные символы.
        """
        if not adapter or not adapter.strip():
            raise ValueError("Имя адаптера не может быть пустым.")
        if len(adapter) > cls._ADAPTER_MAX_LEN:
            raise ValueError(f"Имя адаптера слишком длинное (>{cls._ADAPTER_MAX_LEN} символов).")
        forbidden = cls._ADAPTER_FORBIDDEN.intersection(adapter)
        if forbidden:
            bad = ''.join(sorted(forbidden))
            raise ValueError(f"Имя адаптера содержит запрещённые символы: {bad!r}")
        return adapter

    def apply_profile(self, profile: Profile) -> CommandResult:
        """
        Apply network profile configuration.

        Args:
            profile: Profile to apply

        Returns:
            CommandResult with execution details
        """
        # C2: валидируем имя адаптера до формирования команд
        try:
            self._validate_adapter_name(profile.adapter)
        except ValueError as e:
            msg = f"Недопустимое имя адаптера: {e}"
            logger.error(msg)
            return CommandResult(
                success=False,
                stdout="",
                stderr=msg,
                exit_code=-1,
                duration_ms=0,
                command="",
            )

        # C3: валидируем сетевые поля статического профиля перед передачей в netsh
        if not profile.is_dhcp_ip:
            from quickip.shared.net_utils import validate_profile_network_fields
            try:
                validate_profile_network_fields(
                    ipv4=profile.ipv4,
                    mask=profile.mask,
                    gateway=profile.gateway,
                    dns_primary="" if profile.is_dhcp_dns else profile.dns_primary,
                    dns_secondary="" if profile.is_dhcp_dns else profile.dns_secondary,
                )
            except ValueError as e:
                msg = f"Некорректные сетевые настройки профиля: {e}"
                logger.error(msg)
                return CommandResult(
                    success=False,
                    stdout="",
                    stderr=msg,
                    exit_code=-1,
                    duration_ms=0,
                    command="",
                )
        elif not profile.is_dhcp_dns and (profile.dns_primary or profile.dns_secondary):
            # DHCP IP, но статический DNS — валидируем только DNS поля
            from quickip.shared.net_utils import validate_ipv4
            try:
                if profile.dns_primary:
                    validate_ipv4(profile.dns_primary, "основной DNS")
                if profile.dns_secondary:
                    validate_ipv4(profile.dns_secondary, "дополнительный DNS")
            except ValueError as e:
                msg = f"Некорректный DNS-адрес: {e}"
                logger.error(msg)
                return CommandResult(
                    success=False,
                    stdout="",
                    stderr=msg,
                    exit_code=-1,
                    duration_ms=0,
                    command="",
                )

        commands = self._build_commands(profile)
        all_output = []
        all_errors = []
        total_duration = 0

        for cmd in commands:
            result = self.runner.run(cmd)
            total_duration += result.duration_ms

            if result.stdout:
                all_output.append(result.stdout)
            if result.stderr:
                all_errors.append(result.stderr)

            if not result.success:
                # Команда delete dnsservers может упасть если DNS не настроен — игнорируем
                if "delete" in cmd and "dnsservers" in cmd:
                    logger.debug(f"Ignored non-critical DNS delete failure: {result.stdout}")
                    continue

                # Проверяем до формирования error_msg: если "Access is denied" —
                # даём пользователю actionable объяснение про UAC/filtered token.
                if is_access_denied_error(result.stdout, result.stderr):
                    op = ' '.join(cmd[2:5])  # напр. "interface ipv4 set"
                    error_msg = make_access_denied_message(op)
                    logger.error(
                        "netsh access denied for %r: stdout=%r stderr=%r",
                        op, result.stdout, result.stderr,
                    )
                else:
                    error_msg = (
                        f"Command failed: {' '.join(cmd)}\n"
                        f"stdout: {result.stdout}\nstderr: {result.stderr}\n"
                        f"exit_code: {result.exit_code}"
                    )
                    logger.error(error_msg)

                return CommandResult(
                    success=False,
                    stdout='\n'.join(all_output),
                    stderr=error_msg,
                    exit_code=result.exit_code,
                    duration_ms=total_duration,
                    command='; '.join([' '.join(c) for c in commands])
                )

        return CommandResult(
            success=True,
            stdout='\n'.join(all_output),
            stderr='\n'.join(all_errors),
            exit_code=0,
            duration_ms=total_duration,
            command='; '.join([' '.join(c) for c in commands])
        )

    def _build_commands(self, profile: Profile) -> List[List[str]]:
        """Build netsh commands for profile application."""
        commands = []
        adapter = profile.adapter

        # IP configuration
        if profile.is_dhcp_ip:
            commands.append([
                "netsh", "interface", "ipv4", "set", "address",
                f'name="{adapter}"', "source=dhcp"
            ])
        else:
            if profile.gateway:
                commands.append([
                    "netsh", "interface", "ipv4", "set", "address",
                    f'name="{adapter}"', "source=static",
                    f"address={profile.ipv4}",
                    f"mask={profile.mask}",
                    f"gateway={profile.gateway}",
                ])
            else:
                commands.append([
                    "netsh", "interface", "ipv4", "set", "address",
                    f'name="{adapter}"', "source=static",
                    f"address={profile.ipv4}",
                    f"mask={profile.mask}",
                    "gateway=none"
                ])

        # DNS configuration
        if profile.is_dhcp_dns:
            commands.append([
                "netsh", "interface", "ipv4", "set", "dnsservers",
                f'name="{adapter}"', "source=dhcp"
            ])
        else:
            if profile.dns_primary:
                # Сбрасываем DNS через DHCP — гарантированно очищает список
                commands.append([
                    "netsh", "interface", "ipv4", "set", "dnsservers",
                    f'name="{adapter}"', "source=dhcp"
                ])
                # Ставим первичный DNS статически
                commands.append([
                    "netsh", "interface", "ipv4", "set", "dnsservers",
                    f'name="{adapter}"', "source=static",
                    f"address={profile.dns_primary}",
                    "register=primary", "validate=no"
                ])
                # Добавляем вторичный только если он отличается от первичного
                if profile.dns_secondary and profile.dns_secondary != profile.dns_primary:
                    commands.append([
                        "netsh", "interface", "ipv4", "add", "dnsservers",
                        f'name="{adapter}"',
                        f"address={profile.dns_secondary}",
                        "index=2", "validate=no"
                    ])

        return commands

    def get_network_snapshot(self) -> str:
        """
        Get complete network configuration snapshot.
        
        Returns:
            Formatted network configuration text
        """
        parts = []

        # ipconfig /all
        result1 = self.runner.run(["ipconfig", "/all"])
        if result1.success:
            parts.append("=== ipconfig /all ===")
            parts.append(result1.stdout)
        else:
            parts.append(f"ipconfig failed: {result1.stderr}")

        # netsh interface ipv4 show config
        result2 = self.runner.run(["netsh", "interface", "ipv4", "show", "config"])
        if result2.success:
            parts.append("\n=== netsh interface ipv4 show config ===")
            parts.append(result2.stdout)
        else:
            parts.append(f"netsh config failed: {result2.stderr}")

        return '\n'.join(parts)
