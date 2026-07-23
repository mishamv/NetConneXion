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

    def _make_mock_winreg(self):
        import base64 as _b64
        mock_winreg = types.ModuleType("winreg")
        mock_winreg.HKEY_CURRENT_USER = 0
        mock_winreg.REG_SZ = 1
        stored_key = _b64.b64encode(b"\x42" * 32).decode()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_winreg.OpenKey = MagicMock(return_value=ctx)
        mock_winreg.QueryValueEx = MagicMock(return_value=(stored_key, mock_winreg.REG_SZ))
        return mock_winreg

    def test_build_entropy_returns_32_bytes(self):
        # Mock winreg so the test runs on non-Windows / in CI
        # Patch _get_or_create_app_seed so no PROGRAMDATA access is needed
        mock_winreg = self._make_mock_winreg()
        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            from importlib import reload
            import quickip.core.security.vault as vault_mod
            reload(vault_mod)
            with patch.object(vault_mod, "_get_or_create_app_seed", return_value=b"\x01" * 32):
                entropy = vault_mod._build_entropy()
            assert isinstance(entropy, bytes)
            assert len(entropy) == 32

    def test_build_entropy_explicit_seed(self):
        """Passing an explicit seed uses that seed, not the app seed from disk."""
        mock_winreg = self._make_mock_winreg()
        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            from importlib import reload
            import quickip.core.security.vault as vault_mod
            reload(vault_mod)
            seed_a = b"\xAA" * 32
            seed_b = b"\xBB" * 32
            with patch.object(vault_mod, "_get_or_create_app_seed", side_effect=AssertionError("should not be called")):
                ent_a = vault_mod._build_entropy(seed_a)
                ent_b = vault_mod._build_entropy(seed_b)
            assert ent_a != ent_b, "Different seeds must produce different entropy"
            assert len(ent_a) == 32 and len(ent_b) == 32

    def test_build_entropy_legacy_seed_differs_from_app_seed(self):
        """LEGACY_SEED entropy must differ from per-installation entropy."""
        mock_winreg = self._make_mock_winreg()
        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            from importlib import reload
            import quickip.core.security.vault as vault_mod
            reload(vault_mod)
            fixed_app_seed = b"\xCC" * 32
            with patch.object(vault_mod, "_get_or_create_app_seed", return_value=fixed_app_seed):
                ent_app = vault_mod._build_entropy()
            ent_legacy = vault_mod._build_entropy(vault_mod._LEGACY_SEED)
            assert ent_app != ent_legacy


# ---------------------------------------------------------------------------
# Vault v3: _get_or_create_app_seed filesystem behaviour
# ---------------------------------------------------------------------------

class TestGetOrCreateAppSeed(unittest.TestCase):
    """_get_or_create_app_seed() reads/creates entropy_seed.bin correctly."""

    def _vault(self):
        import quickip.core.security.vault as v
        return v

    def test_returns_existing_32_byte_file(self):
        """If entropy_seed.bin exists with 32 bytes, return it unchanged."""
        import os
        existing_seed = b"\xDE\xAD" * 16
        vault = self._vault()
        with patch.dict(os.environ, {"PROGRAMDATA": "C:\\ProgramData"}):
            with patch("quickip.core.security.vault.Path") as MockPath:
                mock_dir = MagicMock()
                mock_dir.__truediv__ = lambda s, n: mock_dir
                mock_dir.mkdir = MagicMock()
                mock_seed_file = MagicMock()
                mock_seed_file.exists.return_value = True
                mock_seed_file.read_bytes.return_value = existing_seed
                mock_dir.__truediv__ = MagicMock(side_effect=lambda n: mock_seed_file if n == "entropy_seed.bin" else mock_dir)
                MockPath.return_value = mock_dir
                result = vault._get_or_create_app_seed()
        assert result == existing_seed

    def test_generates_and_saves_new_seed_if_missing(self, *_):
        """If entropy_seed.bin is missing, generate 32 random bytes and save."""
        import os, tempfile
        vault = self._vault()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"PROGRAMDATA": tmp}):
                seed = vault._get_or_create_app_seed()
            assert isinstance(seed, bytes)
            assert len(seed) == 32
            seed_path = __import__("pathlib").Path(tmp) / "NetConneXion" / "entropy_seed.bin"
            assert seed_path.exists()
            assert seed_path.read_bytes() == seed

    def test_returns_ephemeral_seed_on_os_error(self):
        """If write fails, still returns a 32-byte seed without raising."""
        import os
        vault = self._vault()
        with patch.dict(os.environ, {"PROGRAMDATA": "C:\\ProgramData"}):
            with patch("quickip.core.security.vault._get_programdata_dir", side_effect=OSError("permission denied")):
                seed = vault._get_or_create_app_seed()
        assert isinstance(seed, bytes)
        assert len(seed) == 32

    def test_v3_prefix_in_protect_text(self):
        """protect_text() must produce dpapi3: blobs, not dpapi2:."""
        mock_win32crypt = types.ModuleType("win32crypt")
        mock_win32crypt.CryptProtectData = MagicMock(return_value=b"\x00" * 16)
        mock_winreg = types.ModuleType("winreg")
        mock_winreg.HKEY_CURRENT_USER = 0
        mock_winreg.REG_SZ = 1
        import base64 as _b
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_winreg.OpenKey = MagicMock(return_value=ctx)
        mock_winreg.QueryValueEx = MagicMock(return_value=(_b.b64encode(b"\x01" * 32).decode(), 1))
        import quickip.core.security.vault as vault_mod
        with patch.dict(sys.modules, {"win32crypt": mock_win32crypt, "winreg": mock_winreg}):
            with patch.object(vault_mod, "_get_or_create_app_seed", return_value=b"\x02" * 32):
                result = vault_mod.protect_text("secret")
        assert result.startswith("dpapi3:"), f"Expected dpapi3: prefix, got: {result[:12]!r}"


# ---------------------------------------------------------------------------
# NEW: WifiService.connect() blocks b64 profiles
# ---------------------------------------------------------------------------

class TestB64Blocked(unittest.TestCase):
    """WifiService.connect() must refuse b64-encoded profiles (T1552.001)."""

    def _make_service(self, vault_available: bool = True):
        from quickip.features.wifi.service import WifiService
        container = MagicMock()
        container.process_runner = MagicMock()
        container.vault_available = vault_available
        return WifiService(container)

    def _make_profile(self, key_protected: str):
        from quickip.features.wifi.repository import WifiProfile
        return WifiProfile(
            id="test-id", ssid="TestNet", auth="WPA2-Personal",
            cipher="AES", key_protected=key_protected,
        )

    def test_b64_profile_blocked_vault_available(self):
        """b64: profile должен быть отклонён даже при доступном vault."""
        import base64
        svc = self._make_service(vault_available=True)
        profile = self._make_profile("b64:" + base64.b64encode(b"password").decode())
        result = svc.connect("TestNet", profile)
        self.assertFalse(result.success)
        self.assertIn("b64", result.message.lower())

    def test_b64_profile_blocked_no_vault(self):
        """b64: profile должен быть отклонён и без vault."""
        import base64
        svc = self._make_service(vault_available=False)
        profile = self._make_profile("b64:" + base64.b64encode(b"password").decode())
        result = svc.connect("TestNet", profile)
        self.assertFalse(result.success)

    def test_dpapi_profile_not_blocked(self):
        """dpapi2: профиль не блокируется b64-проверкой.

        win32crypt недоступен на Linux — мокируем весь модуль,
        проверяем только что b64-блок-сообщение НЕ возвращается.
        """
        import types
        mock_win32 = types.ModuleType("win32crypt")
        mock_pywintypes = types.ModuleType("pywintypes")
        mock_pywintypes.error = Exception

        _B64_BLOCK_MSG = "b64"  # маркер, который присутствует в b64-блокировке

        svc = self._make_service(vault_available=True)
        profile = self._make_profile("dpapi2:AAAA")

        with patch.dict(sys.modules, {"win32crypt": mock_win32,
                                       "pywintypes": mock_pywintypes}):
            # CryptUnprotectData выбрасывает ошибку (невалидный blob) — это не b64-блок
            mock_win32.CryptUnprotectData = MagicMock(
                side_effect=mock_pywintypes.error("bad blob")
            )
            try:
                result = svc.connect("TestNet", profile)
                # Если вернулся ConnectResult — убеждаемся что это не b64-ошибка
                self.assertNotIn(_B64_BLOCK_MSG, (result.message or "").lower())
            except Exception as exc:
                # VaultUnavailableError или другое — главное, это не b64-блок
                self.assertNotIn(_B64_BLOCK_MSG, str(exc).lower())


# ---------------------------------------------------------------------------
# NEW: build_profile_xml rejects WEP
# ---------------------------------------------------------------------------

class TestWepBlocked(unittest.TestCase):

    def test_wep_raises_value_error(self):
        from quickip.features.wifi.xml_builder import build_profile_xml
        with self.assertRaises(ValueError) as ctx:
            build_profile_xml(ssid="TestNet", auth="WEP", cipher="WEP", password="secret")
        self.assertIn("WEP", str(ctx.exception))

    def test_wpa2_builds_ok(self):
        from quickip.features.wifi.xml_builder import build_profile_xml
        xml = build_profile_xml(ssid="TestNet", auth="WPA2-Personal",
                                cipher="AES", password="password123")
        self.assertIn("WPA2PSK", xml)
        self.assertIn("TestNet", xml)

    def test_wep_not_in_auth_options(self):
        from quickip.features.wifi.repository import AUTH_OPTIONS
        self.assertNotIn("WEP", AUTH_OPTIONS)


# ---------------------------------------------------------------------------
# NEW: validate_ipv4 / validate_ipv4_mask / validate_profile_network_fields
# ---------------------------------------------------------------------------

class TestNetUtils(unittest.TestCase):

    def setUp(self):
        from quickip.shared.net_utils import (
            validate_ipv4, validate_ipv4_mask, validate_profile_network_fields
        )
        self.validate_ipv4 = validate_ipv4
        self.validate_mask = validate_ipv4_mask
        self.validate_fields = validate_profile_network_fields

    # validate_ipv4
    def test_valid_ip(self):
        self.validate_ipv4("192.168.1.1")

    def test_empty_ip_raises(self):
        with self.assertRaises(ValueError):
            self.validate_ipv4("")

    def test_invalid_ip_raises(self):
        with self.assertRaises(ValueError):
            self.validate_ipv4("999.0.0.1")

    def test_text_not_ip_raises(self):
        with self.assertRaises(ValueError):
            self.validate_ipv4("not-an-ip")

    def test_injection_attempt_raises(self):
        with self.assertRaises(ValueError):
            self.validate_ipv4("192.168.1.1; rm -rf /")

    # validate_ipv4_mask
    def test_valid_mask_24(self):
        self.validate_mask("255.255.255.0")

    def test_valid_mask_16(self):
        self.validate_mask("255.255.0.0")

    def test_valid_mask_32(self):
        self.validate_mask("255.255.255.255")

    def test_valid_mask_0(self):
        self.validate_mask("0.0.0.0")

    def test_invalid_mask_holey(self):
        with self.assertRaises(ValueError):
            self.validate_mask("255.0.255.0")  # дырявая маска

    def test_empty_mask_raises(self):
        with self.assertRaises(ValueError):
            self.validate_mask("")

    # validate_profile_network_fields
    def test_valid_profile_fields(self):
        self.validate_fields("192.168.1.100", "255.255.255.0",
                             "192.168.1.1", "8.8.8.8", "8.8.4.4")

    def test_invalid_ip_in_profile_raises(self):
        with self.assertRaises(ValueError):
            self.validate_fields("300.0.0.1", "255.255.255.0", "", "", "")

    def test_invalid_gateway_raises(self):
        with self.assertRaises(ValueError):
            self.validate_fields("192.168.1.1", "255.255.255.0",
                                 "not-a-gateway", "", "")

    def test_invalid_dns_raises(self):
        with self.assertRaises(ValueError):
            self.validate_fields("192.168.1.1", "255.255.255.0",
                                 "192.168.1.1", "bad-dns", "")

    def test_empty_optional_fields_ok(self):
        # gateway, dns — опциональные, пустые строки допустимы
        self.validate_fields("10.0.0.50", "255.0.0.0", "", "", "")


if __name__ == "__main__":
    unittest.main()
