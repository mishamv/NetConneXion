"""Unit tests for presenters with mocked views and services."""

import uuid
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from quickip.domain.models import (
    Profile, IPMode, DNSMode, ProfileHistoryEntry, HistoryStats,
)
from quickip.events.bus import EventBus
from quickip.infrastructure.storage.json_profile_repo import JsonProfileRepository
from quickip.infrastructure.storage.json_history_repo import JsonHistoryRepository
from quickip.infrastructure.storage.json_settings_repo import JsonSettingsRepository
from quickip.infrastructure.storage.json_network_mapping_repo import JsonNetworkMappingRepository

from quickip.presenters.profiles_presenter import ProfilesPresenter
from quickip.presenters.history_presenter import HistoryPresenter
from quickip.presenters.tools_presenter import ToolsPresenter
from quickip.presenters.settings_presenter import SettingsPresenter


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_profile(**kw) -> Profile:
    defaults = dict(
        id=str(uuid.uuid4()),
        name="Test",
        adapter="Ethernet",
        ip_mode=IPMode.DHCP,
        dns_mode=DNSMode.DHCP,
    )
    defaults.update(kw)
    return Profile(**defaults)


def _make_entry(**kw) -> ProfileHistoryEntry:
    defaults = dict(
        id=str(uuid.uuid4()),
        timestamp="2025-01-01T12:00:00",
        profile_id="pid",
        profile_name="Test",
        adapter="Ethernet",
        success=True,
        duration_ms=150,
    )
    defaults.update(kw)
    return ProfileHistoryEntry(**defaults)


def _make_container(tmp_path):
    """Build a lightweight ServiceContainer mock with real repos."""
    bus = EventBus()
    container = MagicMock()
    container.event_bus = bus
    container.profile_repo = JsonProfileRepository(tmp_path / "profiles.json")
    container.history_repo = JsonHistoryRepository(tmp_path / "history.json")
    container.settings_repo = JsonSettingsRepository(tmp_path / "settings.json")
    container.mapping_repo = JsonNetworkMappingRepository(tmp_path / "mappings.json")
    container.netsh.list_adapters.return_value = ["Ethernet", "Wi-Fi"]
    container.netsh.get_network_snapshot.return_value = "Adapter: Ethernet\nIP: 192.168.1.10"
    container.diagnostics.ping.return_value = MagicMock(stdout="Reply from 8.8.8.8")
    container.diagnostics.dns_check.return_value = MagicMock(stdout="Name: google.com")
    container.diagnostics.netstat.return_value = MagicMock(stdout="Active Connections")
    container.diagnostics.flush_dns.return_value = MagicMock(stdout="Flushed")
    container.diagnostics.tcp_reset.return_value = MagicMock(stdout="Reset OK")
    container.import_export = MagicMock()
    container.profile_apply = MagicMock()
    return container


# ── ProfilesPresenter ────────────────────────────────────────────────────────

class TestProfilesPresenter:
    @pytest.fixture
    def setup(self, tmp_path):
        container = _make_container(tmp_path)
        view = MagicMock()
        view.get_search_query.return_value = ""
        view.get_adapter_filter.return_value = "Все адаптеры"
        presenter = ProfilesPresenter(container, view)
        return presenter, view, container

    def test_load_initial_empty(self, setup):
        presenter, view, _ = setup
        presenter.load_initial()
        view.show_profiles_list.assert_called_once()
        names, selected = view.show_profiles_list.call_args[0]
        assert names == []
        assert selected is None

    def test_load_initial_with_profiles(self, setup):
        presenter, view, container = setup
        p = _make_profile(name="Office")
        container.profile_repo.save(p)
        presenter.load_initial()
        names, selected = view.show_profiles_list.call_args[0]
        assert "Office" in names

    def test_create_profile(self, setup):
        presenter, view, container = setup
        presenter.load_initial()
        presenter.create_profile()
        profiles = container.profile_repo.list()
        assert len(profiles) == 1
        assert profiles[0].name.startswith("Новый профиль")

    def test_delete_profile(self, setup):
        presenter, view, container = setup
        p = _make_profile(name="ToDelete")
        container.profile_repo.save(p)
        presenter.load_initial()
        view.ask_yes_no.return_value = True
        presenter.delete_profile("ToDelete")
        assert container.profile_repo.find_by_name("ToDelete") is None

    def test_duplicate_profile(self, setup):
        presenter, view, container = setup
        p = _make_profile(name="Original")
        container.profile_repo.save(p)
        presenter.load_initial()
        presenter.duplicate_profile("Original")
        profiles = container.profile_repo.list()
        assert len(profiles) == 2
        names = [pr.name for pr in profiles]
        assert "Original" in names
        assert any("копия" in n.lower() or "original" in n.lower() for n in names if n != "Original")

    def test_get_adapters(self, setup):
        presenter, _, _ = setup
        presenter.load_initial()
        assert presenter.get_adapters() == ["Ethernet", "Wi-Fi"]

    def test_save_profile_static(self, setup):
        presenter, view, container = setup
        p = _make_profile(name="Static")
        container.profile_repo.save(p)
        presenter.load_initial()
        presenter.on_select("Static")

        form = {
            "name": "Static",
            "adapter": "Ethernet",
            "ip_mode": "static",
            "dns_mode": "static",
            "ip": "192.168.1.100",
            "mask": "255.255.255.0",
            "gateway": "192.168.1.1",
            "dns1": "8.8.8.8",
            "dns2": "8.8.4.4",
        }
        presenter.save_profile(form)
        saved = container.profile_repo.find_by_name("Static")
        assert saved is not None
        assert saved.ip_mode == IPMode.STATIC

    def test_get_profiles_dict(self, setup):
        presenter, _, container = setup
        p = _make_profile(name="A")
        container.profile_repo.save(p)
        presenter.load_initial()
        d = presenter.get_profiles()
        assert "A" in d

    def test_refresh_list_with_search(self, setup):
        presenter, view, container = setup
        container.profile_repo.save(_make_profile(name="Office"))
        container.profile_repo.save(_make_profile(name="Home"))
        presenter.load_initial()
        view.get_search_query.return_value = "off"
        presenter.refresh_list()
        names, _ = view.show_profiles_list.call_args[0]
        assert "Office" in names
        assert "Home" not in names


# ── HistoryPresenter ─────────────────────────────────────────────────────────

class TestHistoryPresenter:
    @pytest.fixture
    def setup(self, tmp_path):
        container = _make_container(tmp_path)
        view = MagicMock()
        view.get_history_search.return_value = ""
        view.get_history_status_filter.return_value = "Все"
        presenter = HistoryPresenter(container, view)
        return presenter, view, container

    def test_refresh_empty(self, setup):
        presenter, view, _ = setup
        presenter.refresh()
        view.show_history_entries.assert_called_once()
        lines = view.show_history_entries.call_args[0][0]
        assert any("пуста" in l for l in lines)

    def test_refresh_with_entries(self, setup):
        presenter, view, container = setup
        container.history_repo.append(_make_entry(profile_name="Office", success=True))
        container.history_repo.append(_make_entry(profile_name="Home", success=False))
        presenter.refresh()
        lines = view.show_history_entries.call_args[0][0]
        assert len(lines) >= 2

    def test_filter_success_only(self, setup):
        presenter, view, container = setup
        container.history_repo.append(_make_entry(profile_name="A", success=True))
        container.history_repo.append(_make_entry(profile_name="B", success=False))
        view.get_history_status_filter.return_value = "Успешные"
        presenter.refresh()
        lines = view.show_history_entries.call_args[0][0]
        assert all("FAIL" not in l for l in lines)

    def test_filter_errors_only(self, setup):
        presenter, view, container = setup
        container.history_repo.append(_make_entry(profile_name="A", success=True))
        container.history_repo.append(_make_entry(profile_name="B", success=False, error_message="timeout"))
        view.get_history_status_filter.return_value = "Ошибки"
        presenter.refresh()
        lines = view.show_history_entries.call_args[0][0]
        assert all("OK" not in l.split("]")[0] for l in lines if "]" in l)

    def test_stats_display(self, setup):
        presenter, view, container = setup
        container.history_repo.append(_make_entry(success=True, duration_ms=100))
        container.history_repo.append(_make_entry(success=True, duration_ms=200))
        container.history_repo.append(_make_entry(success=False, duration_ms=50))
        presenter.refresh()
        stats_text = view.show_history_stats.call_args[0][0]
        assert "3" in stats_text  # total
        assert "2" in stats_text  # OK
        assert "1" in stats_text  # FAIL

    def test_compute_stats_static(self):
        entries = [
            _make_entry(success=True, duration_ms=100),
            _make_entry(success=False, duration_ms=200),
        ]
        stats = HistoryPresenter._compute_stats(entries)
        assert stats.total_applies == 2
        assert stats.successful_applies == 1
        assert stats.failed_applies == 1
        assert stats.avg_duration_ms == 150.0

    def test_search_filter(self, setup):
        presenter, view, container = setup
        container.history_repo.append(_make_entry(profile_name="Office"))
        container.history_repo.append(_make_entry(profile_name="Home"))
        view.get_history_search.return_value = "off"
        presenter.refresh()
        lines = view.show_history_entries.call_args[0][0]
        assert any("Office" in l for l in lines)
        assert not any("Home" in l for l in lines)


# ── ToolsPresenter ───────────────────────────────────────────────────────────

class TestToolsPresenter:
    @pytest.fixture
    def setup(self, tmp_path):
        container = _make_container(tmp_path)
        view = MagicMock()
        view.get_tool_target.return_value = ""
        presenter = ToolsPresenter(container, view)
        return presenter, view, container

    def test_ping(self, setup):
        presenter, view, container = setup
        view.get_tool_target.return_value = "8.8.8.8"
        presenter.run_tool("ping")
        view.show_tool_output.assert_called_once_with("Reply from 8.8.8.8")

    def test_dns(self, setup):
        presenter, view, _ = setup
        view.get_tool_target.return_value = "google.com"
        presenter.run_tool("dns")
        view.show_tool_output.assert_called_once_with("Name: google.com")

    def test_netstat(self, setup):
        presenter, view, _ = setup
        presenter.run_tool("netstat")
        view.show_tool_output.assert_called_once_with("Active Connections")

    def test_flushdns_confirmed(self, setup):
        presenter, view, _ = setup
        view.ask_yes_no.return_value = True
        presenter.run_tool("flushdns")
        view.show_tool_output.assert_called_once_with("Flushed")

    def test_flushdns_cancelled(self, setup):
        presenter, view, _ = setup
        view.ask_yes_no.return_value = False
        presenter.run_tool("flushdns")
        view.show_tool_output.assert_not_called()

    def test_tcpreset_confirmed(self, setup):
        presenter, view, _ = setup
        view.ask_yes_no.return_value = True
        presenter.run_tool("tcpreset")
        view.show_tool_output.assert_called_once_with("Reset OK")

    def test_unknown_tool(self, setup):
        presenter, view, _ = setup
        presenter.run_tool("unknown")
        view.show_tool_output.assert_called_once_with("Неизвестный инструмент.")

    def test_tool_exception(self, setup):
        presenter, view, container = setup
        container.diagnostics.ping.side_effect = RuntimeError("network down")
        view.get_tool_target.return_value = "8.8.8.8"
        presenter.run_tool("ping")
        output = view.show_tool_output.call_args[0][0]
        assert "Ошибка" in output


# ── SettingsPresenter ────────────────────────────────────────────────────────

class TestSettingsPresenter:
    @pytest.fixture
    def setup(self, tmp_path):
        container = _make_container(tmp_path)
        view = MagicMock()
        presenter = SettingsPresenter(container, view)
        return presenter, view, container

    def test_get_current_theme_default(self, setup):
        presenter, _, _ = setup
        assert presenter.get_current_theme() in ("light", "dark")

    def test_toggle_theme(self, setup):
        presenter, view, container = setup
        container.settings_repo.set("ui_theme", "light")
        presenter.toggle_theme()
        view.apply_theme.assert_called_once_with("dark")

    def test_set_theme_persists(self, setup):
        presenter, view, container = setup
        presenter.set_theme("dark")
        assert container.settings_repo.get("ui_theme") == "dark"
        view.apply_theme.assert_called_once_with("dark")

    def test_refresh_home_snapshot(self, setup):
        presenter, view, _ = setup
        presenter.refresh_home_snapshot()
        view.show_home_snapshot.assert_called_once()
        view.show_network_info.assert_called_once()

    def test_format_snapshot_empty(self):
        result = SettingsPresenter._format_snapshot("")
        assert "Нет данных" in result

    def test_format_snapshot_content(self):
        result = SettingsPresenter._format_snapshot("Adapter: Ethernet\nIP: 10.0.0.1\n\nAdapter: Wi-Fi\nIP: 192.168.1.5")
        assert "ТЕКУЩАЯ СЕТЬ" in result
        assert "Ethernet" in result

    def test_get_set_setting(self, setup):
        presenter, _, _ = setup
        presenter.set_setting("auto_apply", True)
        assert presenter.get_setting("auto_apply") is True
