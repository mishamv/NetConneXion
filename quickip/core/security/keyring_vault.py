"""Keyring-based credential vault — fallback for Windows DPAPI.

Uses the system keyring (Windows Credential Manager on Windows) via the
``keyring`` library. Secrets are keyed by **profile UUID**, not SSID.

Key format in ``key_protected``:
  ``"kr:<profile_uuid>"`` — stored as username ``"wifi:<uuid>"``.

Using UUID avoids collisions when two profiles share the same SSID but have
different passwords (e.g. home vs office network with same name), and makes
rename/reimport safe.

Requires: keyring >= 25.0  (``pip install keyring``)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SERVICE = "NetConneXion"
_PREFIX = "wifi:"   # keyring username prefix → "wifi:<uuid>"


class KeyringUnavailableError(Exception):
    """Raised when the keyring package is not installed."""


class KeyringSecretNotFoundError(Exception):
    """Raised when no secret exists in keyring for the given profile ID."""


def is_available() -> bool:
    """Return True if keyring is installed AND uses a secure backend.

    Checking only ``import keyring`` is insufficient: keyring may fall back to
    a plaintext ``FileKeyring`` or ``fail.Keyring`` (raises on every operation)
    when no system keyring is configured.

    On Windows we require ``WinVaultKeyring`` (Windows Credential Manager).
    On other platforms we accept any backend with ``priority > 0``
    (plaintext ``ChainerKeyring`` / ``fail.Keyring`` have priority ≤ 0).
    """
    try:
        import keyring
        import platform

        backend = keyring.get_keyring()
        backend_name = type(backend).__name__

        if platform.system().lower() == "windows":
            # На Windows единственный приемлемый secure backend — Credential Manager.
            # Имя класса может быть WinVaultKeyring или похожим.
            secure = "winvault" in backend_name.lower() or "windows" in backend_name.lower()
            if not secure:
                logger.warning(
                    "keyring backend is %r — not Windows Credential Manager. "
                    "Falling back to DPAPI.", backend_name
                )
            return secure
        else:
            # Не-Windows: проверяем priority (plaintext и fail имеют priority ≤ 0)
            priority = getattr(backend, "priority", 1)
            if priority <= 0:
                logger.warning("keyring backend %r has priority=%s — insecure", backend_name, priority)
            return priority > 0

    except Exception as exc:
        logger.debug("keyring availability check failed: %s", exc)
        return False


# ── Write ─────────────────────────────────────────────────────────────────────

def protect_text(profile_id: str, plaintext: str) -> str:
    """Store *plaintext* in the system keyring under *profile_id*.

    The keyring username is ``"wifi:<profile_id>"`` to namespace entries and
    avoid collisions with other apps using the same service name.

    Returns the sentinel ``"kr:<profile_id>"`` to be stored in ``key_protected``.

    Raises:
        KeyringUnavailableError: if the keyring package is not installed.
    """
    try:
        import keyring
    except ImportError as exc:
        raise KeyringUnavailableError(
            "keyring package is required. Install it with: pip install keyring"
        ) from exc

    username = _PREFIX + profile_id
    keyring.set_password(_SERVICE, username, plaintext)
    logger.info("Secret stored in keyring for profile_id=%r", profile_id)
    return f"kr:{profile_id}"


# ── Read ──────────────────────────────────────────────────────────────────────

def unprotect_text(profile_id: str) -> str:
    """Retrieve the secret for *profile_id* from the system keyring.

    Raises:
        KeyringUnavailableError: if the keyring package is not installed.
        KeyringSecretNotFoundError: if no secret exists for this profile.
    """
    try:
        import keyring
    except ImportError as exc:
        raise KeyringUnavailableError(
            "keyring package is required. Install it with: pip install keyring"
        ) from exc

    username = _PREFIX + profile_id
    secret = keyring.get_password(_SERVICE, username)
    if secret is None:
        raise KeyringSecretNotFoundError(
            f"No keyring secret found for profile_id={profile_id!r}. "
            "Re-save the profile to store the password."
        )
    return secret



# ── Delete ────────────────────────────────────────────────────────────────────

def delete(profile_id: str) -> None:
    """Remove the keyring entry for *profile_id* (no-op if not found or unavailable)."""
    try:
        import keyring
        username = _PREFIX + profile_id
        keyring.delete_password(_SERVICE, username)
        logger.info("Keyring secret deleted for profile_id=%r", profile_id)
    except Exception:
        pass  # best-effort
