"""Shared network utility functions."""

import ipaddress


def prefix_to_mask(prefix: int) -> str:
    """Convert CIDR prefix length (e.g. 24) to dotted-decimal mask (e.g. 255.255.255.0)."""
    if not (0 <= prefix <= 32):
        return ""
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return ".".join(str((mask >> (8 * i)) & 0xFF) for i in reversed(range(4)))


def validate_ipv4(addr: str, field: str = "адрес") -> None:
    """Проверяет что addr является корректным IPv4-адресом.

    Args:
        addr:  Строка для проверки.
        field: Название поля для сообщения об ошибке.

    Raises:
        ValueError: если addr не является валидным IPv4.
    """
    if not addr or not addr.strip():
        raise ValueError(f"Поле «{field}» не может быть пустым")
    try:
        ipaddress.IPv4Address(addr.strip())
    except ValueError:
        raise ValueError(f"Некорректный IPv4 {field}: {addr!r}")


def validate_ipv4_mask(mask: str) -> None:
    """Проверяет что mask является валидной маской подсети IPv4.

    Допустимы только маски с непрерывными единицами (e.g. 255.255.255.0).
    Маски вида 255.255.0.255 (дырявые) — недопустимы.

    Raises:
        ValueError: если mask невалидна.
    """
    if not mask or not mask.strip():
        raise ValueError("Маска подсети не может быть пустой")
    try:
        packed = int(ipaddress.IPv4Address(mask.strip()))
    except ValueError:
        raise ValueError(f"Некорректная маска подсети: {mask!r}")
    # Проверяем что это непрерывная маска: packed | (packed - 1) == 0xFFFFFFFF
    # Эквивалентно: инвертированное значение должно быть степенью двойки минус 1
    inv = (~packed) & 0xFFFFFFFF
    if inv != 0 and (inv & (inv + 1)) != 0:
        raise ValueError(
            f"Маска подсети {mask!r} содержит непоследовательные биты. "
            "Используйте стандартную маску (например 255.255.255.0)."
        )


def validate_profile_network_fields(
    ipv4: str, mask: str, gateway: str,
    dns_primary: str, dns_secondary: str,
) -> None:
    """Валидирует сетевые поля статического профиля.

    Вызывать перед передачей в netsh. Поднимает ValueError с человекочитаемым
    описанием первого найденного нарушения.
    """
    validate_ipv4(ipv4, "IP-адрес")
    validate_ipv4_mask(mask)
    if gateway:
        validate_ipv4(gateway, "шлюз")
    if dns_primary:
        validate_ipv4(dns_primary, "основной DNS")
    if dns_secondary:
        validate_ipv4(dns_secondary, "дополнительный DNS")
