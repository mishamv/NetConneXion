"""Tests for P0/P1 features added during review cycle.

Covers:
  - ScannerService._expand_target: host limit enforcement, lazy generator
  - ManagedProcess: cancel() terminates process, no zombie; kill() backward-compat
  - keyring_vault UUID scheme: protect/unprotect/delete
  - WifiService.scan_networks: cached result returned during active scan
"""

from __future__ import annotations

import subprocess
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, call
from typing import List


# ── ScannerService._expand_target ─────────────────────────────────────────────

class TestExpandTarget(unittest.TestCase):

    def _expand(self, target: str, allow_large: bool = False):
        from quickip.features.tools.services.scanner import ScannerService
        # _expand_target is a static-ish method; instantiate with dummy runner
        runner = MagicMock()
        svc = ScannerService(runner)
        return svc._expand_target(target, allow_large=allow_large)

    # ── single host ────────────────────────────────────────────────

    def test_single_ip_returns_itself(self):
        gen, total = self._expand("192.168.1.1")
        self.assertEqual(list(gen), ["192.168.1.1"])
        self.assertEqual(total, 1)

    def test_hostname_returns_itself(self):
        gen, total = self._expand("example.com")
        self.assertEqual(list(gen), ["example.com"])
        self.assertEqual(total, 1)

    # ── small network ──────────────────────────────────────────────

    def test_slash_30_returns_2_hosts(self):
        gen, total = self._expand("192.168.1.0/30")
        hosts = list(gen)
        self.assertEqual(total, 2)
        self.assertEqual(len(hosts), 2)

    def test_slash_24_returns_254_hosts(self):
        gen, total = self._expand("192.168.1.0/24")
        self.assertEqual(total, 254)

    # ── limit enforcement ──────────────────────────────────────────

    def test_slash_20_within_default_limit(self):
        # /20 = 4094 hosts — exactly at MAX_SCAN_HOSTS limit
        gen, total = self._expand("10.0.0.0/20")
        self.assertEqual(total, 4094)

    def test_slash_19_exceeds_default_limit(self):
        # /19 = 8190 hosts > MAX_SCAN_HOSTS (4094)
        with self.assertRaises(ValueError) as ctx:
            self._expand("10.0.0.0/19")
        msg = str(ctx.exception)
        # Сообщение должно упоминать лимит (формат числа зависит от locale)
        self.assertTrue(
            "4,094" in msg or "4 094" in msg or "4094" in msg,
            f"Limit not mentioned in: {msg}"
        )

    def test_slash_16_allowed_with_allow_large(self):
        gen, total = self._expand("10.0.0.0/16", allow_large=True)
        self.assertEqual(total, 65534)

    def test_slash_15_exceeds_extended_limit(self):
        # /15 = 131070 > MAX_SCAN_HOSTS_EXTENDED (65534)
        with self.assertRaises(ValueError):
            self._expand("10.0.0.0/15", allow_large=True)

    def test_slash_0_rejected(self):
        with self.assertRaises(ValueError):
            self._expand("0.0.0.0/0")

    def test_slash_8_rejected(self):
        with self.assertRaises(ValueError):
            self._expand("10.0.0.0/8")

    def test_error_message_contains_host_count(self):
        with self.assertRaises(ValueError) as ctx:
            self._expand("10.0.0.0/8")
        # Должно содержать реальное кол-во хостов
        self.assertIn("16", str(ctx.exception))  # 16 777 214

    # ── generator is lazy ──────────────────────────────────────────

    def test_expand_returns_generator_not_list(self):
        import types
        gen, total = self._expand("192.168.1.0/24")
        self.assertIsInstance(gen, types.GeneratorType)


# ── ManagedProcess ────────────────────────────────────────────────────────────

class TestManagedProcess(unittest.TestCase):

    def _make_proc(self, returncode=0):
        """Create a ManagedProcess wrapping a mock Popen."""
        from quickip.infrastructure.system.process_runner import ManagedProcess
        mock_popen = MagicMock(spec=subprocess.Popen)
        mock_popen.returncode = returncode
        mock_popen.stdout = MagicMock()
        mock_popen.poll.return_value = None  # still running
        mock_popen.wait.return_value = returncode
        return ManagedProcess(mock_popen, "test_command"), mock_popen

    def test_stdout_delegates_to_popen(self):
        proc, mock_popen = self._make_proc()
        self.assertIs(proc.stdout, mock_popen.stdout)

    def test_returncode_delegates_to_popen(self):
        proc, mock_popen = self._make_proc(returncode=1)
        self.assertEqual(proc.returncode, 1)

    def test_wait_closes_stdout_then_waits(self):
        proc, mock_popen = self._make_proc()
        proc.wait()
        mock_popen.stdout.close.assert_called_once()
        mock_popen.wait.assert_called_once()

    def test_cancel_terminates_process(self):
        proc, mock_popen = self._make_proc()
        mock_popen.poll.return_value = None  # still running
        mock_popen.wait.return_value = 0
        proc.cancel(timeout=1.0)
        mock_popen.terminate.assert_called_once()
        mock_popen.wait.assert_called()

    def test_cancel_closes_stdout_first(self):
        proc, mock_popen = self._make_proc()
        proc.cancel(timeout=1.0)
        mock_popen.stdout.close.assert_called()

    def test_cancel_already_finished_is_noop(self):
        proc, mock_popen = self._make_proc()
        mock_popen.poll.return_value = 0  # already done
        proc.cancel()
        mock_popen.terminate.assert_not_called()

    def test_cancel_kills_after_timeout(self):
        from quickip.infrastructure.system.process_runner import ManagedProcess
        mock_popen = MagicMock(spec=subprocess.Popen)
        mock_popen.poll.return_value = None
        mock_popen.stdout = MagicMock()
        # terminate + first wait → TimeoutExpired; kill + second wait → ok
        mock_popen.wait.side_effect = [
            subprocess.TimeoutExpired("cmd", 1),  # after terminate
            0,                                      # after kill
        ]
        proc = ManagedProcess(mock_popen, "slow_cmd")
        proc.cancel(timeout=0.1)
        mock_popen.terminate.assert_called_once()
        mock_popen.kill.assert_called_once()

    def test_kill_delegates_to_cancel(self):
        """kill() backward-compat shim must call cancel()."""
        proc, mock_popen = self._make_proc()
        mock_popen.poll.return_value = None
        mock_popen.wait.return_value = 0
        proc.kill()
        mock_popen.terminate.assert_called_once()

    def test_popen_returns_managed_process(self):
        """ProcessRunner.popen() must return ManagedProcess, not raw Popen."""
        from quickip.infrastructure.system.process_runner import ProcessRunner, ManagedProcess
        runner = ProcessRunner()
        popen_spec = subprocess.Popen
        with patch("subprocess.Popen") as mock_popen_cls:
            mock_instance = MagicMock(spec=popen_spec)
            mock_instance.stdout = MagicMock()
            mock_popen_cls.return_value = mock_instance
            result = runner.popen(["echo", "test"])
        self.assertIsInstance(result, ManagedProcess)


# ── keyring_vault UUID scheme ─────────────────────────────────────────────────

class TestKeyringVaultUUID(unittest.TestCase):

    def _make_mock_keyring(self):
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = "secret123"
        return mock_kr

    def test_protect_stores_with_uuid_prefix(self):
        mock_kr = self._make_mock_keyring()
        with patch.dict(__import__("sys").modules, {"keyring": mock_kr}):
            from importlib import reload
            import quickip.core.security.keyring_vault as kv
            reload(kv)
            sentinel = kv.protect_text("test-uuid-1234", "mypassword")
        mock_kr.set_password.assert_called_once_with("NetConneXion", "wifi:test-uuid-1234", "mypassword")
        self.assertEqual(sentinel, "kr:test-uuid-1234")

    def test_unprotect_looks_up_by_uuid(self):
        mock_kr = self._make_mock_keyring()
        with patch.dict(__import__("sys").modules, {"keyring": mock_kr}):
            from importlib import reload
            import quickip.core.security.keyring_vault as kv
            reload(kv)
            result = kv.unprotect_text("test-uuid-5678")
        mock_kr.get_password.assert_called_once_with("NetConneXion", "wifi:test-uuid-5678")
        self.assertEqual(result, "secret123")

    def test_unprotect_raises_if_not_found(self):
        mock_kr = self._make_mock_keyring()
        mock_kr.get_password.return_value = None
        with patch.dict(__import__("sys").modules, {"keyring": mock_kr}):
            from importlib import reload
            import quickip.core.security.keyring_vault as kv
            reload(kv)
            with self.assertRaises(kv.KeyringSecretNotFoundError):
                kv.unprotect_text("missing-uuid")

    def test_delete_uses_uuid_prefix(self):
        mock_kr = self._make_mock_keyring()
        with patch.dict(__import__("sys").modules, {"keyring": mock_kr}):
            from importlib import reload
            import quickip.core.security.keyring_vault as kv
            reload(kv)
            kv.delete("some-uuid")
        mock_kr.delete_password.assert_called_once_with("NetConneXion", "wifi:some-uuid")



# ── WifiService scan_networks cache ───────────────────────────────────────────

class TestScanNetworksCache(unittest.TestCase):

    def _make_service(self):
        from quickip.features.wifi.service import WifiService
        container = MagicMock()
        container.process_runner = MagicMock()
        container.vault_available = False
        svc = WifiService(container)
        return svc

    def test_returns_cached_result_when_lock_held(self):
        from quickip.features.wifi.netsh_parser import WifiNetworkSnapshot
        svc = self._make_service()

        # Предзаполняем кеш
        cached = [WifiNetworkSnapshot(ssid="CachedNet", bssid="", signal_pct=80,
                                      auth="WPA2", cipher="AES", channel=6,
                                      freq_ghz=2.437, mbps=300, protocol="802.11n")]
        svc._last_scan_result = cached

        # Захватываем lock — имитируем активный скан
        svc._scan_lock.acquire()
        try:
            result = svc.scan_networks()
        finally:
            svc._scan_lock.release()

        # Должны вернуть кеш, а не []
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ssid, "CachedNet")

    def test_returns_empty_list_if_no_cache_yet(self):
        svc = self._make_service()
        # Кеш пустой, lock занят
        svc._scan_lock.acquire()
        try:
            result = svc.scan_networks()
        finally:
            svc._scan_lock.release()
        self.assertEqual(result, [])

    def test_successful_scan_updates_cache(self):
        svc = self._make_service()

        _NETSH_OUTPUT = (
            "SSID 1 : TestNet\n"
            "Authentication          : WPA2-Personal\n"
            "Encryption              : AES\n"
            " BSSID 1                : aa:bb:cc:dd:ee:ff\n"
            "      Signal             : 75%\n"
            "      Radio type         : 802.11n\n"
            "      Channel            : 6\n"
        )
        mock_result = MagicMock()
        mock_result.stdout = _NETSH_OUTPUT
        mock_result.success = True
        svc._runner.run.return_value = mock_result

        svc.scan_networks()
        self.assertEqual(len(svc._last_scan_result), 1)
        self.assertEqual(svc._last_scan_result[0].ssid, "TestNet")

    def test_returned_cache_is_copy_not_reference(self):
        from quickip.features.wifi.netsh_parser import WifiNetworkSnapshot
        svc = self._make_service()
        cached = [WifiNetworkSnapshot(ssid="Net", bssid="", signal_pct=50,
                                      auth="", cipher="", channel=1,
                                      freq_ghz=2.412, mbps=54, protocol="")]
        svc._last_scan_result = cached
        svc._scan_lock.acquire()
        try:
            result = svc.scan_networks()
        finally:
            svc._scan_lock.release()
        # Модификация возвращённого списка не должна менять кеш
        result.clear()
        self.assertEqual(len(svc._last_scan_result), 1)


# ── VaultPortabilityError → needs_reauth ─────────────────────────────────────

class TestNeedsReauthFlow(unittest.TestCase):
    """WifiService.connect() returns needs_reauth=True on VaultPortabilityError."""

    def _make_service(self, vault_available=True):
        from quickip.features.wifi.service import WifiService
        container = MagicMock()
        container.process_runner = MagicMock()
        container.vault_available = vault_available
        return WifiService(container)

    def _make_profile(self, key_protected="dpapi3:AAAA=="):
        from quickip.features.wifi.repository import WifiProfile
        return WifiProfile(
            id="test-uuid-001",
            ssid="TestNet",
            auth="WPA2-Personal",
            cipher="AES",
            key_protected=key_protected,
        )

    def test_needs_reauth_true_on_portability_error(self):
        """Direct test: mock vault inside service to raise VaultPortabilityError."""
        from quickip.features.wifi.service import WifiService, ConnectResult
        from quickip.core.security.vault import VaultPortabilityError

        container = MagicMock()
        container.process_runner = MagicMock()
        container.vault_available = True
        svc = WifiService(container)

        profile = self._make_profile("dpapi3:FAKEFAKE==")

        # Патчим unprotect_text в точке импорта внутри service.py
        with patch("quickip.core.security.vault.unprotect_text",
                   side_effect=VaultPortabilityError("cross-user")):
            result = svc.connect("TestNet", profile)

        self.assertTrue(result.needs_reauth)
        self.assertFalse(result.success)
        self.assertIn("другим аккаунтом", result.message)

    def test_successful_dpapi_decrypt_does_not_set_needs_reauth(self):
        """Normal DPAPI decrypt → needs_reauth stays False."""
        from quickip.features.wifi.service import WifiService
        from unittest.mock import patch

        container = MagicMock()
        container.process_runner = MagicMock()
        container.vault_available = True
        svc = WifiService(container)

        profile = self._make_profile("dpapi3:GOODBLOB==")

        # unprotect_text возвращает пароль, netsh — успех
        runner_result = MagicMock()
        runner_result.success = True
        runner_result.exit_code = 0
        runner_result.stdout = "Profile added"
        runner_result.stderr = ""
        svc._runner.run.return_value = runner_result

        with patch("quickip.core.security.vault.unprotect_text", return_value="s3cr3t"):
            result = svc.connect("TestNet", profile)

        self.assertFalse(result.needs_reauth)

    def test_connect_result_default_needs_reauth_false(self):
        """ConnectResult.needs_reauth defaults to False."""
        from quickip.features.wifi.service import ConnectResult
        r = ConnectResult(success=True, message="ok")
        self.assertFalse(r.needs_reauth)

    def test_reauth_connect_calls_connect_with_password(self):
        """WifiPresenter.reauth_connect() calls service.connect_with_password()."""
        from quickip.features.wifi.presenter import WifiPresenter
        from quickip.features.wifi.service import ConnectResult

        container = MagicMock()
        container.vault_available = True
        container.keyring_available = False
        container.event_bus = MagicMock()

        presenter = WifiPresenter(container)

        # Мокаем репозиторий и сервис
        mock_profile = self._make_profile()
        mock_profile.auto_connect = True
        mock_profile.connect_hidden = False
        mock_profile.is_adhoc = False
        presenter._profile_repo = MagicMock()
        presenter._profile_repo.find_by_ssid.return_value = mock_profile

        ok_result = ConnectResult(success=True, message="Connected")
        presenter._service = MagicMock()
        presenter._service.connect_with_password.return_value = ok_result

        with patch.object(presenter, "save_profile") as mock_save:
            result = presenter.reauth_connect("TestNet", "newpassword")

        # connect_with_password должен быть вызван с паролем
        presenter._service.connect_with_password.assert_called_once_with(
            "TestNet", "newpassword",
            auth="WPA2-Personal", cipher="AES",
        )
        # При успехе — save_profile сохраняет профиль под текущим аккаунтом
        mock_save.assert_called_once()
        self.assertTrue(result.success)

    def test_reauth_connect_no_resave_on_failure(self):
        """WifiPresenter.reauth_connect() does NOT re-save if connect failed."""
        from quickip.features.wifi.presenter import WifiPresenter
        from quickip.features.wifi.service import ConnectResult

        container = MagicMock()
        container.vault_available = True
        container.keyring_available = False
        container.event_bus = MagicMock()

        presenter = WifiPresenter(container)
        mock_profile = self._make_profile()
        mock_profile.auto_connect = True
        mock_profile.connect_hidden = False
        mock_profile.is_adhoc = False
        presenter._profile_repo = MagicMock()
        presenter._profile_repo.find_by_ssid.return_value = mock_profile

        fail_result = ConnectResult(success=False, message="Wrong password")
        presenter._service = MagicMock()
        presenter._service.connect_with_password.return_value = fail_result

        with patch.object(presenter, "save_profile") as mock_save:
            result = presenter.reauth_connect("TestNet", "wrongpw")

        mock_save.assert_not_called()
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
