"""Windows DPAPI credential vault.

Encrypts/decrypts secrets using the Windows Data Protection API so that
passwords are tied to the current Windows user account and machine.

Entropy scheme (v2):
  - App-level seed compiled into the binary (_APP_ENTROPY_SEED)
  - Per-installation 32-byte random key stored in HKCU registry
  - Derived entropy = HMAC-SHA256(seed, machine_key)
  This means even another process running as the same user cannot decrypt
  the blob with plain CryptUnprotectData (would need the entropy).

Backward compatibility:
  - New blobs are prefixed with "dpapi2:" and use entropy.
  - Old blobs (plain base64, no prefix) are decrypted without entropy.
  - All new protect_text() calls use v2 scheme automatically.

Requires: pywin32 >= 306 (``pip install pywin32``).
"""

import base64
import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)

# Hardcoded app-level entropy seed (compiled into binary).
# MITRE T1555.004: prevents mimikatz dpapi::blob without this seed.
_APP_ENTROPY_SEED = b"NetConneXion-quickip-v2-entropy-2024"

# Registry path for per-installation machine key (HKCU)
_REG_KEY_PATH = r"Software\NetConneXion\Security"
_REG_VALUE_NAME = "EntropyKey"

# Prefix distinguishing v2 (entropy) blobs from legacy (no entropy)
_V2_PREFIX = "dpapi2:"


class VaultUnavailableError(Exception):
    """Raised when pywin32 is not installed."""


class VaultPortabilityError(Exception):
    """Raised when data was encrypted on a different machine or user account."""


def _get_or_create_machine_key() -> bytes:
    """Return per-installation 32-byte key from HKCU registry, creating it if absent."""
    import secrets
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY_PATH) as k:
            value, _ = winreg.QueryValueEx(k, _REG_VALUE_NAME)
            return base64.b64decode(value)
    except FileNotFoundError:
        pass

    machine_key = secrets.token_bytes(32)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_KEY_PATH) as k:
            winreg.SetValueEx(
                k, _REG_VALUE_NAME, 0, winreg.REG_SZ,
                base64.b64encode(machine_key).decode("ascii"),
            )
        logger.info("Created new DPAPI machine entropy key in HKCU")
    except Exception as exc:
        logger.warning("Could not persist machine entropy key: %s", exc)
    return machine_key


def _build_entropy() -> bytes:
    """Derive app-specific DPAPI entropy bytes."""
    machine_key = _get_or_create_machine_key()
    return hmac.new(_APP_ENTROPY_SEED, machine_key, hashlib.sha256).digest()


def protect_text(plaintext: str) -> str:
    """Encrypt *plaintext* using Windows DPAPI with app-specific entropy (v2).

    Returns a "dpapi2:<base64>" string suitable for JSON storage.

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

    entropy = _build_entropy()
    raw = win32crypt.CryptProtectData(
        plaintext.encode("utf-8"),
        None,      # description
        entropy,   # app-specific entropy — prevents cross-process decryption
        None,      # reserved
        None,      # prompt struct
        0,         # flags
    )
    return _V2_PREFIX + base64.b64encode(raw).decode("ascii")


def unprotect_text(ciphertext: str) -> str:
    """Decrypt a DPAPI *ciphertext* (v2 with entropy, or legacy without).

    Handles both:
    - New "dpapi2:<base64>" blobs (v2, with app entropy)
    - Old plain base64 blobs (legacy, no entropy — backward compat)

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

    if ciphertext.startswith(_V2_PREFIX):
        # v2 blob — decrypt with app-specific entropy
        raw = base64.b64decode(ciphertext[len(_V2_PREFIX):].encode("ascii"))
        entropy = _build_entropy()
        try:
            _, plaintext_bytes = win32crypt.CryptUnprotectData(
                raw, entropy, None, None, 0,
            )
        except pywintypes.error as exc:
            raise VaultPortabilityError(
                "Credential was encrypted on a different machine or user account "
                "and cannot be decrypted here."
            ) from exc
    else:
        # Legacy blob — no entropy (backward compat for profiles saved before v2)
        raw = base64.b64decode(ciphertext.encode("ascii"))
        try:
            _, plaintext_bytes = win32crypt.CryptUnprotectData(
                raw, None, None, None, 0,
            )
        except pywintypes.error as exc:
            raise VaultPortabilityError(
                "Credential was encrypted on a different machine or user account "
                "and cannot be decrypted here."
            ) from exc

    return plaintext_bytes.decode("utf-8")
