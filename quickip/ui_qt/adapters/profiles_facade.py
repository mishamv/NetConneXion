"""Qt facade that bridges the Profiles Qt UI with existing ProfilesPresenter logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

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
        """Удаляет один профиль — обёртка для обратной совместимости."""
        if name:
            self.delete_profiles([name])

    def delete_profiles(self, names: List[str]) -> None:
        """Удаляет один или несколько профилей с подтверждением."""
        if not names:
            return

        dlg = QDialog(self._parent_widget)
        dlg.setWindowTitle("Удаление")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(16)

        if len(names) == 1:
            display_name = names[0] if len(names[0]) <= 28 else names[0][:25] + "..."
            text = f"Удалить профиль «{display_name}»?"
        else:
            text = f"Удалить {len(names)} профиля(-ей)?"

        lbl = QLabel(text)
        lbl.setFixedWidth(340)
        lbl.setWordWrap(False)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        btn_no = QPushButton("Отмена")
        btn_no.setProperty("role", "action")
        btn_no.setFixedSize(90, 32)
        btn_no.clicked.connect(dlg.reject)

        btn_yes = QPushButton("Удалить")
        btn_yes.setProperty("role", "delete")
        btn_yes.setFixedSize(90, 32)
        btn_yes.clicked.connect(dlg.accept)

        btn_row.addWidget(btn_no)
        btn_row.addWidget(btn_yes)
        lay.addLayout(btn_row)

        dlg.setFixedSize(420, 110)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._presenter.delete_profiles(names)

    def export_profiles(self, path: str) -> None:
        self._presenter.export_profiles(path)

    def import_profiles(self, path: str) -> None:
        self._presenter.import_profiles(path, strategy="rename")

    def save_profile(self, form_data: Dict) -> None:
        # Если редактируем существующий профиль — показываем диалог подтверждения
        if self._selected_name:
            action = self._confirm_save_dialog(self._selected_name)
            if action == "cancel":
                return
            elif action == "new":
                # Сохраняем как новый — сбрасываем текущий ключ в presenter
                self._presenter._current_key = None
        self._presenter.save_profile(form_data)

    def _confirm_save_dialog(self, name: str) -> str:
        """Показывает диалог подтверждения сохранения.
        Возвращает: 'save' | 'new' | 'cancel'
        """
        dlg = QDialog(self._parent_widget)
        dlg.setWindowTitle("Сохранение профиля")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(16)

        display_name = name if len(name) <= 28 else name[:25] + "..."
        lbl = QLabel(f"Изменить сохранённый профиль «{display_name}»?")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedWidth(380)
        lbl.setWordWrap(False)
        lay.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setProperty("role", "action")
        btn_cancel.setFixedSize(90, 32)

        btn_new = QPushButton("Сохранить как новый")
        btn_new.setProperty("role", "action")
        btn_new.setFixedSize(150, 32)

        btn_save = QPushButton("Сохранить")
        btn_save.setProperty("role", "primary")
        btn_save.setFixedSize(100, 32)

        result = ["cancel"]

        btn_cancel.clicked.connect(dlg.reject)
        btn_new.clicked.connect(lambda: (result.__setitem__(0, "new"), dlg.accept()))
        btn_save.clicked.connect(lambda: (result.__setitem__(0, "save"), dlg.accept()))

        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        dlg.setFixedSize(460, 110)
        dlg.exec()
        return result[0]

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
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def get_adapter_filter(self) -> str:
        return self._adapter_filter

    def get_search_query(self) -> str:
        return self._search_query

    def update_adapter_filter_values(self, values: List[str]) -> None:
        self.adapter_values_changed.emit(values)
