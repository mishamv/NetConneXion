"""Auto-switch presenter – Wi-Fi SSID mapping and auto-apply logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol

from quickip.domain.models import Profile

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)


# ── View contract ────────────────────────────────────────────────

class AutoSwitchView(Protocol):
    """Callback interface for the Wi-Fi / auto-switch UI panel."""

    def show_current_ssid(self, text: str) -> None:
        """Update the 'current SSID' label."""
        ...

    def show_auto_status(self, text: str) -> None:
        """Update the auto-apply status label."""
        ...

    def show_visible_networks(self, names: List[str]) -> None:
        """Populate the visible Wi-Fi list."""
        ...

    def show_mappings(self, lines: List[str]) -> None:
        """Populate the SSID→profile mappings list."""
        ...

    def get_ssid_input(self) -> str:
        """Return SSID from the input field."""
        ...

    def get_profile_combo(self) -> str:
        """Return selected profile name from the combo."""
        ...

    def get_alias_input(self) -> str:
        """Return alias/name from the input field."""
        ...

    def get_username_input(self) -> str:
        """Return username from the input field."""
        ...

    def is_auto_enabled(self) -> bool:
        """Return whether auto-apply checkbox is on."""
        ...

    def is_mapping_auto(self) -> bool:
        """Return whether the 'auto' checkbox for new mapping is on."""
        ...

    def get_selected_mapping_index(self) -> Optional[int]:
        """Return selected index in mappings list, or None."""
        ...

    def show_message(self, title: str, message: str) -> None:
        ...

    def ask_yes_no(self, title: str, message: str) -> bool:
        ...

    def refresh_related_panels(self) -> None:
        """Trigger refresh of home snapshot, history, profiles, etc."""
        ...

    def schedule_next_tick(self, interval_ms: int) -> None:
        """Schedule the next auto-switch tick via Tk after()."""
        ...


# ── Presenter ────────────────────────────────────────────────────

class AutoSwitchPresenter:
    """
    Manages Wi-Fi SSID→profile mappings and periodic auto-apply.

    The presenter does NOT touch Tkinter directly; it calls back
    through :class:`AutoSwitchView`.
    """

    def __init__(
        self,
        container: "ServiceContainer",
        view: AutoSwitchView,
        get_profiles: callable,
    ) -> None:
        self.container = container
        self.view = view
        self._get_profiles = get_profiles  # callable returning dict[str, Profile]
        self._last_seen_ssid: Optional[str] = None
        self._last_auto_applied_ssid: Optional[str] = None
        self._polling_active: bool = True

    # ── Settings ─────────────────────────────────────────────────

    def toggle_auto_apply(self, enabled: bool) -> None:
        """Persist the auto-apply toggle."""
        self.container.settings_repo.set("wifi_auto_apply", enabled)
        self.container.settings_repo.save()
        state = "включено" if enabled else "выключено"
        self.view.show_auto_status(f"Автоприменение: {state}")

    # ── Visible networks ─────────────────────────────────────────

    def refresh_visible_networks(self) -> None:
        try:
            networks = self.container.network_probe.list_visible_wifi()
        except Exception:
            networks = []

        if not networks:
            self.view.show_visible_networks(["(Сети не найдены)"])
        else:
            self.view.show_visible_networks(networks)

    def refresh_current_ssid(self) -> None:
        try:
            ssid = self.container.network_probe.get_current_ssid()
        except Exception:
            ssid = None
        self.view.show_current_ssid(f"Текущий SSID: {ssid or '-'}")

    # ── Mappings CRUD ────────────────────────────────────────────

    def refresh_mappings(self) -> None:
        """Load mappings from settings and push formatted list to view."""
        mappings = self._get_mappings()
        lines: List[str] = []
        for idx, item in enumerate(mappings, start=1):
            ssid = str(item.get("ssid", "")).strip()
            profile = str(item.get("profile", "")).strip()
            alias = str(item.get("name", "")).strip()
            username = str(item.get("username", "")).strip()
            details = []
            if alias:
                details.append(f"name={alias}")
            if username:
                details.append(f"user={username}")
            if item.get("auto", True):
                details.append("auto")
            tail = f" ({', '.join(details)})" if details else ""
            lines.append(f"{idx:02d}. {ssid}  →  {profile}{tail}")
        self.view.show_mappings(lines)

    def add_mapping(self) -> None:
        ssid = self.view.get_ssid_input().strip()
        profile = self.view.get_profile_combo().strip()
        alias = self.view.get_alias_input().strip()
        username = self.view.get_username_input().strip()
        auto = self.view.is_mapping_auto()

        if not ssid or not profile:
            self.view.show_message("Ошибка", "Укажите SSID и профиль.")
            return

        mappings = self._get_mappings()
        mappings.append({
            "ssid": ssid,
            "profile": profile,
            "name": alias,
            "username": username,
            "auto": auto,
        })
        self._save_mappings(mappings)
        self.refresh_mappings()
        self.refresh_current_ssid()

    def remove_mapping(self) -> None:
        index = self.view.get_selected_mapping_index()
        if index is None:
            return
        mappings = self._get_mappings()
        if 0 <= index < len(mappings):
            mappings.pop(index)
        self._save_mappings(mappings)
        self.refresh_mappings()
        self.refresh_current_ssid()

    def apply_selected_mapping(self) -> None:
        """Apply the profile linked to the selected mapping (or current SSID)."""
        try:
            mapping = None
            index = self.view.get_selected_mapping_index()
            mappings = self._get_mappings()

            if index is not None and 0 <= index < len(mappings):
                mapping = mappings[index]

            if mapping is None:
                ssid = self.container.network_probe.get_current_ssid()
                self.view.show_current_ssid(f"Текущий SSID: {ssid or '-'}")
                if not ssid:
                    raise ValueError("Выберите привязку из списка или подключитесь к Wi‑Fi сети.")
                profile_name = self._resolve_for_ssid(ssid)
                if not profile_name:
                    raise ValueError(f"Для SSID '{ssid}' не найдена привязка.")
                mapping = {"ssid": ssid, "profile": profile_name}

            profile_name = str(mapping.get("profile", "")).strip()
            ssid_label = str(mapping.get("ssid", "")).strip()
            profiles = self._get_profiles()
            profile = profiles.get(profile_name)
            if not profile:
                raise ValueError(f"Профиль '{profile_name}' не найден.")

            # Apply
            self.container.profile_apply.apply(profile.id)
            self.view.refresh_related_panels()
            self.view.show_message(
                "Готово",
                f"Для SSID '{ssid_label}' применен профиль '{profile_name}'.",
            )
        except Exception as exc:
            self.view.show_message("Ошибка", str(exc))

    # ── Auto-switch tick ─────────────────────────────────────────

    def stop_polling(self) -> None:
        """Stop the auto-switch polling loop."""
        self._polling_active = False

    def start_polling(self) -> None:
        """Kick off the first tick; view will schedule subsequent ones."""
        interval = int(self.container.settings_repo.get("wifi_auto_interval_sec", 5) or 5)
        if self._polling_active:
            self.view.schedule_next_tick(max(2000, interval * 1000))

    def tick(self) -> None:
        """Called periodically by the Tk after() loop."""
        try:
            ssid = self.container.network_probe.get_current_ssid()
            if ssid != self._last_seen_ssid:
                self._last_seen_ssid = ssid
                self.view.show_current_ssid(f"Текущий SSID: {ssid or '-'}")

            if self.view.is_auto_enabled() and ssid:
                profile_name = self._resolve_for_ssid(ssid)
                profiles = self._get_profiles()
                if (
                    profile_name
                    and profile_name in profiles
                    and self._last_auto_applied_ssid != ssid
                ):
                    profile = profiles[profile_name]
                    self.container.profile_apply.apply(profile.id)
                    self._last_auto_applied_ssid = ssid
                    self.view.show_auto_status(
                        f"Автоприменение: SSID '{ssid}' → '{profile_name}'"
                    )
                    self.view.refresh_related_panels()
                    # Toast notification
                    if hasattr(self.container, 'toast'):
                        self.container.toast.notify_auto_switch(ssid, profile_name)
        except Exception as exc:
            self.view.show_auto_status(f"Автоприменение: ошибка ({exc})")
        finally:
            if self._polling_active:
                self.start_polling()

    # ── Internals ────────────────────────────────────────────────

    def _get_mappings(self) -> list:
        return self.container.settings_repo.get("wifi_mappings", [])

    def _save_mappings(self, mappings: list) -> None:
        self.container.settings_repo.set("wifi_mappings", mappings)
        self.container.settings_repo.save()

    def _resolve_for_ssid(self, ssid: str) -> Optional[str]:
        """Find profile name for a given SSID from settings mappings."""
        mappings = self._get_mappings()
        ssid_lower = ssid.lower()
        for m in mappings:
            if str(m.get("ssid", "")).strip().lower() == ssid_lower:
                if m.get("auto", True):
                    return str(m.get("profile", "")).strip() or None
        return None
