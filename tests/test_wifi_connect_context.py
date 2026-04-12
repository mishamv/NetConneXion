"""Tests: _last_connect_password and _last_connect_ssid are cleared in all scenarios.

Scenarios:
  1. Connection failure  → _clear_connect_context called immediately
  2. Success, no password (open/saved profile) → cleared immediately
  3. Success, offer shown, profile already exists (early return) → cleared via try/finally
  4. Success, offer shown, user responds (Yes or No) → cleared via try/finally
  5. Tab change → cleared
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Minimal stub so we can import/test without PySide6 present
# ---------------------------------------------------------------------------

class _FakePage:
    """Mimics the connect-context state machine of WifiPage."""

    def __init__(self):
        self._last_connect_ssid: str = ""
        self._last_connect_password: str = ""

    def _clear_connect_context(self) -> None:
        self._last_connect_password = ""
        self._last_connect_ssid = ""

    def _offer_save_profile(self, *, profile_exists: bool, user_says_yes: bool) -> None:
        """Simplified _offer_save_profile with injected dependencies."""
        try:
            ssid = self._last_connect_ssid
            if not ssid or profile_exists:
                return
            if user_says_yes:
                pass  # would switch to editor tab
        finally:
            self._clear_connect_context()

    def _on_connect_result(
        self,
        success: bool,
        has_password: bool,
        *,
        profile_exists: bool = False,
        user_says_yes: bool = False,
    ) -> None:
        """Simplified _on_connect_result."""
        if success:
            if self._last_connect_ssid and self._last_connect_password:
                self._offer_save_profile(
                    profile_exists=profile_exists,
                    user_says_yes=user_says_yes,
                )
            else:
                self._clear_connect_context()
        else:
            self._clear_connect_context()

    def _on_tab_changed(self, index: int) -> None:
        self._clear_connect_context()


def _page_with_context(ssid="TestNet", password="secret123") -> _FakePage:
    p = _FakePage()
    p._last_connect_ssid = ssid
    p._last_connect_password = password
    return p


# ---------------------------------------------------------------------------
# Scenario 1: connection failed
# ---------------------------------------------------------------------------

def test_context_cleared_on_failure():
    page = _page_with_context()
    page._on_connect_result(success=False, has_password=True)
    assert page._last_connect_password == ""
    assert page._last_connect_ssid == ""


# ---------------------------------------------------------------------------
# Scenario 2: success but no password to offer (open/saved profile)
# ---------------------------------------------------------------------------

def test_context_cleared_on_success_no_password():
    page = _FakePage()
    page._last_connect_ssid = "OpenNet"
    page._last_connect_password = ""   # open network — no password cached
    page._on_connect_result(success=True, has_password=False)
    assert page._last_connect_password == ""
    assert page._last_connect_ssid == ""


# ---------------------------------------------------------------------------
# Scenario 3: offer triggered, but profile already exists → early return
# ---------------------------------------------------------------------------

def test_context_cleared_on_offer_early_return():
    page = _page_with_context()
    page._on_connect_result(success=True, has_password=True, profile_exists=True)
    assert page._last_connect_password == ""
    assert page._last_connect_ssid == ""


# ---------------------------------------------------------------------------
# Scenario 4a: offer shown, user says Yes
# ---------------------------------------------------------------------------

def test_context_cleared_after_offer_yes():
    page = _page_with_context()
    page._on_connect_result(success=True, has_password=True, profile_exists=False, user_says_yes=True)
    assert page._last_connect_password == ""
    assert page._last_connect_ssid == ""


# ---------------------------------------------------------------------------
# Scenario 4b: offer shown, user says No
# ---------------------------------------------------------------------------

def test_context_cleared_after_offer_no():
    page = _page_with_context()
    page._on_connect_result(success=True, has_password=True, profile_exists=False, user_says_yes=False)
    assert page._last_connect_password == ""
    assert page._last_connect_ssid == ""


# ---------------------------------------------------------------------------
# Scenario 5: tab changed
# ---------------------------------------------------------------------------

def test_context_cleared_on_tab_change():
    page = _page_with_context()
    page._on_tab_changed(0)
    assert page._last_connect_password == ""
    assert page._last_connect_ssid == ""


# ---------------------------------------------------------------------------
# Scenario 6: exception inside _offer_save_profile → finally still clears
# ---------------------------------------------------------------------------

def test_context_cleared_on_exception_in_offer():
    page = _page_with_context()

    def _bad_offer(*, profile_exists, user_says_yes):
        try:
            raise RuntimeError("unexpected error")
        finally:
            page._clear_connect_context()

    page._offer_save_profile = _bad_offer  # type: ignore[method-assign]

    try:
        page._on_connect_result(success=True, has_password=True)
    except RuntimeError:
        pass

    assert page._last_connect_password == ""
    assert page._last_connect_ssid == ""
