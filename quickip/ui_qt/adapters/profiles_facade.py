"""Qt facade that bridges the Profiles Qt UI with existing ProfilesPresenter logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from quickip.app.bootstrap import ServiceContainer
from quickip.features.profiles.presenter import ProfilesPresenter


@dataclass
class ProfileListItem:
    name: str
    adapter: str
    mode_badge: str


class ProfilesFacade(QObject):
    profiles_changed = Signal(list, str)
    form_loaded = Signal(dict)
    adapter_values_changed = Signal(list)

    def __init__(self, container: ServiceContainer, parent_widget: QWidget) -> None:
        super().__init__(parent_widget)
        self._container = container
        self._parent_widget = parent_widget
        self._presenter = ProfilesPresenter(container)
        self._presenter.bind_view(self)

        self._search_query = ""
        self._adapter_filter = "Все адаптеры"
        self._selected_name: Optional[str] = None

    def bootstrap(self) -> None:
        self._presenter.load_initial()

    # ---- ui->presenter actions ----

    def set_search_query(self, value: str) -> None:
        self._search_query = value
        self._presenter.refresh_list(select=self._selected_name)

    def set_adapter_filter(self, value: str) -> None:
        self._adapter_filter = value
        self._presenter.refresh_list(select=self._selected_name)

    def select_profile(self, name: str) -> None:
        self._selected_name = name
        self._presenter.on_select(name)

    def create_profile(self) -> None:
        self._presenter.create_profile()

    def duplicate_profile(self, name: str) -> None:
        if name:
            self._presenter.duplicate_profile(name)

    def delete_profile(self, name: str) -> None:
        if not name:
            return
        confirm = QMessageBox.question(
            self._parent_widget,
            "Удаление",
            f"Удалить профиль «{name}»?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            self._presenter.delete_profiles([name])

    def export_profiles(self, path: str) -> None:
        self._presenter.export_profiles(path)

    def import_profiles(self, path: str) -> None:
        self._presenter.import_profiles(path, strategy="rename")

    def save_profile(self, form_data: Dict) -> None:
        self._presenter.save_profile(form_data)

    def apply_profile(self, form_data: Dict) -> None:
        self._presenter.apply_profile(form_data)

    # ---- presenter view protocol ----

    def show_profiles_list(self, names: List[str], selected: Optional[str]) -> None:
        items: List[ProfileListItem] = []
        for n in names:
            profile = self._presenter.get_profile(n)
            if profile is None:
                continue
            mode = "DHCP" if profile.is_dhcp_ip else "Static"
            items.append(ProfileListItem(name=n, adapter=profile.adapter or "-", mode_badge=mode))
        self._selected_name = selected
        self.profiles_changed.emit(items, selected or "")

    def load_profile_form(self, profile, focus: bool = False) -> None:
        self.form_loaded.emit(
            {
                "name": profile.name,
                "adapter": profile.adapter,
                "dhcp_ip": profile.is_dhcp_ip,
                "ip": profile.ipv4,
                "mask": profile.mask,
                "gateway": profile.gateway,
                "dhcp_dns": profile.is_dhcp_dns,
                "dns_primary": profile.dns_primary,
                "dns_secondary": profile.dns_secondary,
            }
        )

    def show_message(self, title: str, message: str) -> None:
        QMessageBox.information(self._parent_widget, title, message)

    def ask_yes_no(self, title: str, message: str) -> bool:
        answer = QMessageBox.question(
            self._parent_widget,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def get_adapter_filter(self) -> str:
        return self._adapter_filter

    def get_search_query(self) -> str:
        return self._search_query

    def update_adapter_filter_values(self, values: List[str]) -> None:
        self.adapter_values_changed.emit(values)
