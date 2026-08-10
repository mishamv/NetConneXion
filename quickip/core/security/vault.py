"""Windows DPAPI credential vault.

Encrypts/decrypts secrets using the Windows Data Protection API.

Entropy scheme (v3):
  - Per-installation 32-byte random app seed stored in
    %PROGRAMDATA%\\NetConneXion\\entropy_seed.bin  — NOT in source code,
    NOT compiled into the binary.  Generated once at first launch.
  - Per-user 32-byte random key stored in HKCU registry.
  - Derived entropy = HMAC-SHA256(app_seed, user_key)

  This means an attacker who decompiles the binary gets nothing useful:
  the seed is only on the filesystem of the installed machine.

Blob format:
  "dpapi3:<base64>" — entropy = HMAC(file_seed, user_key).

Only the current v3 format is accepted. Unsupported stored credentials must be
re-entered and saved again by the user.

Requires: pywin32 >= 306 (``pip install pywin32``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Registry path for per-user installation key (HKCU)
_REG_KEY_PATH = r"Software\NetConneXion\Security"
_REG_VALUE_NAME = "EntropyKey"

# Blob version prefix
_V3_PREFIX = "dpapi3:"


# ── Exceptions ────────────────────────────────────────────────────────────────

class VaultUnavailableError(Exception):
    """Raised when pywin32 is not installed."""


class VaultPortabilityError(Exception):
    """Raised when data was encrypted on a different machine or user account."""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_programdata_dir() -> Path:
    """Return %PROGRAMDATA%\\NetConneXion, creating it if absent."""
    import os
    programdata = os.getenv("PROGRAMDATA", "")
    if not programdata:
        raise VaultUnavailableError("PROGRAMDATA environment variable not set")
    app_dir = Path(programdata) / "NetConneXion"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def _get_or_create_app_seed() -> bytes:
    """Return the per-installation 32-byte random app seed.

    Stored in %PROGRAMDATA%\\NetConneXion\\entropy_seed.bin (raw binary).
    Generated once at first launch; never stored in source code or binary.

    Raises VaultUnavailableError rather than returning an ephemeral seed:
    credentials must remain decryptable after the application restarts.
    """
    import secrets

    try:
        seed_file = _get_programdata_dir() / "entropy_seed.bin"
        if seed_file.exists():
            data = seed_file.read_bytes()
            if len(data) != 32:
                raise VaultUnavailableError(
                    f"DPAPI installation seed has invalid size: {len(data)} bytes."
                )
            return data
        # Generate and persist
        new_seed = secrets.token_bytes(32)
        seed_file.write_bytes(new_seed)
        logger.info("Generated new app entropy seed at %s", seed_file)
        return new_seed
    except OSError as exc:
        raise VaultUnavailableError(
            "Cannot read or persist the DPAPI installation seed."
        ) from exc


def _get_or_create_user_key() -> bytes:
    """Return per-user 32-byte key from HKCU registry, creating it if absent."""
    import secrets
    import winreg  # type: ignore

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY_PATH) as k:
            value, _ = winreg.QueryValueEx(k, _REG_VALUE_NAME)
            try:
                user_key = base64.b64decode(value, validate=True)
            except (TypeError, ValueError) as exc:
                raise VaultUnavailableError(
                    "DPAPI user key in the Windows registry is not valid base64."
                ) from exc
            if len(user_key) != 32:
                raise VaultUnavailableError(
                    f"DPAPI user key has invalid size: {len(user_key)} bytes."
                )
            return user_key
    except FileNotFoundError:
        pass

    user_key = secrets.token_bytes(32)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_KEY_PATH) as k:
            winreg.SetValueEx(
                k, _REG_VALUE_NAME, 0, winreg.REG_SZ,
                base64.b64encode(user_key).decode("ascii"),
            )
        logger.info("Created new DPAPI user entropy key in HKCU")
    except Exception as exc:
        raise VaultUnavailableError(
            "Cannot persist the DPAPI user key in the Windows registry."
        ) from exc
    return user_key


def _build_entropy() -> bytes:
    """Derive DPAPI entropy from the installation seed and per-user key."""
    seed = _get_or_create_app_seed()
    user_key = _get_or_create_user_key()
    return hmac.new(seed, user_key, hashlib.sha256).digest()


# ── Public API ────────────────────────────────────────────────────────────────

def protect_text(plaintext: str) -> str:
    """Encrypt *plaintext* using Windows DPAPI with per-installation entropy (v3).

    Returns a "dpapi3:<base64>" string suitable for JSON storage.
    The app seed comes from entropy_seed.bin — not from the binary.

    Raises:
        VaultUnavailableError: if pywin32 is not installed or PROGRAMDATA unavailable.
    """
    try:
        import win32crypt  # type: ignore
    except ImportError as exc:
        raise VaultUnavailableError(
            "pywin32 is required for credential encryption. "
            "Install it with: pip install pywin32"
        ) from exc

    entropy = _build_entropy()  # uses per-installation app seed
    raw = win32crypt.CryptProtectData(
        plaintext.encode("utf-8"),
        None,      # description
        entropy,   # prevents cross-process/cross-app decryption
        None,      # reserved
        None,      # prompt struct
        0,         # flags
    )
    return _V3_PREFIX + base64.b64encode(raw).decode("ascii")


def unprotect_text(ciphertext: str) -> str:
    """Decrypt a current-format ``dpapi3:`` credential.

    Raises:
        VaultUnavailableError: if pywin32 is not installed.
        VaultPortabilityError: if the format is unsupported or the data belongs
            to a different machine/account.
    """
    try:
        import win32crypt  # type: ignore
        import pywintypes  # type: ignore
    except ImportError as exc:
        raise VaultUnavailableError(
            "pywin32 is required for credential decryption. "
            "Install it with: pip install pywin32"
        ) from exc

    if not ciphertext.startswith(_V3_PREFIX):
        raise VaultPortabilityError(
            "Unsupported credential format. Re-enter and save the password."
        )

    raw = base64.b64decode(ciphertext[len(_V3_PREFIX):].encode("ascii"))
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

    return plaintext_bytes.decode("utf-8")
