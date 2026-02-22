"""Unit tests for domain models, repositories and services."""

import json
import tempfile
import uuid
from pathlib import Path

import pytest

from quickip.domain.models import (
    Profile, IPMode, DNSMode,
    ProfileHistoryEntry, AdapterConfig,
    NetworkFingerprint,
)
from quickip.events.bus import EventBus
from quickip.events.event_types import ProfileApplied, ProfileApplyFailed
from quickip.infrastructure.storage.json_profile_repo import JsonProfileRepository
from quickip.infrastructure.storage.json_history_repo import JsonHistoryRepository
from quickip.infrastructure.storage.json_settings_repo import JsonSettingsRepository
from quickip.domain.services.import_export_service import ImportExportService
from quickip.domain.services.diagnostics_service import ConflictCheckService


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_profiles(tmp_path):
    return JsonProfileRepository(tmp_path / "profiles.json")


@pytest.fixture
def tmp_history(tmp_path):
    return JsonHistoryRepository(tmp_path / "history.json")


@pytest.fixture
def tmp_settings(tmp_path):
    return JsonSettingsRepository(tmp_path / "settings.json")


@pytest.fixture
def bus():
    b = EventBus()
    yield b
    b.clear()


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


def _make_history_entry(**kw) -> ProfileHistoryEntry:
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


# ── Domain model tests ───────────────────────────────────────────────────────

class TestProfileModel:
    def test_dhcp_ip_true(self):
        p = _make_profile(ip_mode=IPMode.DHCP)
        assert p.is_dhcp_ip is True

    def test_dhcp_ip_false(self):
        p = _make_profile(ip_mode=IPMode.STATIC)
        assert p.is_dhcp_ip is False

    def test_dhcp_dns_true(self):
        p = _make_profile(dns_mode=DNSMode.DHCP)
        assert p.is_dhcp_dns is True

    def test_tags_default_empty(self):
        p = _make_profile()
        assert p.tags == []


class TestNetworkFingerprint:
    def test_primary_key_ssid(self):
        fp = NetworkFingerprint(ssid="MyWiFi")
        assert fp.primary_key == "MyWiFi"

    def test_primary_key_fallback_mac(self):
        fp = NetworkFingerprint(ssid="", gateway_mac="AA:BB:CC:DD:EE:FF")
        assert fp.primary_key == "AA:BB:CC:DD:EE:FF"

    def test_is_valid_true(self):
        assert NetworkFingerprint(ssid="X").is_valid is True

    def test_is_valid_false(self):
        assert NetworkFingerprint().is_valid is False


# ── Repository tests ─────────────────────────────────────────────────────────

class TestJsonProfileRepository:
    def test_save_and_get(self, tmp_profiles):
        p = _make_profile(name="Office")
        tmp_profiles.save(p)
        loaded = tmp_profiles.get(p.id)
        assert loaded is not None
        assert loaded.name == "Office"

    def test_list_returns_all(self, tmp_profiles):
        for n in ("A", "B", "C"):
            tmp_profiles.save(_make_profile(name=n))
        assert len(tmp_profiles.list()) == 3

    def test_delete(self, tmp_profiles):
        p = _make_profile(name="ToDelete")
        tmp_profiles.save(p)
        tmp_profiles.delete(p.id)
        assert tmp_profiles.get(p.id) is None

    def test_find_by_name(self, tmp_profiles):
        p = _make_profile(name="FindMe")
        tmp_profiles.save(p)
        found = tmp_profiles.find_by_name("FindMe")
        assert found is not None
        assert found.id == p.id

    def test_exists(self, tmp_profiles):
        p = _make_profile()
        tmp_profiles.save(p)
        assert tmp_profiles.exists(p.id) is True
        assert tmp_profiles.exists("nonexistent") is False

    def test_persistence_across_instances(self, tmp_path):
        path = tmp_path / "p.json"
        repo1 = JsonProfileRepository(path)
        p = _make_profile(name="Persistent")
        repo1.save(p)

        repo2 = JsonProfileRepository(path)
        assert repo2.find_by_name("Persistent") is not None

    def test_legacy_format_no_id(self, tmp_path):
        """Profiles without 'id' field should get auto-generated UUID."""
        path = tmp_path / "legacy.json"
        legacy = [{"name": "LegacyProfile", "adapter": "Wi-Fi",
                   "dhcp_ip": True, "dhcp_dns": True}]
        path.write_text(json.dumps(legacy), encoding="utf-8")

        repo = JsonProfileRepository(path)
        profiles = repo.list()
        assert len(profiles) == 1
        assert profiles[0].name == "LegacyProfile"
        assert profiles[0].id  # should have generated an ID


class TestJsonHistoryRepository:
    def test_append_and_list(self, tmp_history):
        e = _make_history_entry()
        tmp_history.append(e)
        entries = tmp_history.list()
        assert len(entries) == 1
        assert entries[0].id == e.id

    def test_stats_basic(self, tmp_history):
        tmp_history.append(_make_history_entry(success=True, duration_ms=100))
        tmp_history.append(_make_history_entry(success=True, duration_ms=200))
        tmp_history.append(_make_history_entry(success=False, duration_ms=50))
        stats = tmp_history.stats()
        assert stats.total_applies == 3
        assert stats.successful_applies == 2
        assert stats.failed_applies == 1
        assert stats.avg_duration_ms == pytest.approx(116.67, abs=1)

    def test_clear(self, tmp_history):
        tmp_history.append(_make_history_entry())
        tmp_history.clear()
        assert tmp_history.list() == []

    def test_filter_by_success(self, tmp_history):
        tmp_history.append(_make_history_entry(success=True))
        tmp_history.append(_make_history_entry(success=False))
        ok = tmp_history.list(success_only=True)
        assert all(e.success for e in ok)


class TestJsonSettingsRepository:
    def test_defaults(self, tmp_settings):
        assert isinstance(tmp_settings.get_bool("dark_mode"), bool)

    def test_set_and_get(self, tmp_settings):
        tmp_settings.set("dark_mode", True)
        assert tmp_settings.get_bool("dark_mode") is True

    def test_persistence(self, tmp_path):
        path = tmp_path / "s.json"
        r1 = JsonSettingsRepository(path)
        r1.set("dark_mode", True)
        r1.save()

        r2 = JsonSettingsRepository(path)
        assert r2.get_bool("dark_mode") is True


# ── Event bus tests ───────────────────────────────────────────────────────────

class TestEventBus:
    def test_subscribe_and_publish(self, bus):
        received = []
        bus.subscribe(ProfileApplied, received.append)
        evt = ProfileApplied(
            profile_id="1", profile_name="X",
            adapter="eth0", result=None
        )
        bus.publish(evt)
        assert len(received) == 1
        assert received[0] is evt

    def test_unsubscribe(self, bus):
        received = []
        sub = bus.subscribe(ProfileApplied, received.append)
        sub.unsubscribe()
        bus.publish(ProfileApplied(
            profile_id="1", profile_name="X",
            adapter="eth0", result=None
        ))
        assert received == []

    def test_handler_error_does_not_crash_bus(self, bus):
        def bad_handler(_): raise RuntimeError("boom")
        bus.subscribe(ProfileApplied, bad_handler)
        bus.publish(ProfileApplied(
            profile_id="1", profile_name="X",
            adapter="eth0", result=None
        ))  # should not raise


# ── ImportExportService tests ─────────────────────────────────────────────────

class TestImportExportService:
    def _make_svc(self, repo):
        b = EventBus()
        return ImportExportService(repo, b)

    def test_export_and_reimport(self, tmp_profiles, tmp_path):
        svc = self._make_svc(tmp_profiles)
        p = _make_profile(name="ExportMe")
        tmp_profiles.save(p)

        out = str(tmp_path / "export.json")
        svc.export_profiles(out)

        assert Path(out).exists()
        payload = json.loads(Path(out).read_text())
        assert payload["schema_version"] == 1
        assert len(payload["profiles"]) == 1

        # Re-import into fresh repo
        repo2 = JsonProfileRepository(tmp_path / "profiles2.json")
        svc2 = self._make_svc(repo2)
        report = svc2.import_profiles(out)
        assert report.successful == 1

    def test_import_rename_conflict(self, tmp_profiles, tmp_path):
        svc = self._make_svc(tmp_profiles)
        p = _make_profile(name="Conflict")
        tmp_profiles.save(p)

        export_data = {
            "schema_version": 1, "app": "quick-ip-change",
            "exported_at": "2025-01-01T00:00:00",
            "profiles": [{"id": str(uuid.uuid4()), "name": "Conflict",
                           "adapter": "Ethernet", "dhcp_ip": True, "dhcp_dns": True}]
        }
        src = tmp_path / "conflict.json"
        src.write_text(json.dumps(export_data), encoding="utf-8")

        report = svc.import_profiles(str(src), strategy="rename")
        assert report.successful == 1
        # Both original and renamed should exist
        assert len(tmp_profiles.list()) == 2

    def test_import_skip_conflict(self, tmp_profiles, tmp_path):
        svc = self._make_svc(tmp_profiles)
        p = _make_profile(name="Skip")
        tmp_profiles.save(p)

        export_data = {
            "schema_version": 1, "app": "quick-ip-change",
            "exported_at": "2025-01-01T00:00:00",
            "profiles": [{"id": str(uuid.uuid4()), "name": "Skip",
                           "adapter": "Ethernet", "dhcp_ip": True, "dhcp_dns": True}]
        }
        src = tmp_path / "skip.json"
        src.write_text(json.dumps(export_data), encoding="utf-8")

        report = svc.import_profiles(str(src), strategy="skip")
        assert report.skipped == 1
        assert len(tmp_profiles.list()) == 1   # still only the original
