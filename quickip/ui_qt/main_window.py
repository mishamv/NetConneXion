"""PySide6 parallel main window (MVP: Profiles screen only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from quickip.app.bootstrap import bootstrap
from quickip.ui_qt.adapters.profiles_facade import ProfilesFacade, ProfileListItem
from quickip.ui_qt.theme import load_qss


@dataclass
class _NavItem:
    key: str
    label: str
    icon: str


class BackdropWidget(QWidget):
    """Paints atmospheric gradient background with vignette and subtle noise."""

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Base vertical gradient.
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#163564"))
        gradient.setColorAt(0.35, QColor("#2A4E85"))
        gradient.setColorAt(0.72, QColor("#4A6FA8"))
        gradient.setColorAt(1.0, QColor("#6F8FC7"))
        painter.fillRect(self.rect(), gradient)

        # Primary light spot near center-top.
        primary = QRadialGradient(self.width() * 0.5, self.height() * 0.14, max(self.width(), self.height()) * 0.75)
        primary.setColorAt(0.0, QColor(223, 236, 255, 92))
        primary.setColorAt(1.0, QColor(223, 236, 255, 0))
        painter.fillRect(self.rect(), primary)

        # Secondary side glow for depth.
        side = QRadialGradient(self.width() * 0.12, self.height() * 0.62, max(self.width(), self.height()) * 0.58)
        side.setColorAt(0.0, QColor(132, 177, 255, 52))
        side.setColorAt(1.0, QColor(132, 177, 255, 0))
        painter.fillRect(self.rect(), side)

        # Bottom mist band.
        mist = QLinearGradient(0, self.height() * 0.66, 0, self.height())
        mist.setColorAt(0.0, QColor(236, 242, 255, 10))
        mist.setColorAt(0.52, QColor(236, 242, 255, 58))
        mist.setColorAt(1.0, QColor(236, 242, 255, 96))
        painter.fillRect(self.rect(), mist)

        # Soft wave highlights near the bottom.
        wave_pen = QPen(QColor(255, 255, 255, 78), 3)
        wave_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(wave_pen)
        wave1 = QPainterPath()
        y1 = self.height() * 0.915
        wave1.moveTo(-40, y1)
        wave1.cubicTo(self.width() * 0.18, y1 - 26, self.width() * 0.38, y1 + 20, self.width() * 0.62, y1 - 6)
        wave1.cubicTo(self.width() * 0.82, y1 - 22, self.width() * 0.96, y1 + 8, self.width() + 40, y1 - 8)
        painter.drawPath(wave1)

        wave_pen2 = QPen(QColor(255, 255, 255, 42), 2)
        wave_pen2.setCapStyle(Qt.RoundCap)
        painter.setPen(wave_pen2)
        wave2 = QPainterPath()
        y2 = self.height() * 0.86
        wave2.moveTo(-60, y2)
        wave2.cubicTo(self.width() * 0.16, y2 - 18, self.width() * 0.34, y2 + 12, self.width() * 0.56, y2 - 6)
        wave2.cubicTo(self.width() * 0.76, y2 - 20, self.width() * 0.92, y2 + 6, self.width() + 50, y2 - 6)
        painter.drawPath(wave2)

        # Radial vignette overlay.
        vignette = QRadialGradient(self.rect().center(), max(self.width(), self.height()) * 0.8)
        vignette.setColorAt(0.58, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(8, 18, 36, 70))
        painter.fillRect(self.rect(), vignette)

        # Soft border vignette pass.
        for i in range(5):
            alpha = 11 - i
            inset = i * 24
            painter.setPen(QPen(QColor(22, 42, 74, max(alpha, 2)), 20))
            painter.drawRoundedRect(self.rect().adjusted(inset, inset, -inset, -inset), 30, 30)

        # Subtle deterministic noise.
        painter.setPen(QColor(255, 255, 255, 6))
        w, h = self.width(), self.height()
        for y in range(0, h, 3):
            for x in range(0, w, 3):
                if ((x * 13 + y * 17) % 113) == 0:
                    painter.drawPoint(x, y)


class Card(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setProperty("class", "card")
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        lay.addWidget(self.title)
        self.content = QWidget()
        lay.addWidget(self.content, 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)


class ProfileRowWidget(QWidget):
    """Visual list row for saved profiles."""

    def __init__(self, item: ProfileListItem) -> None:
        super().__init__()
        self._selected = False
        self.setObjectName("ProfileRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        self.icon = QLabel("◈")
        self.icon.setObjectName("ProfileIcon")
        lay.addWidget(self.icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(8)

        self.name = QLabel(item.name)
        self.name.setObjectName("ProfileName")
        top.addWidget(self.name)

        self.mode_badge = QLabel(item.mode_badge)
        self.mode_badge.setObjectName("ModeBadge")
        top.addWidget(self.mode_badge)
        top.addStretch(1)

        text_col.addLayout(top)

        self.meta = QLabel(item.adapter or "-")
        self.meta.setObjectName("ProfileMeta")
        text_col.addWidget(self.meta)

        lay.addLayout(text_col, 1)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        if selected:
            lift = QGraphicsDropShadowEffect(self)
            lift.setBlurRadius(22)
            lift.setOffset(0, 6)
            lift.setColor(QColor(42, 100, 210, 82))
            self.setGraphicsEffect(lift)
        else:
            self.setGraphicsEffect(None)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._selected:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2D7DFF"))
        painter.drawRoundedRect(2, 8, 3, max(8, self.height() - 16), 2, 2)


class ProfilesPage(QWidget):
    def __init__(self, facade: ProfilesFacade) -> None:
        super().__init__()
        self.facade = facade

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        self.saved_card = Card("Saved Profiles")
        self.editor_card = Card("Profile Editor")
        splitter.addWidget(self.saved_card)
        splitter.addWidget(self.editor_card)
        splitter.setSizes([420, 800])

        self._build_saved_profiles()
        self._build_editor()

        self.facade.profiles_changed.connect(self._render_profiles)
        self.facade.form_loaded.connect(self._load_form)
        self.facade.adapter_values_changed.connect(self._set_adapter_values)

    def _build_saved_profiles(self) -> None:
        lay = QVBoxLayout(self.saved_card.content)
        lay.setContentsMargins(0, 0, 0, 0)

        self.search = QLineEdit()
        self.search.setObjectName("ProfilesSearch")
        self.search.setPlaceholderText("Search profiles...")
        self.search.textChanged.connect(self.facade.set_search_query)
        lay.addWidget(self.search)

        self.adapter_filter = QComboBox()
        self.adapter_filter.setObjectName("AdapterFilter")
        self.adapter_filter.addItem("All adapters")
        self.adapter_filter.currentTextChanged.connect(self._apply_profile_filters)
        lay.addWidget(self.adapter_filter)

        self.list = QListWidget()
        self.list.setObjectName("ProfilesList")
        self.list.setSpacing(8)
        self.list.itemSelectionChanged.connect(self._on_profile_selected)
        lay.addWidget(self.list, 1)

        actions_wrap = QFrame()
        actions_wrap.setObjectName("SavedActions")
        actions_grid = QGridLayout(actions_wrap)
        actions_grid.setContentsMargins(8, 8, 8, 8)
        actions_grid.setHorizontalSpacing(8)
        actions_grid.setVerticalSpacing(8)
        self.btn_new = QPushButton("✚ New")
        self.btn_copy = QPushButton("Copy")
        self.btn_export = QPushButton("Export")
        self.btn_import = QPushButton("Import")
        self.btn_delete = QPushButton("Delete")

        self.btn_new.setProperty("role", "primary")
        self.btn_copy.setProperty("role", "secondary")
        self.btn_export.setProperty("role", "soft_blue")
        self.btn_import.setProperty("role", "soft_purple")
        self.btn_delete.setProperty("role", "danger")

        self.btn_new.clicked.connect(self.facade.create_profile)
        self.btn_copy.clicked.connect(lambda: self.facade.duplicate_profile(self._selected_name()))
        self.btn_export.clicked.connect(self._on_export)
        self.btn_import.clicked.connect(self._on_import)
        self.btn_delete.clicked.connect(lambda: self.facade.delete_profile(self._selected_name()))

        for b in (self.btn_new, self.btn_copy, self.btn_export, self.btn_import, self.btn_delete):
            b.setMinimumHeight(38)
            b.setMaximumHeight(38)
            b.setProperty("compact", False)

        actions_grid.addWidget(self.btn_new, 0, 0)
        actions_grid.addWidget(self.btn_copy, 0, 1)
        actions_grid.addWidget(self.btn_export, 0, 2)
        actions_grid.addWidget(self.btn_import, 1, 0)
        actions_grid.addWidget(self.btn_delete, 1, 1)
        actions_grid.setColumnStretch(0, 1)
        actions_grid.setColumnStretch(1, 1)
        actions_grid.setColumnStretch(2, 1)
        lay.addWidget(actions_wrap)

    def _build_editor(self) -> None:
        lay = QVBoxLayout(self.editor_card.content)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        self.editor_actions_wrap = QWidget()
        self.editor_actions_wrap.setObjectName("EditorActionsWrap")
        self.editor_actions_layout = QHBoxLayout(self.editor_actions_wrap)
        self.editor_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_actions_layout.setSpacing(8)
        self.editor_actions_layout.addStretch(1)
        lay.addWidget(self.editor_actions_wrap)

        form = QWidget()
        lay.addWidget(form, 1)

        grid = QGridLayout(form)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        grid.setColumnMinimumWidth(0, 146)

        self.name_edit = QLineEdit()
        self.adapter_combo = QComboBox()
        self.dhcp_ip_cb = QCheckBox("Use DHCP for IP")
        self.ip_edit = QLineEdit()
        self.mask_edit = QLineEdit()
        self.gw_edit = QLineEdit()
        self.dhcp_dns_cb = QCheckBox("Use DHCP for DNS")
        self.dns1_edit = QLineEdit()
        self.dns2_edit = QLineEdit()

        name_label = QLabel("Profile Name")
        name_label.setMinimumWidth(146)
        grid.addWidget(name_label, 0, 0)
        grid.addWidget(self.name_edit, 0, 1)
        adapter_label = QLabel("Adapter")
        adapter_label.setMinimumWidth(146)
        grid.addWidget(adapter_label, 1, 0)
        grid.addWidget(self.adapter_combo, 1, 1)
        grid.addWidget(self.dhcp_ip_cb, 2, 0, 1, 2)
        ip_label = QLabel("IP Address")
        ip_label.setMinimumWidth(146)
        grid.addWidget(ip_label, 3, 0)
        grid.addWidget(self.ip_edit, 3, 1)
        mask_label = QLabel("Subnet Mask")
        mask_label.setMinimumWidth(146)
        grid.addWidget(mask_label, 4, 0)
        grid.addWidget(self.mask_edit, 4, 1)
        gateway_label = QLabel("Gateway")
        gateway_label.setMinimumWidth(146)
        grid.addWidget(gateway_label, 5, 0)
        grid.addWidget(self.gw_edit, 5, 1)

        dns_sep = QLabel("DNS Settings")
        dns_sep.setObjectName("DnsSectionLabel")
        grid.addWidget(dns_sep, 6, 0, 1, 2)
        grid.addWidget(self.dhcp_dns_cb, 7, 0, 1, 2)
        dns1_label = QLabel("Primary DNS")
        dns1_label.setMinimumWidth(146)
        grid.addWidget(dns1_label, 8, 0)
        grid.addWidget(self.dns1_edit, 8, 1)
        dns2_label = QLabel("Secondary DNS")
        dns2_label.setMinimumWidth(146)
        grid.addWidget(dns2_label, 9, 0)
        grid.addWidget(self.dns2_edit, 9, 1)

        self.dhcp_ip_cb.toggled.connect(self._apply_dhcp_state)
        self.dhcp_dns_cb.toggled.connect(self._apply_dhcp_state)

    def _render_profiles(self, items: List[ProfileListItem], selected: str) -> None:
        self._all_items = items
        self._selected_profile_name = selected
        self._refresh_adapter_filter_options(items)
        self._apply_profile_filters()

    def _refresh_adapter_filter_options(self, items: List[ProfileListItem]) -> None:
        adapters = sorted({(i.adapter or "").strip() for i in items if (i.adapter or "").strip()})
        current = self.adapter_filter.currentText() if hasattr(self, "adapter_filter") else "All adapters"
        self.adapter_filter.blockSignals(True)
        self.adapter_filter.clear()
        self.adapter_filter.addItem("All adapters")
        self.adapter_filter.addItems(adapters)
        idx = self.adapter_filter.findText(current)
        self.adapter_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.adapter_filter.blockSignals(False)

    def _apply_profile_filters(self) -> None:
        selected_adapter = self.adapter_filter.currentText() if hasattr(self, "adapter_filter") else "All adapters"
        self.list.clear()
        for p in getattr(self, "_all_items", []):
            adapter = (p.adapter or "").strip()
            if selected_adapter != "All adapters" and adapter != selected_adapter:
                continue
            row_item = QListWidgetItem()
            row_item.setData(Qt.UserRole, p.name)
            row_item.setSizeHint(QRect(0, 0, 0, 62).size())
            self.list.addItem(row_item)
            row = ProfileRowWidget(p)
            is_selected = p.name == getattr(self, "_selected_profile_name", "")
            row.set_selected(is_selected)
            self.list.setItemWidget(row_item, row)
            if is_selected:
                row_item.setSelected(True)

    def _load_form(self, data: Dict) -> None:
        self.editor_card.title.setText(f"Profile Editor — {data.get('name', '-')}")
        self.name_edit.setText(data.get("name", ""))
        self._set_combo_value(self.adapter_combo, data.get("adapter", ""))
        self.dhcp_ip_cb.setChecked(bool(data.get("dhcp_ip", False)))
        self.ip_edit.setText(data.get("ip", ""))
        self.mask_edit.setText(data.get("mask", ""))
        self.gw_edit.setText(data.get("gateway", ""))

        self.dhcp_dns_cb.setChecked(bool(data.get("dhcp_dns", False)))
        self.dns1_edit.setText(data.get("dns_primary", ""))
        self.dns2_edit.setText(data.get("dns_secondary", ""))
        self._apply_dhcp_state()

    def _set_adapter_values(self, values: List[str]) -> None:
        current = self.adapter_combo.currentText()
        self.adapter_combo.clear()
        self.adapter_combo.addItems(values)
        self._set_combo_value(self.adapter_combo, current)

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif value:
            combo.addItem(value)
            combo.setCurrentText(value)

    def _selected_name(self) -> str:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def _on_profile_selected(self) -> None:
        name = self._selected_name()
        if name:
            self.facade.select_profile(name)
        for i in range(self.list.count()):
            item = self.list.item(i)
            widget = self.list.itemWidget(item)
            if isinstance(widget, ProfileRowWidget):
                widget.set_selected(item.isSelected())

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export profiles", "", "JSON (*.json)")
        if path:
            self.facade.export_profiles(path)

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import profiles", "", "JSON (*.json)")
        if path:
            self.facade.import_profiles(path)

    def _apply_dhcp_state(self) -> None:
        ip_disabled = self.dhcp_ip_cb.isChecked()
        self.ip_edit.setEnabled(not ip_disabled)
        self.mask_edit.setEnabled(not ip_disabled)
        self.gw_edit.setEnabled(not ip_disabled)

        dns_disabled = self.dhcp_dns_cb.isChecked()
        self.dns1_edit.setEnabled(not dns_disabled)
        self.dns2_edit.setEnabled(not dns_disabled)

    def collect_form_data(self) -> Dict:
        return {
            "name": self.name_edit.text(),
            "adapter": self.adapter_combo.currentText(),
            "dhcp_ip": self.dhcp_ip_cb.isChecked(),
            "ip": self.ip_edit.text(),
            "mask": self.mask_edit.text(),
            "gateway": self.gw_edit.text(),
            "dhcp_dns": self.dhcp_dns_cb.isChecked(),
            "dns_primary": self.dns1_edit.text(),
            "dns_secondary": self.dns2_edit.text(),
        }


class QtMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.container = bootstrap()
        self.theme_mode = str(self.container.settings_repo.get("ui_theme", "light")).lower()

        self.setWindowTitle("NetConneXion v2.0")
        self.resize(1380, 860)

        root = BackdropWidget()
        root.setObjectName("RootWindow")
        self.setCentralWidget(root)

        page = QHBoxLayout(root)
        page.setContentsMargins(12, 12, 12, 12)
        page.setSpacing(12)

        self.sidebar = QFrame()
        self.sidebar.setProperty("class", "sidebar")
        self.sidebar.setObjectName("Sidebar")
        side_l = QVBoxLayout(self.sidebar)
        side_l.setContentsMargins(10, 12, 10, 12)
        side_l.setSpacing(7)
        page.addWidget(self.sidebar, 0)

        self.stack = QStackedWidget()
        right_box = QVBoxLayout()
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.setSpacing(12)
        page.addLayout(right_box, 1)

        self.header = QFrame()
        self.header.setProperty("class", "topbar")
        self.header.setObjectName("Header")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(10)

        logo = QLabel("✳")
        logo.setObjectName("LogoMark")
        title = QLabel("NetConneXion v2.0")
        title.setObjectName("AppTitle")
        h.addWidget(logo)
        h.addWidget(title)

        self.btn_apply = QPushButton("Apply")
        self.btn_save = QPushButton("Save")
        self.btn_apply.setProperty("class", "primary")
        self.btn_save.setProperty("class", "secondary")
        self.btn_apply.setProperty("role", "primary")
        self.btn_save.setProperty("role", "secondary")
        self.btn_apply.setMinimumHeight(38)
        self.btn_save.setMinimumHeight(38)

        self.btn_theme = QPushButton("Theme")
        self.btn_theme.setProperty("class", "secondary")
        self.btn_theme.setProperty("role", "secondary")
        h.addWidget(self.btn_theme)

        right_box.addWidget(self.header)
        right_box.addWidget(self.stack, 1)

        self._build_nav(side_l)
        self._build_pages()
        self.profiles_page.editor_actions_layout.addWidget(self.btn_apply)
        self.profiles_page.editor_actions_layout.addWidget(self.btn_save)
        self._tag_widgets_for_premium_qss()

        self.btn_apply.clicked.connect(lambda: self.facade.apply_profile(self.profiles_page.collect_form_data()))
        self.btn_save.clicked.connect(lambda: self.facade.save_profile(self.profiles_page.collect_form_data()))
        self.btn_theme.clicked.connect(self._toggle_theme)

        self._apply_theme()
        self.facade.bootstrap()

    def _tag_widgets_for_premium_qss(self) -> None:
        # Keep style classes explicit for premium QSS selectors.
        for _, button in self.nav_buttons.items():
            button.setProperty("class", "nav")

        self.profiles_page.saved_card.setProperty("class", "card")
        self.profiles_page.editor_card.setProperty("class", "card")
        self.header.setProperty("class", "topbar")
        self.sidebar.setProperty("class", "sidebar")

    def _build_nav(self, side_l: QVBoxLayout) -> None:
        self.nav_buttons: dict[str, QPushButton] = {}
        for item in [
            _NavItem("profiles", "Profiles", "◻"),
            _NavItem("wifi", "Wi-Fi", "⌁"),
            _NavItem("tools", "Tools", "⌘"),
            _NavItem("settings", "Settings", "⚙"),
        ]:
            b = QPushButton(f"{item.icon}  {item.label}")
            b.setProperty("class", "nav")
            b.setProperty("nav", True)
            b.clicked.connect(lambda _=False, key=item.key: self._switch_page(key))
            side_l.addWidget(b)
            self.nav_buttons[item.key] = b
        side_l.addStretch(1)

    def _build_pages(self) -> None:
        self.facade = ProfilesFacade(self.container, self)
        self.profiles_page = ProfilesPage(self.facade)
        self.stack.addWidget(self.profiles_page)

        for title in ("Wi-Fi placeholder", "Tools placeholder", "Settings placeholder"):
            w = QWidget()
            l = QVBoxLayout(w)
            lbl = QLabel(title)
            lbl.setObjectName("Placeholder")
            lbl.setAlignment(Qt.AlignCenter)
            l.addWidget(lbl, 1)
            self.stack.addWidget(w)

        self._switch_page("profiles")

    def _switch_page(self, key: str) -> None:
        idx = {"profiles": 0, "wifi": 1, "tools": 2, "settings": 3}[key]
        self.stack.setCurrentIndex(idx)
        for k, btn in self.nav_buttons.items():
            btn.setProperty("active", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            if k == key:
                btn.setProperty("active", True)
            else:
                btn.setProperty("active", False)

    def _apply_premium_effects(self) -> None:
        # Apply coherent depth and glow effects after style updates.
        shadow_alpha = 170 if self.theme_mode == "dark" else 70
        shadow_blur = 36 if self.theme_mode == "dark" else 30

        for widget in (self.sidebar, self.header, self.profiles_page.saved_card, self.profiles_page.editor_card):
            effect = QGraphicsDropShadowEffect(widget)
            effect.setBlurRadius(shadow_blur)
            effect.setOffset(0, 12)
            effect.setColor(QColor(0, 0, 0, shadow_alpha))
            widget.setGraphicsEffect(effect)

        apply_glow = QGraphicsDropShadowEffect(self.btn_apply)
        apply_glow.setBlurRadius(46)
        apply_glow.setOffset(0, 4)
        apply_glow.setColor(QColor(45, 125, 255, 105 if self.theme_mode == "dark" else 80))
        self.btn_apply.setGraphicsEffect(apply_glow)

        for key, btn in self.nav_buttons.items():
            if key == "profiles" and self.stack.currentIndex() == 0:
                glow = QGraphicsDropShadowEffect(btn)
                glow.setBlurRadius(20)
                glow.setOffset(0, 2)
                glow.setColor(QColor(45, 125, 255, 110))
                btn.setGraphicsEffect(glow)
            elif btn.property("active"):
                glow = QGraphicsDropShadowEffect(btn)
                glow.setBlurRadius(20)
                glow.setOffset(0, 2)
                glow.setColor(QColor(45, 125, 255, 110))
                btn.setGraphicsEffect(glow)
            else:
                btn.setGraphicsEffect(None)

    def _apply_theme(self) -> None:
        self.setStyleSheet(load_qss(self.theme_mode))

        # Keep placeholder text readable across theme switches.
        placeholder = QColor(227, 238, 255, 194) if self.theme_mode == "dark" else QColor(86, 114, 166, 175)
        for field in (self.profiles_page.search,):
            pal = field.palette()
            pal.setColor(QPalette.PlaceholderText, placeholder)
            field.setPalette(pal)

        self._apply_premium_effects()

    def _toggle_theme(self) -> None:
        self.theme_mode = "dark" if self.theme_mode == "light" else "light"
        self.container.settings_repo.set("ui_theme", self.theme_mode)
        self._apply_theme()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    w = QtMainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
