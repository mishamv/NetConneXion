"""Shared network utility functions."""


def prefix_to_mask(prefix: int) -> str:
    """Convert CIDR prefix length (e.g. 24) to dotted-decimal mask (e.g. 255.255.255.0)."""
    if not (0 <= prefix <= 32):
        return ""
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return ".".join(str((mask >> (8 * i)) & 0xFF) for i in reversed(range(4)))
