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
  "dpapi2:<base64>"  — v2 legacy blobs (entropy = HMAC(hardcoded_seed, user_key))
  "dpapi3:<base64>"  — v3 blobs      (entropy = HMAC(file_seed, user_key))

  unprotect_text() handles both prefixes transparently.
  protect_text() always writes v3 blobs.

  When a v2 blob is successfully decrypted, the caller should re-save the
  profile so it gets upgraded to v3 (the reauth dialog handles this automatically).

Backward compatibility:
  - "dpapi2:" blobs: try with file seed first (in case user re-saved after upgrade),
    then fall back to the legacy hardcoded seed.
  - Plain base64 (no prefix): legacy pre-v2, decrypted without entropy.
  - _LEGACY_SEED will be removed in a future release once all profiles are migrated.

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

# Legacy hardcoded seed — kept ONLY for backward-compat decryption of dpapi2: blobs
# created before the v3 upgrade.  New protect_text() calls never use this.
# TODO: remove after all profiles have been re-saved under v3.
_LEGACY_SEED = b"NetConneXion-quickip-v2-entropy-2024"

# Registry path for per-user installation key (HKCU)
_REG_KEY_PATH = r"Software\NetConneXion\Security"
_REG_VALUE_NAME = "EntropyKey"

# Blob version prefixes
_V2_PREFIX = "dpapi2:"   # legacy: HMAC(hardcoded_seed, user_key)
_V3_PREFIX = "dpapi3:"   # current: HMAC(file_seed, user_key)


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

    Falls back to an ephemeral seed (logged as warning) if the file can't
    be written — e.g. running without write access to PROGRAMDATA.
    """
    import secrets

    try:
        seed_file = _get_programdata_dir() / "entropy_seed.bin"
        if seed_file.exists():
            data = seed_file.read_bytes()
            if len(data) == 32:
                return data
            logger.warning(
                "entropy_seed.bin has unexpected size (%d bytes) — regenerating", len(data)
            )
        # Generate and persist
        new_seed = secrets.token_bytes(32)
        seed_file.write_bytes(new_seed)
        logger.info("Generated new app entropy seed at %s", seed_file)
        return new_seed
    except OSError as exc:
        logger.warning(
            "Cannot persist entropy_seed.bin (%s) — using ephemeral seed. "
            "DPAPI blobs created now will not survive a restart.", exc
        )
        return secrets.token_bytes(32)


def _get_or_create_user_key() -> bytes:
    """Return per-user 32-byte key from HKCU registry, creating it if absent."""
    import secrets
    import winreg  # type: ignore

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY_PATH) as k:
            value, _ = winreg.QueryValueEx(k, _REG_VALUE_NAME)
            return base64.b64decode(value)
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
        logger.warning("Could not persist user entropy key: %s", exc)
    return user_key


def _build_entropy(seed: bytes | None = None) -> bytes:
    """Derive DPAPI entropy from *seed* + per-user key.

    If *seed* is None, the per-installation app seed is loaded from
    ``entropy_seed.bin`` via :func:`_get_or_create_app_seed`.
    Pass an explicit seed (e.g. ``_LEGACY_SEED``) to derive legacy entropy.
    """
    if seed is None:
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
    """Decrypt a DPAPI *ciphertext*.

    Handles all three formats:
    - "dpapi3:<base64>" — v3: uses per-installation file seed
    - "dpapi2:<base64>" — v2 legacy: tries file seed first, then hardcoded seed
    - plain base64      — pre-v2 legacy: no entropy

    After successfully decrypting a v2 blob with the legacy hardcoded seed,
    the caller should re-save the profile to upgrade it to v3.

    Raises:
        VaultUnavailableError: if pywin32 is not installed.
        VaultPortabilityError: if data was encrypted on a different machine/account.
    """
    try:
        import win32crypt  # type: ignore
        import pywintypes  # type: ignore
    except ImportError as exc:
        raise VaultUnavailableError(
            "pywin32 is required for credential decryption. "
            "Install it with: pip install pywin32"
        ) from exc

    if ciphertext.startswith(_V3_PREFIX):
        raw = base64.b64decode(ciphertext[len(_V3_PREFIX):].encode("ascii"))
        entropy = _build_entropy()  # uses per-installation app seed
        try:
            _, plaintext_bytes = win32crypt.CryptUnprotectData(
                raw, entropy, None, None, 0,
            )
        except pywintypes.error as exc:
            raise VaultPortabilityError(
                "Credential was encrypted on a different machine or user account "
                "and cannot be decrypted here."
            ) from exc

    elif ciphertext.startswith(_V2_PREFIX):
        raw = base64.b64decode(ciphertext[len(_V2_PREFIX):].encode("ascii"))
        # Try with current file seed first (user may have re-saved after upgrade)
        try:
            _, plaintext_bytes = win32crypt.CryptUnprotectData(
                raw, _build_entropy(), None, None, 0,
            )
            logger.debug("Decrypted dpapi2: blob with current file seed")
        except pywintypes.error:
            # Fall back to legacy hardcoded seed (pre-v3 blob)
            try:
                _, plaintext_bytes = win32crypt.CryptUnprotectData(
                    raw, _build_entropy(_LEGACY_SEED), None, None, 0,
                )
                logger.info(
                    "Decrypted legacy dpapi2: blob with hardcoded seed — "
                    "profile will be upgraded to v3 on next save"
                )
            except pywintypes.error as exc:
                raise VaultPortabilityError(
                    "Credential was encrypted on a different machine or user account "
                    "and cannot be decrypted here."
                ) from exc

    else:
        # Pre-v2 legacy blob — no entropy at all
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
