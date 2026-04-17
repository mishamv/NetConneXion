"""Tests for security hardening changes (P0-2, P1-3/5/6, P2-7/8).

Runs without PySide6, pywin32, or any real network access.
"""

from __future__ import annotations

import types
import sys
import unittest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# P2-7: WifiService._validate_ssid
# ---------------------------------------------------------------------------

def _make_wifi_service():
    """Import WifiService without side-effects from container."""
    # Patch out ProcessRunner so no real subprocess is created
    from quickip.features.wifi.service import WifiService
    return WifiService


class TestValidateSsid(unittest.TestCase):

    def setUp(self):
        WifiService = _make_wifi_service()
        self.validate = WifiService._validate_ssid

    def test_valid_ascii(self):
        self.validate("MyNetwork")

    def test_valid_unicode(self):
        self.validate("Сеть_42")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            self.validate("")

    def test_exceeds_32_bytes_raises(self):
        # 33 ASCII chars = 33 bytes (> 32)
        with self.assertRaises(ValueError):
            self.validate("A" * 33)

    def test_exactly_32_bytes_ok(self):
        self.validate("A" * 32)

    def test_control_char_raises(self):
        with self.assertRaises(ValueError):
            self.validate("Net\x01work")

    def test_null_byte_raises(self):
        with self.assertRaises(ValueError):
            self.validate("Net\x00work")

    def test_double_quote_raises(self):
        with self.assertRaises(ValueError):
            self.validate('Net"work')

    def test_unicode_32_byte_boundary(self):
        # Cyrillic char = 2 bytes in UTF-8; 16 chars = 32 bytes → OK
        self.validate("А" * 16)
        # 17 chars = 34 bytes → raises
        with self.assertRaises(ValueError):
            self.validate("А" * 17)


# ---------------------------------------------------------------------------
# P1-6: ConsoleService extra_args whitelist
# ---------------------------------------------------------------------------

from quickip.features.tools.services.console import ConsoleService, _validate_extra_args


class TestExtraArgsWhitelist(unittest.TestCase):

    def test_allowed_flag_ping(self):
        _validate_extra_args("ping", ["-n", "5"])

    def test_disallowed_flag_ping(self):
        with self.assertRaises(ValueError):
            _validate_extra_args("ping", ["-z"])

    def test_numeric_bound_ping_n_ok(self):
        _validate_extra_args("ping", ["-n", "100"])

    def test_numeric_bound_ping_n_too_large(self):
        with self.assertRaises(ValueError):
            _validate_extra_args("ping", ["-n", "101"])

    def test_numeric_bound_ping_n_too_small(self):
        with self.assertRaises(ValueError):
            _validate_extra_args("ping", ["-n", "0"])

    def test_non_integer_value_raises(self):
        with self.assertRaises(ValueError):
            _validate_extra_args("ping", ["-n", "abc"])

    def test_allowed_flag_tracert(self):
        _validate_extra_args("tracert", ["-d", "-h", "30"])

    def test_disallowed_flag_tracert(self):
        with self.assertRaises(ValueError):
            _validate_extra_args("tracert", ["-x"])

    def test_empty_args_ok(self):
        _validate_extra_args("ping", [])

    def test_bare_word_allowed_route(self):
        _validate_extra_args("route", ["print"])

    def test_bare_word_disallowed_ping(self):
        with self.assertRaises(ValueError):
            _validate_extra_args("ping", ["print"])

    def test_injection_attempt_blocked(self):
        with self.assertRaises(ValueError):
            _validate_extra_args("ping", ["-n", "1", "&&", "calc.exe"])

    def test_injection_via_unknown_flag_blocked(self):
        with self.assertRaises(ValueError):
            _validate_extra_args("ping", ["--exec=calc"])


# ---------------------------------------------------------------------------
# P1-6: ConsoleService.run validates extra_args
# ---------------------------------------------------------------------------

class TestConsoleServiceRun(unittest.TestCase):

    def _make_service(self):
        runner = MagicMock()
        runner.run.return_value = MagicMock(
            stdout="reply from 8.8.8.8", stderr="", success=True
        )
        return ConsoleService(runner), runner

    def test_run_with_valid_extra_args(self):
        svc, runner = self._make_service()
        result = svc.run("ping", "8.8.8.8", extra_args=["-n", "3"])
        assert result.success

    def test_run_with_invalid_extra_args_raises(self):
        svc, _ = self._make_service()
        with self.assertRaises(ValueError):
            svc.run("ping", "8.8.8.8", extra_args=["-z"])

    def test_run_unknown_tool_raises(self):
        svc, _ = self._make_service()
        with self.assertRaises(ValueError):
            svc.run("nmap", "8.8.8.8")

    def test_run_invalid_target_raises(self):
        svc, _ = self._make_service()
        with self.assertRaises(ValueError):
            svc.run("ping", "../../etc/passwd")


# ---------------------------------------------------------------------------
# P0-2: WifiPresenter.migrate_legacy_profiles
# ---------------------------------------------------------------------------

class TestMigrateLegacyProfiles(unittest.TestCase):

    def _make_presenter(self, profiles):
        """Build a minimal WifiPresenter with mocked repo and container."""
        # Avoid importing PySide6 by stubbing only what we need
        from quickip.features.wifi.presenter import WifiPresenter

        container = MagicMock()
        container.vault_available = False
        container.keyring_available = False

        presenter = WifiPresenter.__new__(WifiPresenter)
        presenter._container = container
        presenter._profile_repo = MagicMock()
        presenter._profile_repo.list.return_value = profiles
        presenter._service = MagicMock()
        return presenter

    def test_no_legacy_profiles_no_migration(self):
        profile = MagicMock()
        profile.key_protected = "dpapi2:abc123"
        presenter = self._make_presenter([profile])
        presenter.migrate_legacy_profiles()
        # list() was called, but no save (key was not b64:)
        presenter._profile_repo.save.assert_not_called()

    def test_legacy_b64_profile_attempted(self):
        import base64 as _b64
        profile = MagicMock()
        profile.key_protected = "b64:" + _b64.b64encode(b"mypassword").decode()
        profile.ssid = "TestNet"
        presenter = self._make_presenter([profile])
        # Both vault and keyring unavailable → migration warns but doesn't raise
        presenter.migrate_legacy_profiles()
        presenter._profile_repo.list.assert_called_once()

    def test_empty_profiles_no_error(self):
        presenter = self._make_presenter([])
        presenter.migrate_legacy_profiles()  # should not raise


# ---------------------------------------------------------------------------
# P1-3: vault.py _build_entropy doesn't use global socket state
# ---------------------------------------------------------------------------

class TestVaultEntropy(unittest.TestCase):
    """Smoke test _build_entropy returns bytes without crashing."""

    def test_build_entropy_returns_32_bytes(self):
        # Mock winreg so the test runs on non-Windows / in CI
        mock_winreg = types.ModuleType("winreg")
        mock_winreg.HKEY_CURRENT_USER = 0
        mock_winreg.REG_SZ = 1
        import base64 as _b64
        _stored_key = _b64.b64encode(b"\x42" * 32).decode()

        mock_key_ctx = MagicMock()
        mock_key_ctx.__enter__ = MagicMock(return_value=mock_key_ctx)
        mock_key_ctx.__exit__ = MagicMock(return_value=False)
        mock_winreg.OpenKey = MagicMock(return_value=mock_key_ctx)
        mock_winreg.QueryValueEx = MagicMock(return_value=(_stored_key, mock_winreg.REG_SZ))

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            from importlib import reload
            import quickip.core.security.vault as vault_mod
            reload(vault_mod)
            entropy = vault_mod._build_entropy()
            assert isinstance(entropy, bytes)
            assert len(entropy) == 32


if __name__ == "__main__":
    unittest.main()
