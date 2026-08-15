"""Contracts for profile JSON import and export."""

from __future__ import annotations

import json

import pytest

from quickip.features.profiles.import_export import ImportExportService


class FakeRepository:
    def __init__(self) -> None:
        self.profiles = []

    def list(self):
        return list(self.profiles)

    def find_by_name(self, name):
        return next((profile for profile in self.profiles if profile.name == name), None)

    def save(self, profile):
        existing = next((p for p in self.profiles if p.id == profile.id), None)
        if existing:
            self.profiles.remove(existing)
        self.profiles.append(profile)


class FakeEventBus:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event) -> None:
        self.events.append(event)


def profile_data(**overrides):
    data = {
        "id": "profile-1",
        "name": "Office",
        "adapter": "Ethernet",
        "dhcp_ip": False,
        "ip": "192.168.50.10",
        "mask": "255.255.255.0",
        "gateway": "192.168.50.1",
        "dhcp_dns": False,
        "dns_primary": "1.1.1.1",
        "dns_secondary": "8.8.8.8",
        "tags": ["work"],
    }
    data.update(overrides)
    return data


def write_payload(tmp_path, payload):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def make_service():
    repo = FakeRepository()
    bus = FakeEventBus()
    return ImportExportService(repo, bus), repo, bus


def test_imports_current_schema_and_publishes_event(tmp_path) -> None:
    service, repo, bus = make_service()
    path = write_payload(tmp_path, {"schema_version": 1, "profiles": [profile_data()]})

    report = service.import_profiles(str(path))

    assert report.successful == 1
    assert repo.profiles[0].name == "Office"
    assert len(bus.events) == 1
    assert bus.events[0].profile_ids == ["profile-1"]


@pytest.mark.parametrize("version", [None, 0, 2, "1"])
def test_rejects_missing_or_unsupported_schema_version(tmp_path, version) -> None:
    service, _, _ = make_service()
    payload = {"profiles": [profile_data()]}
    if version is not None:
        payload["schema_version"] = version
    path = write_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="schema version"):
        service.import_profiles(str(path))


def test_supports_legacy_list_export(tmp_path) -> None:
    service, repo, _ = make_service()
    path = write_payload(tmp_path, [profile_data()])

    report = service.import_profiles(str(path))

    assert report.successful == 1
    assert len(repo.profiles) == 1


@pytest.mark.parametrize("strategy", ["", "merge", "overwrite"])
def test_rejects_unknown_conflict_strategy(tmp_path, strategy) -> None:
    service, _, _ = make_service()
    path = write_payload(tmp_path, {"schema_version": 1, "profiles": []})

    with pytest.raises(ValueError, match="Unknown import strategy"):
        service.import_profiles(str(path), strategy=strategy)


@pytest.mark.parametrize(
    "invalid_profile",
    [
        profile_data(name=""),
        profile_data(name="Bad\nName"),
        profile_data(adapter=""),
        profile_data(adapter="Ethernet & calc.exe"),
        profile_data(ip="999.1.1.1"),
        profile_data(tags="not-a-list"),
        profile_data(tags=["valid", 42]),
    ],
)
def test_skips_invalid_external_profiles(tmp_path, invalid_profile) -> None:
    service, repo, bus = make_service()
    path = write_payload(
        tmp_path,
        {"schema_version": 1, "profiles": [invalid_profile, profile_data(id="valid-2")]},
    )

    report = service.import_profiles(str(path))

    assert report.successful == 1
    assert [profile.id for profile in repo.profiles] == ["valid-2"]
    assert len(bus.events) == 1


def test_rejects_non_list_profiles_collection(tmp_path) -> None:
    service, _, _ = make_service()
    path = write_payload(tmp_path, {"schema_version": 1, "profiles": {}})

    with pytest.raises(ValueError, match="profiles.*list"):
        service.import_profiles(str(path))
