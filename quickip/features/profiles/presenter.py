"""Profiles feature presenter — CRUD, apply, import/export, validation."""

from __future__ import annotations

import ipaddress
import logging
import threading
import uuid
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Protocol

from quickip.domain.models import Profile, IPMode, DNSMode
from quickip.core.events.types import (
    ProfileCreated, ProfileUpdated, ProfileDeleted, ProfilesChanged,
)
from quickip.features.profiles.service import ProfileService
from quickip.features.profiles.import_export import ImportExportService

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)


# ── View protocol ─────────────────────────────────────────────────

class ProfilesViewProtocol(Protocol):
    """UI contract the view must satisfy."""

    def show_profiles_list(self, names: List[str], selected: Optional[str]) -> None: ...
    def load_profile_form(self, profile: Profile, focus: bool = False) -> None: ...
    def show_message(self, title: str, message: str) -> None: ...
    def ask_yes_no(self, title: str, message: str) -> bool: ...
    def get_adapter_filter(self) -> str: ...
    def get_search_query(self) -> str: ...
    def update_adapter_filter_values(self, values: List[str]) -> None: ...


# ── Presenter ─────────────────────────────────────────────────────

class ProfilesPresenter:
    """Orchestrates profile CRUD, apply, import/export.

    Constructor takes only the ServiceContainer (DI convention).
    bind_view() is called from the view's __init__.
    """

    def __init__(self, container: "ServiceContainer") -> None:
        self._container = container
        self._repo = container.profile_repo
        self._service = ProfileService(container)
        self._import_export = ImportExportService(self._repo, container.event_bus)  # type: ignore[arg-type]
        self._view: Optional[ProfilesViewProtocol] = None
        self._profiles: Dict[str, Profile] = {}   # keyed by name
        self._current_key: Optional[str] = None
        self._adapters: List[str] = []

    def bind_view(self, view: ProfilesViewProtocol) -> None:
        """Called by the view's __init__ to register the UI callback target."""
        self._view = view

    def _t(self, key: str) -> str:
        return self._container.i18n.get(key)

    # ── Bootstrap ─────────────────────────────────────────────────

    def load_initial(self) -> None:
        """Load profiles from repo and populate the view."""
        self._sync_from_repo()
        self._adapters = self._service.get_adapters()
        self.refresh_list(select=next(iter(self._profiles), None))

    # ── Adapters ──────────────────────────────────────────────────

    def get_adapters(self) -> List[str]:
        return list(self._adapters)

    def refresh_adapters(self) -> List[str]:
        self._adapters = self._service.get_adapters()
        return list(self._adapters)

    # ── Profile list ──────────────────────────────────────────────

    def refresh_list(self, select: Optional[str] = None) -> None:
        """Filter, sort and push the profile list to the view."""
        if self._view is None:
            return
        search = self._view.get_search_query().strip().lower()
        adapter_filter = self._view.get_adapter_filter().strip()

        filtered: List[str] = []
        adapter_values: set = set()
        all_adapters_label = self._t("filter_all_adapters")

        for name, profile in self._profiles.items():
            if profile.adapter:
                adapter_values.add(profile.adapter)
            if search and search not in name.lower():
                continue
            if adapter_filter and adapter_filter != all_adapters_label and profile.adapter != adapter_filter:
                continue
            filtered.append(name)

        self._view.update_adapter_filter_values(
            [all_adapters_label] + sorted(adapter_values)
        )

        if not filtered:
            self._current_key = None
            self._view.show_profiles_list([], None)
            return

        chosen = select if select in filtered else filtered[0]
        self._current_key = chosen
        self._view.show_profiles_list(filtered, chosen)
        self._load_into_form(chosen, focus=False)

    def on_select(self, name: str) -> None:
        """User selected a profile in the list."""
        self._current_key = name
        self._load_into_form(name, focus=True)

    # ── CRUD ──────────────────────────────────────────────────────

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
        self._container.event_bus.publish(ProfileCreated(profile=profile))  # type: ignore[arg-type]
        self._publish_profiles_changed()
        self.refresh_list(select=name)

    def delete_profile(self, name: str) -> None:
        if name not in self._profiles:
            return
        names = list(self._profiles.keys())
        idx = names.index(name)
        profile = self._profiles.pop(name)
        self._repo.delete(profile.id)
        self._container.event_bus.publish(
            ProfileDeleted(profile_id=profile.id, profile_name=profile.name)
        )
        self._publish_profiles_changed()
        remaining = list(self._profiles.keys())
        next_select = remaining[min(idx, len(remaining) - 1)] if remaining else None
        self.refresh_list(select=next_select)

    def delete_profiles(self, names: List[str]) -> None:
        """Delete multiple profiles at once; select the nearest remaining neighbour."""
        to_delete = [n for n in names if n in self._profiles]
        if not to_delete:
            return
        all_names = list(self._profiles.keys())
        min_idx = min(all_names.index(n) for n in to_delete)
        for name in to_delete:
            profile = self._profiles.pop(name)
            self._repo.delete(profile.id)
            self._container.event_bus.publish(  # type: ignore[arg-type]
                ProfileDeleted(profile_id=profile.id, profile_name=profile.name)
            )
        self._publish_profiles_changed()
        remaining = list(self._profiles.keys())
        next_select = remaining[min(min_idx, len(remaining) - 1)] if remaining else None
        self.refresh_list(select=next_select)

    def duplicate_profile(self, source_name: str) -> None:
        if source_name not in self._profiles:
            return
        src = self._profiles[source_name]
        MAX_LEN = 30  # максимальная длина имени профиля
        idx = 2

        def _make_name(base: str, n: int) -> str:
            suffix = f" ({n})"
            # Если базовое имя + суффикс не влезают — обрезаем базу
            if len(base) + len(suffix) > MAX_LEN:
                base = base[:MAX_LEN - len(suffix)]
            return f"{base}{suffix}"

        new_name = _make_name(src.name, idx)
        while new_name in self._profiles:
            idx += 1
            new_name = _make_name(src.name, idx)

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
        self._publish_profiles_changed()
        self.refresh_list(select=new_name)

    def save_profile(self, form_data: dict) -> None:
        """Save profile from form data; rename old key if name changed."""
        if self._view is None:
            return
        try:
            profile = self._form_to_profile(form_data)
            self._validate(profile)

            # Guard: new name already taken by a DIFFERENT profile
            if (profile.name != self._current_key
                    and profile.name in self._profiles):
                self._view.show_message(
                    self._t("dlg_name_taken_title"),
                    self._t("dlg_name_taken_text").format(name=profile.name),
                )
                return

            if (self._current_key and self._current_key != profile.name
                    and self._current_key in self._profiles):
                del self._profiles[self._current_key]

            self._profiles[profile.name] = profile
            self._save_all()
            self._container.event_bus.publish(ProfileUpdated(profile=profile, old_name=self._current_key))  # type: ignore[arg-type]
            self._publish_profiles_changed()
            self.refresh_list(select=profile.name)
        except Exception as exc:
            self._view.show_message(self._t("error"), str(exc))

    def save_as_new_profile(self, form_data: dict) -> None:
        """Save form data as a brand-new profile with a unique name and new ID."""
        if self._view is None:
            return
        try:
            base = self._form_to_profile(form_data)
            self._validate(base)

            name = base.name
            idx = 2
            while name in self._profiles:
                name = f"{base.name} ({idx})"
                idx += 1

            profile = Profile(
                id=str(uuid.uuid4()),
                name=name,
                adapter=base.adapter,
                ip_mode=base.ip_mode,
                ipv4=base.ipv4,
                mask=base.mask,
                gateway=base.gateway,
                dns_mode=base.dns_mode,
                dns_primary=base.dns_primary,
                dns_secondary=base.dns_secondary,
                tags=list(base.tags),
            )
            self._profiles[name] = profile
            self._save_all()
            self._container.event_bus.publish(ProfileCreated(profile=profile))  # type: ignore[arg-type]
            self._publish_profiles_changed()
            self.refresh_list(select=name)
        except Exception as exc:
            self._view.show_message(self._t("error"), str(exc))

    # ── Apply ─────────────────────────────────────────────────────

    def apply_profile(self, form_data: dict) -> None:
        """Validate form, persist latest state, conflict-check, then apply."""
        if self._view is None:
            return
        try:
            profile = self._form_to_profile(form_data)
            self._validate(profile)

            # Persist current form state
            if (self._current_key and self._current_key != profile.name
                    and self._current_key in self._profiles):
                del self._profiles[self._current_key]
            self._profiles[profile.name] = profile
            self._save_all()

            # IP conflict check
            if not profile.is_dhcp_ip and profile.ipv4:
                if self._service.is_ip_in_use(profile.ipv4):
                    proceed = self._view.ask_yes_no(
                        self._t("dlg_ip_conflict_title"),
                        self._t("dlg_ip_conflict_text").format(ip=profile.ipv4),
                    )
                    if not proceed:
                        return

            result = self._service.apply(profile)
            self._publish_profiles_changed()
            self.refresh_list(select=profile.name)

            if result.success:
                self._view.show_message(
                    self._t("dlg_profile_applied_title"),
                    self._t("dlg_profile_applied_text").format(name=profile.name),
                )
                self._container.toast.notify_profile_applied(profile.name, profile.adapter)
            else:
                self._view.show_message(self._t("dlg_apply_error_title"), result.message)
                self._container.toast.notify_profile_failed(profile.name, result.message)

        except Exception as exc:
            self._view.show_message(self._t("error"), str(exc))
            self._container.toast.notify_profile_failed(form_data.get("name", "?"), str(exc))

    # ── Import / Export ───────────────────────────────────────────

    def export_profiles(self, path: str) -> None:
        if not path or self._view is None:
            return
        try:
            self._import_export.export_profiles(path)
        except Exception as exc:
            self._view.show_message(self._t("dlg_export_error_title"), str(exc))

    def import_profiles(self, path: str, strategy: str = "rename") -> None:
        if not path or self._view is None:
            return
        try:
            self._import_export.import_profiles(path, strategy=strategy)
            self._sync_from_repo()
            self._publish_profiles_changed()
            self.refresh_list(select=next(iter(self._profiles), None))
        except Exception as exc:
            self._view.show_message(self._t("dlg_import_error_title"), str(exc))

    # ── Summary ───────────────────────────────────────────────────

    def get_summary_text(self, form_data: dict) -> str:
        """Build a human-readable summary from current form state."""
        dhcp_ip  = form_data.get("dhcp_ip", False)
        dhcp_dns = form_data.get("dhcp_dns", False)
        lines = [
            f"Профиль: {form_data.get('name', '-')}",
            f"Адаптер: {form_data.get('adapter', '-')}",
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

    def get_network_info(self, callback: Callable[[list], None]) -> None:
        """Fetch current adapter details in background; deliver via callback(list[dict])."""
        def _work() -> None:
            try:
                data = self._service.get_adapters_detail()
                callback(data)
            except Exception:
                logger.exception("get_network_info error")
                callback([])
        threading.Thread(target=_work, daemon=True, name="net_info_fetch").start()

    def get_profile(self, name: str) -> Optional[Profile]:
        return self._profiles.get(name)

    def get_profiles(self) -> Dict[str, Profile]:
        return dict(self._profiles)

    # ── Private helpers ───────────────────────────────────────────

    def _sync_from_repo(self) -> None:
        """Reload in-memory profiles from the repository."""
        self._profiles = {p.name: p for p in self._repo.list()}

    def _save_all(self) -> None:
        """Atomic bulk write of all in-memory profiles to the repository."""
        self._repo.replace_all(list(self._profiles.values()))

    def _load_into_form(self, name: str, focus: bool = False) -> None:
        profile = self._profiles.get(name)
        if profile and self._view:
            self._view.load_profile_form(profile, focus=focus)

    def _publish_profiles_changed(self) -> None:
        self._container.event_bus.publish(  # type: ignore[arg-type]
            ProfilesChanged(profile_names=list(self._profiles.keys()))
        )

    def _form_to_profile(self, data: dict) -> Profile:
        existing = self._profiles.get(self._current_key) if self._current_key else None
        return Profile(
            id=existing.id if existing else str(uuid.uuid4()),
            name=data.get("name", "").strip(),
            adapter=data.get("adapter", "").strip(),
            ip_mode=IPMode.DHCP if data.get("dhcp_ip", False) else IPMode.STATIC,
            ipv4=data.get("ip", "").strip(),
            mask=data.get("mask", "").strip(),
            gateway=data.get("gateway", "").strip(),
            dns_mode=DNSMode.DHCP if data.get("dhcp_dns", False) else DNSMode.STATIC,
            dns_primary=data.get("dns_primary", "").strip(),
            dns_secondary=data.get("dns_secondary", "").strip(),
            tags=existing.tags if existing else [],
        )

    def _validate(self, profile: Profile) -> None:
        if not profile.name.strip():
            raise ValueError(self._t("val_name_required"))
        if len(profile.name) > 30:
            raise ValueError(self._t("val_name_too_long"))
        if not profile.adapter.strip():
            raise ValueError(self._t("val_adapter_required"))

        def _ip(value: str, field_key: str) -> None:
            try:
                ipaddress.IPv4Address(value)
            except Exception as exc:
                raise ValueError(
                    self._t("val_ip_invalid").format(field=self._t(field_key), value=value)
                ) from exc

        if not profile.is_dhcp_ip:
            if not profile.ipv4 or not profile.mask:
                raise ValueError(self._t("val_ip_mask_required"))
            _ip(profile.ipv4, "field_ip")
            _ip(profile.mask, "field_mask")
            if profile.gateway:
                _ip(profile.gateway, "field_gateway")

        if not profile.is_dhcp_dns:
            if profile.dns_primary:
                _ip(profile.dns_primary, "field_dns_primary")
            if profile.dns_secondary:
                _ip(profile.dns_secondary, "field_dns_secondary")
                if profile.dns_secondary == profile.dns_primary:
                    raise ValueError(self._t("val_dns_duplicate"))
