"""Keyring-based credential vault — fallback for Windows DPAPI.

Uses the system keyring (Windows Credential Manager on Windows) via the
``keyring`` library.  Secrets are never stored in the JSON profile file;
``key_protected`` stores only the sentinel ``"kr:"`` so the reader knows
to look up the actual secret by SSID name.

Requires: keyring >= 25.0  (``pip install keyring``)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SERVICE = "NetConneXion"


class KeyringUnavailableError(Exception):
    """Raised when the keyring package is not installed."""


class KeyringSecretNotFoundError(Exception):
    """Raised when no secret exists in keyring for the given SSID."""


def is_available() -> bool:
    """Return True if the keyring package is importable."""
    try:
        import keyring  # noqa: F401
        return True
    except ImportError:
        return False


def protect_text(ssid: str, plaintext: str) -> str:
    """Store *plaintext* in the system keyring under *ssid*.

    Returns the sentinel string ``"kr:"`` to be stored in ``key_protected``.

    Raises:
        KeyringUnavailableError: if the keyring package is not installed.
    """
    try:
        import keyring
    except ImportError as exc:
        raise KeyringUnavailableError(
            "keyring package is required. Install it with: pip install keyring"
        ) from exc

    keyring.set_password(_SERVICE, ssid, plaintext)
    logger.info("Secret stored in keyring for SSID=%r", ssid)
    return "kr:"


def unprotect_text(ssid: str) -> str:
    """Retrieve the secret for *ssid* from the system keyring.

    Raises:
        KeyringUnavailableError: if the keyring package is not installed.
        KeyringSecretNotFoundError: if no secret exists for this SSID.
    """
    try:
        import keyring
    except ImportError as exc:
        raise KeyringUnavailableError(
            "keyring package is required. Install it with: pip install keyring"
        ) from exc

    secret = keyring.get_password(_SERVICE, ssid)
    if secret is None:
        raise KeyringSecretNotFoundError(
            f"No keyring secret found for SSID={ssid!r}. "
            "Re-save the profile to store the password."
        )
    return secret


def delete(ssid: str) -> None:
    """Remove the keyring entry for *ssid* (no-op if not found or unavailable)."""
    try:
        import keyring
        keyring.delete_password(_SERVICE, ssid)
        logger.info("Keyring secret deleted for SSID=%r", ssid)
    except Exception:
        pass
