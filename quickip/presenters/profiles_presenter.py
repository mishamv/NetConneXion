"""Profiles presenter – CRUD, apply, import/export, validation."""

from __future__ import annotations

import ipaddress
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Protocol

from quickip.domain.models import Profile, IPMode, DNSMode, ApplyResult
from quickip.events.event_types import ProfileApplied, ProfileApplyFailed

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)


# ── View contract ────────────────────────────────────────────────

class ProfilesView(Protocol):
    """Callback interface that the UI layer must implement."""

    def show_profiles_list(self, names: List[str], selected: Optional[str]) -> None:
        """Refresh the profile listbox with *names*; highlight *selected*."""
        ...

    def load_profile_form(self, profile: Profile) -> None:
        """Populate form fields from *profile*."""
        ...

    def show_message(self, title: str, message: str) -> None:
        ...

    def ask_yes_no(self, title: str, message: str) -> bool:
        ...

    def ask_rename_action(self, old_name: str, new_name: str) -> str:
        """Return 'rename' | 'save_as_new' | 'cancel'."""
        ...

    def get_adapter_filter(self) -> str:
        """Return current adapter filter value (e.g. 'Все адаптеры')."""
        ...

    def get_search_query(self) -> str:
        """Return current search text."""
        ...

    def update_adapter_filter_values(self, values: List[str]) -> None:
        """Update the adapter filter dropdown options."""
        ...

    def update_wifi_profile_combo(self, names: List[str]) -> None:
        """Sync the Wi-Fi mapping profile combo with current profile names."""
        ...

    def refresh_related_panels(self) -> None:
        """Trigger refresh of home snapshot, history, wifi mappings, etc."""
        ...


# ── Presenter ────────────────────────────────────────────────────

class ProfilesPresenter:
    """
    Orchestrates profile CRUD, apply, import/export.

    Owns no widgets – communicates with the UI exclusively through
    the :class:`ProfilesView` protocol.
    """

    def __init__(self, container: "ServiceContainer", view: ProfilesView) -> None:
        self.container = container
        self.view = view
        self._profiles: dict[str, Profile] = {}
        self._current_key: Optional[str] = None
        self._adapters: List[str] = []

    # ── Bootstrap ────────────────────────────────────────────────

    def load_initial(self) -> None:
        """Load profiles from repo and populate the view."""
        self._sync_profiles_from_repo()
        self._adapters = self._fetch_adapters()
        first_key = next(iter(self._profiles), None)
        self.refresh_list(select=first_key)

    # ── Adapter helpers ──────────────────────────────────────────

    def get_adapters(self) -> List[str]:
        return list(self._adapters)

    def refresh_adapters(self) -> List[str]:
        self._adapters = self._fetch_adapters()
        return list(self._adapters)

    def _fetch_adapters(self) -> List[str]:
        try:
            return self.container.netsh.list_adapters()
        except Exception:
            return ["Ethernet", "Wi-Fi"]

    # ── Profile list ─────────────────────────────────────────────

    def refresh_list(self, select: Optional[str] = None) -> None:
        """Filter, sort and push the profile list to the view."""
        search = self.view.get_search_query().strip().lower()
        adapter_filter = self.view.get_adapter_filter().strip()

        filtered: List[str] = []
        adapter_values = {"Все адаптеры"}

        for name, profile in self._profiles.items():
            adapter_values.add(profile.adapter or "")
            if search and search not in name.lower():
                continue
            if adapter_filter != "Все адаптеры" and profile.adapter != adapter_filter:
                continue
            filtered.append(name)

        self.view.update_adapter_filter_values(
            ["Все адаптеры"] + sorted(v for v in adapter_values if v)
        )

        if not filtered:
            self._current_key = None
            self.view.show_profiles_list([], None)
            return

        chosen = select if select in filtered else filtered[0]
        self._current_key = chosen
        self.view.show_profiles_list(filtered, chosen)
        self._load_into_form(chosen)

        # Keep wifi combo in sync
        self.view.update_wifi_profile_combo(list(self._profiles.keys()))

    @property
    def current_key(self) -> Optional[str]:
        return self._current_key

    @current_key.setter
    def current_key(self, value: Optional[str]) -> None:
        self._current_key = value

    def on_select(self, name: str) -> None:
        """User clicked a profile in the list."""
        self._current_key = name
        self._load_into_form(name)

    # ── CRUD ─────────────────────────────────────────────────────

    def create_profile(self) -> None:
        base = "Новый профиль"
        idx = 1
        name = base
        while name in self._profiles:
            idx += 1
            name = f"{base} {idx}"

        default_adapter = self._adapters[0] if self._adapters else "Ethernet"
        profile = Profile(
            id=str(uuid.uuid4()),
            name=name,
            adapter=default_adapter,
            ip_mode=IPMode.DHCP,
            dns_mode=DNSMode.DHCP,
        )
        self._profiles[name] = profile
        self._save_all()
        self.refresh_list(select=name)

    def delete_profile(self, name: str) -> None:
        if name in self._profiles:
            del self._profiles[name]
            self._save_all()
            self.refresh_list(select=next(iter(self._profiles), None))
            self.view.refresh_related_panels()

    def duplicate_profile(self, source_name: str) -> None:
        if source_name not in self._profiles:
            return
        src = self._profiles[source_name]
        idx = 2
        new_name = f"{src.name} ({idx})"
        while new_name in self._profiles:
            idx += 1
            new_name = f"{src.name} ({idx})"

        dup = Profile(
            id=str(uuid.uuid4()),
            name=new_name,
            adapter=src.adapter,
            ip_mode=src.ip_mode,
            ipv4=src.ipv4,
            mask=src.mask,
            gateway=src.gateway,
            dns_mode=src.dns_mode,
            dns_primary=src.dns_primary,
            dns_secondary=src.dns_secondary,
            tags=list(src.tags),
        )
        self._profiles[new_name] = dup
        self._save_all()
        self.refresh_list(select=new_name)

    def save_profile(self, form_data: dict) -> None:
        """
        Save profile from form data.

        *form_data* keys: name, adapter, dhcp_ip, ip, mask, gateway,
        dhcp_dns, dns_primary, dns_secondary.
        """
        try:
            profile = self._form_to_profile(form_data)
            self._validate(profile)

            selected_key = self._current_key
            if selected_key and selected_key != profile.name and selected_key in self._profiles:
                action = self.view.ask_rename_action(selected_key, profile.name)
                if action == "cancel":
                    return
                if action == "rename":
                    del self._profiles[selected_key]
                if action == "save_as_new" and profile.name in self._profiles:
                    if not self.view.ask_yes_no(
                        "Подтверждение",
                        f"Профиль '{profile.name}' уже существует. Перезаписать его?",
                    ):
                        return

            self._profiles[profile.name] = profile
            self._save_all()
            self.refresh_list(select=profile.name)
        except Exception as exc:
            self.view.show_message("Ошибка", str(exc))

    # ── Apply ────────────────────────────────────────────────────

    def apply_profile(self, form_data: dict) -> None:
        """Validate, conflict-check, then apply the profile."""
        try:
            profile = self._form_to_profile(form_data)
            self._validate(profile)

            # IP conflict check
            if not profile.is_dhcp_ip and profile.ipv4:
                in_use = self.container.conflict_check.is_ip_in_use(profile.ipv4)
                if in_use:
                    proceed = self.view.ask_yes_no(
                        "Возможный конфликт IP",
                        f"IP {profile.ipv4} уже используется в сети.\n\nПродолжить применение профиля?",
                    )
                    if not proceed:
                        return

            # Save first
            self._profiles[profile.name] = profile
            self._save_all()

            # Apply via service
            result: ApplyResult = self.container.profile_apply.apply(profile.id)

            self.refresh_list(select=profile.name)
            self.view.refresh_related_panels()
            self.view.show_message("Готово", f"Профиль '{profile.name}' применен.")

            # Toast notification
            if hasattr(self.container, 'toast'):
                adapter = form_data.get("adapter", "")
                self.container.toast.notify_profile_applied(profile.name, adapter)

        except Exception as exc:
            self.view.show_message("Ошибка", str(exc))
            if hasattr(self.container, 'toast'):
                self.container.toast.notify_profile_failed(
                    form_data.get("name", "?"), str(exc)
                )

    # ── Import / Export ──────────────────────────────────────────

    def export_profiles(self, path: str) -> None:
        if not path:
            return
        try:
            self.container.import_export.export_profiles(path)
            logger.info(f"Exported profiles to {path}")
        except Exception as exc:
            self.view.show_message("Ошибка экспорта", str(exc))

    def import_profiles(self, path: str, strategy: str = "rename") -> None:
        if not path:
            return
        try:
            report = self.container.import_export.import_profiles(path, strategy=strategy)
            self._sync_profiles_from_repo()
            self.refresh_list(select=next(iter(self._profiles), None))
            logger.info(f"Import report: {report}")
        except Exception as exc:
            self.view.show_message("Ошибка импорта", str(exc))

    # ── Summary ──────────────────────────────────────────────────

    def get_summary_text(self, form_data: dict) -> str:
        """Build a human-readable summary from current form state."""
        name = form_data.get("name", "-")
        adapter = form_data.get("adapter", "-")
        dhcp_ip = form_data.get("dhcp_ip", False)
        dhcp_dns = form_data.get("dhcp_dns", False)

        lines = [
            f"Профиль: {name}",
            f"Адаптер: {adapter}",
            "",
            "IP режим: DHCP" if dhcp_ip else "IP режим: Статический",
        ]
        if not dhcp_ip:
            lines += [
                f"IP: {form_data.get('ip', '-')}",
                f"Маска: {form_data.get('mask', '-')}",
                f"Шлюз: {form_data.get('gateway', '-')}",
            ]
        lines += ["", "DNS режим: DHCP" if dhcp_dns else "DNS режим: Статический"]
        if not dhcp_dns:
            lines += [
                f"DNS1: {form_data.get('dns_primary', '-')}",
                f"DNS2: {form_data.get('dns_secondary', '-')}",
            ]
        return "\n".join(lines)

    # ── Internals ────────────────────────────────────────────────

    def _sync_profiles_from_repo(self) -> None:
        """Reload profiles dict from repository."""
        repo_profiles = self.container.profile_repo.list()
        self._profiles = {p.name: p for p in repo_profiles}

    def _save_all(self) -> None:
        """Persist current in-memory profiles to repo."""
        for profile in self._profiles.values():
            self.container.profile_repo.save(profile)

    def _load_into_form(self, name: str) -> None:
        profile = self._profiles.get(name)
        if profile:
            self.view.load_profile_form(profile)

    def _form_to_profile(self, data: dict) -> Profile:
        dhcp_ip = data.get("dhcp_ip", False)
        dhcp_dns = data.get("dhcp_dns", False)
        existing = self._profiles.get(self._current_key) if self._current_key else None
        return Profile(
            id=existing.id if existing else str(uuid.uuid4()),
            name=data.get("name", "").strip(),
            adapter=data.get("adapter", "").strip(),
            ip_mode=IPMode.DHCP if dhcp_ip else IPMode.STATIC,
            ipv4=data.get("ip", "").strip(),
            mask=data.get("mask", "").strip(),
            gateway=data.get("gateway", "").strip(),
            dns_mode=DNSMode.DHCP if dhcp_dns else DNSMode.STATIC,
            dns_primary=data.get("dns_primary", "").strip(),
            dns_secondary=data.get("dns_secondary", "").strip(),
            tags=existing.tags if existing else [],
        )

    @staticmethod
    def _validate(profile: Profile) -> None:
        if not profile.name.strip():
            raise ValueError("Введите имя профиля.")
        if not profile.adapter.strip():
            raise ValueError("Выберите сетевой адаптер.")

        def _valid_ip(value: str, field: str) -> None:
            try:
                ipaddress.IPv4Address(value)
            except Exception as exc:
                raise ValueError(f"Некорректное значение поля '{field}': {value}") from exc

        if not profile.is_dhcp_ip:
            if not profile.ipv4 or not profile.mask:
                raise ValueError("Для статического режима обязательны IP и маска.")
            _valid_ip(profile.ipv4, "IP адрес")
            _valid_ip(profile.mask, "Маска подсети")
            if profile.gateway:
                _valid_ip(profile.gateway, "Шлюз")

        if not profile.is_dhcp_dns:
            if profile.dns_primary:
                _valid_ip(profile.dns_primary, "DNS основной")
            if profile.dns_secondary:
                _valid_ip(profile.dns_secondary, "DNS альтернативный")

    def get_profiles(self) -> dict[str, Profile]:
        """Expose current profiles dict (read-only intent)."""
        return dict(self._profiles)

    def get_profile(self, name: str) -> Optional[Profile]:
        return self._profiles.get(name)
