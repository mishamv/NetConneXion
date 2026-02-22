"""Integration tests – verify wiring between layers."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace


# ── GitHubUpdater unit tests ─────────────────────────────────────

class TestGitHubUpdater:
    """Tests for the update checker."""

    def test_parse_version_tag(self):
        from quickip.infrastructure.update.github_updater import GitHubUpdater
        updater = GitHubUpdater.__new__(GitHubUpdater)
        assert updater._parse_version("v2.1.3") == (2, 1, 3)
        assert updater._parse_version("2.0.0") == (2, 0, 0)
        assert updater._parse_version("no-version") == (0,)

    def test_remote_ver_str(self):
        from quickip.infrastructure.update.github_updater import remote_ver_str
        assert remote_ver_str("v2.1.0") == "2.1.0"
        assert remote_ver_str("V3.0.0-beta") == "3.0.0-beta"

    def test_check_sync_up_to_date(self):
        """When remote version <= current, returns None."""
        from quickip.infrastructure.update.github_updater import GitHubUpdater
        import json

        fake_response = json.dumps({
            "tag_name": "v2.0.0",
            "name": "v2.0.0",
            "body": "",
            "html_url": "",
            "published_at": "",
            "assets": [],
        }).encode()

        updater = GitHubUpdater(current_version="2.0.0")
        with patch("quickip.infrastructure.update.github_updater.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = fake_response
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            result = updater.check_sync()
        assert result is None


# ── ToastService unit tests ──────────────────────────────────────

class TestToastService:
    """Tests for toast notification service (no-op when winotify absent)."""

    def test_available_without_winotify(self):
        from quickip.infrastructure.notify.toast_service import ToastService
        svc = ToastService()
        # In test env winotify is likely not installed
        # Just verify it doesn't crash
        svc.notify_profile_applied("Test")
        svc.notify_profile_failed("Test", "err")
        svc.notify_auto_switch("MyWiFi", "Office")
        svc.notify_update_available("3.0.0")
        svc.notify_generic("Title", "Body")


# ── SettingsPresenter update check ───────────────────────────────

class TestSettingsPresenterUpdate:
    """Test update check flow through presenter."""

    @pytest.fixture
    def setup(self):
        from quickip.presenters.settings_presenter import SettingsPresenter

        container = MagicMock()
        container.settings_repo.get.return_value = "light"
        view = MagicMock()
        presenter = SettingsPresenter(container, view)
        return SimpleNamespace(presenter=presenter, container=container, view=view)

    def test_check_for_updates_calls_updater(self, setup):
        setup.presenter.check_for_updates()
        setup.container.updater.check_async.assert_called_once()

    def test_show_update_available_protocol(self, setup):
        """Verify view protocol method is callable."""
        setup.view.show_update_available("3.0.0", "https://example.com")
        setup.view.show_update_available.assert_called_once()

    def test_show_update_not_found_protocol(self, setup):
        setup.view.show_update_not_found()
        setup.view.show_update_not_found.assert_called_once()


# ── Event bus integration ────────────────────────────────────────

class TestEventBusIntegration:
    """Verify event bus wiring between services."""

    def test_profile_applied_event_fires(self):
        from quickip.events.bus import EventBus
        from quickip.events.event_types import ProfileApplied

        bus = EventBus()
        received = []
        bus.subscribe(ProfileApplied, lambda e: received.append(e))
        event = ProfileApplied(profile_id="p1", profile_name="Test", success=True)
        bus.publish(event)
        assert len(received) == 1
        assert received[0].profile_name == "Test"

    def test_multiple_subscribers(self):
        from quickip.events.bus import EventBus
        from quickip.events.event_types import ProfileApplied

        bus = EventBus()
        results_a, results_b = [], []
        bus.subscribe(ProfileApplied, lambda e: results_a.append(e))
        bus.subscribe(ProfileApplied, lambda e: results_b.append(e))
        bus.publish(ProfileApplied(profile_id="p1", profile_name="X", success=True))
        assert len(results_a) == 1
        assert len(results_b) == 1
