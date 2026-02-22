"""Windows DPAPI credential vault.

Encrypts/decrypts secrets using the Windows Data Protection API so that
passwords are tied to the current Windows user account and machine.

Requires: pywin32 >= 306 (``pip install pywin32``).
"""

import base64
import logging

logger = logging.getLogger(__name__)


class VaultUnavailableError(Exception):
    """Raised when pywin32 is not installed."""


class VaultPortabilityError(Exception):
    """Raised when data was encrypted on a different machine or user account."""


def protect_text(plaintext: str) -> str:
    """Encrypt *plaintext* using Windows DPAPI.

    Returns a base64-encoded ciphertext string suitable for JSON storage.

    Raises:
        VaultUnavailableError: if pywin32 is not installed.
    """
    try:
        import win32crypt  # type: ignore
    except ImportError as exc:
        raise VaultUnavailableError(
            "pywin32 is required for credential encryption. "
            "Install it with: pip install pywin32"
        ) from exc

    raw = win32crypt.CryptProtectData(
        plaintext.encode("utf-8"),
        None,   # description
        None,   # entropy
        None,   # reserved
        None,   # prompt struct
        0,      # flags
    )
    return base64.b64encode(raw).decode("ascii")


def unprotect_text(ciphertext: str) -> str:
    """Decrypt a base64-encoded DPAPI *ciphertext*.

    Raises:
        VaultUnavailableError: if pywin32 is not installed.
        VaultPortabilityError: if data was encrypted by a different user/machine.
    """
    try:
        import win32crypt  # type: ignore
        import pywintypes  # type: ignore
    except ImportError as exc:
        raise VaultUnavailableError(
            "pywin32 is required for credential decryption. "
            "Install it with: pip install pywin32"
        ) from exc

    raw = base64.b64decode(ciphertext.encode("ascii"))
    try:
        _, plaintext_bytes = win32crypt.CryptUnprotectData(
            raw,
            None,   # entropy
            None,   # reserved
            None,   # prompt struct
            0,      # flags
        )
    except pywintypes.error as exc:
        raise VaultPortabilityError(
            "Credential was encrypted on a different machine or user account "
            "and cannot be decrypted here."
        ) from exc

    return plaintext_bytes.decode("utf-8")
