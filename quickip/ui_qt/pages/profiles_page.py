"""Profiles page — list + editor for network profiles."""

from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from quickip.ui_qt.adapters.profiles_facade import ProfilesFacade, ProfileListItem
from quickip.ui_qt.widgets.elide_label import ElideLabel
from quickip.ui_qt.widgets.toggle_switch import ToggleSwitch
from quickip.ui_qt.palette import color, semantic_color


class ProfileRowWidget(QWidget):
    """Строка профиля в списке: иконка сети + имя + адаптер/режим."""

    _WIFI_KEYWORDS = {"wi-fi", "wifi", "wireless", "беспровод", "wlan", "802.11"}

    def __init__(self, item: ProfileListItem, dark_mode: bool = True) -> None:
        super().__init__()
        self._selected = False
        self._dark_mode = dark_mode
        self.setObjectName("ProfileRow")

        adapter_lower = (item.adapter or "").lower()
        self._is_wifi = any(k in adapter_lower for k in self._WIFI_KEYWORDS)

        # Отступ слева = 10 (иконка x) + 34 (иконка w) + 10 (gap) = 54
        lay = QHBoxLayout(self)
        lay.setContentsMargins(54, 10, 12, 10)
        lay.setSpacing(0)

        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        self.name_lbl = ElideLabel(item.name)
        self.name_lbl.setObjectName("ProfileName")
        col.addWidget(self.name_lbl)

        mode = item.mode_badge.upper()
        adapter = item.adapter or "—"
        self.meta_lbl = QLabel(f"{adapter}  ·  {mode}")
        self.meta_lbl.setObjectName(
            "ProfileMetaDhcp" if mode == "DHCP" else "ProfileMetaStatic"
        )
        col.addWidget(self.meta_lbl)
        lay.addLayout(col, 1)

    def set_selected(self, selected: bool, dark_mode: bool = True) -> None:
        self._selected = selected
        self._dark_mode = dark_mode
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)

        # Фон при выделении
        if self._selected:
            if self._dark_mode:
                # Фон выделенной строки: общий ACCENT с ~11% прозрачностью.
                painter.setPen(Qt.PenStyle.NoPen)
                selected_bg = QColor(semantic_color("ACCENT"))
                selected_bg.setAlpha(28)
                painter.setBrush(selected_bg)
                painter.drawRoundedRect(r, 9, 9)
                # Рамка выделенной строки: общий ACCENT, alpha=85/255 (~33%).
                selected_border = QColor(semantic_color("ACCENT"))
                selected_border.setAlpha(85)
                painter.setPen(QPen(selected_border, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(r, 9, 9)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(semantic_color("LIGHT_SELECTION_BG")))
                painter.drawRoundedRect(r, 9, 9)
                painter.setPen(QPen(QColor(semantic_color("LIGHT_SELECTION_BORDER")), 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(r, 9, 9)

        # Плашка иконки — фиксированные координаты (не зависят от height() при первой отрисовке)
        margin = 10   # совпадает с contentsMargins top/bottom
        ix, iy, iw, ih = 10, margin, 34, 34
        # Иконка-плашка: общий ACCENT с alpha 40 (выделено) или 28 (обычно).
        bg = QColor(
            semantic_color("ACCENT" if self._dark_mode else "LIGHT_ICON_BG")
        )
        if self._dark_mode:
            bg.setAlpha(40 if self._selected else 28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(ix, iy, iw, ih, 9, 9)

        icon_theme = "dark" if self._dark_mode else "light"
        icon_prefix = "DARK" if self._dark_mode else "LIGHT"
        ic = QColor(color(icon_theme, f"{icon_prefix}_CUSTOM_PROFILE_ICON"))
        ic.setAlpha(
            210 if self._selected else (160 if self._dark_mode else 170)
        )
        cx, cy = ix + iw // 2, iy + ih // 2
        if self._is_wifi:
            self._draw_wifi(painter, cx, cy, ic)
        else:
            self._draw_ethernet(painter, cx, cy, ic)

    def _draw_ethernet(self, p: QPainter, cx: int, cy: int, c: QColor) -> None:
        pen = QPen(c, 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(cx, cy - 4, cx, cy + 1)
        p.drawLine(cx - 5, cy + 1, cx + 5, cy + 1)
        p.drawLine(cx - 5, cy + 1, cx - 5, cy + 5)
        p.drawLine(cx + 5, cy + 1, cx + 5, cy + 5)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(cx - 3, cy - 8, 6, 4, 1, 1)
        p.drawRoundedRect(cx - 8, cy + 5, 6, 4, 1, 1)
        p.drawRoundedRect(cx + 2, cy + 5, 6, 4, 1, 1)

    def _draw_wifi(self, p: QPainter, cx: int, cy: int, c: QColor) -> None:
        from PySide6.QtCore import QRectF
        pen = QPen(c, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Все дуги центрированы от одной точки внизу — классический Wi-Fi
        dot_y = cy + 6   # точка внизу
        for r in (10, 7, 4):
            # Дуга: верхние 120° (от 30° до 150°)
            p.drawArc(
                QRectF(cx - r, dot_y - r, r * 2, r * 2),
                30 * 16, 120 * 16
            )

        # Точка
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - 2, dot_y - 2, 4, 4)


class ProfilesPage(QWidget):
    """Страница профилей: список слева + редактор справа."""

    def __init__(self, facade: ProfilesFacade) -> None:
        super().__init__()
        # Stable page selector for theme/QSS rules.
        self.setObjectName("ProfilesPage")
        self.facade = facade
        self._dark_mode = True
        self._all_items: List[ProfileListItem] = []
        self._selected_profile_name = ""
        self._loaded_profile_name = ""  # имя профиля загруженного в форму
        self._form_dirty = False
        self._initialized = False  # True только после первой загрузки формы

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Page header: title (left) + action buttons (right) ────────
        self._page_hdr = QFrame()
        self._page_hdr.setObjectName("PageHeader")
        self._page_hdr.setFixedHeight(52)
        root.addWidget(self._page_hdr)

        # ── Body: left panel + right panel ────────────────────────────
        _body = QWidget()
        _body.setObjectName("PageBody")
        _body_lay = QHBoxLayout(_body)
        _body_lay.setContentsMargins(0, 0, 0, 0)
        _body_lay.setSpacing(0)

        self._left = QFrame()
        self._left.setObjectName("LeftPanel")
        self._left.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._left.setFixedWidth(280)

        self._right = QFrame()
        self._right.setObjectName("RightPanel")
        self._right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        _body_lay.addWidget(self._left)
        _body_lay.addWidget(self._right, 1)
        root.addWidget(_body, 1)

        self._build_page_header()
        self._build_left()
        self._build_right()

        self.facade.profiles_changed.connect(self._render_profiles)
        self.facade.form_loaded.connect(self._load_form)
        self.facade.adapter_values_changed.connect(self._set_adapter_values)

    # ── Page header ───────────────────────────────────────────────────

    def _build_page_header(self) -> None:
        """Full-width header: page title (left) + action buttons (right)."""
        lay = QHBoxLayout(self._page_hdr)
        lay.setContentsMargins(24, 0, 16, 0)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._page_title_lbl = QLabel(self._tr("page_profiles"))
        self._page_title_lbl.setObjectName("PageTitle")
        lay.addWidget(self._page_title_lbl)
        lay.addStretch(1)

        self.btn_save = QPushButton("✓  Сохранить")
        self.btn_save.setProperty("role", "action")
        self.btn_save.setObjectName("BtnSave")
        self.btn_save.setFixedSize(100, 28)
        lay.addWidget(self.btn_save)

        self.btn_apply = QPushButton("▶  Применить")
        self.btn_apply.setProperty("role", "primary")
        self.btn_apply.setObjectName("BtnApply")
        self.btn_apply.setFixedSize(110, 28)
        lay.addWidget(self.btn_apply)

    # ── Left panel ────────────────────────────────────────────────────

    def _build_left(self) -> None:
        lay = QVBoxLayout(self._left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setObjectName("PanelHeader")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(13, 10, 13, 8)
        lbl = QLabel("Сохранённые профили")
        lbl.setObjectName("PanelTitle")
        self._lbl_profiles_header = lbl
        hdr_lay.addWidget(lbl)
        hdr_lay.addStretch(1)
        self._count_pill = QLabel("0")
        self._count_pill.setObjectName("CountPill")
        hdr_lay.addWidget(self._count_pill)
        lay.addWidget(hdr)

        # Search
        sw = QFrame()
        sw.setObjectName("SearchWrap")
        sw_lay = QHBoxLayout(sw)
        sw_lay.setContentsMargins(10, 8, 10, 0)
        self.search = QLineEdit()
        self.search.setObjectName("ProfilesSearch")
        self.search.setPlaceholderText("Поиск...")
        self.search.textChanged.connect(self.facade.set_search_query)
        sw_lay.addWidget(self.search)
        lay.addWidget(sw)

        # Adapter filter
        af = QFrame()
        af.setObjectName("SearchWrap")
        af_lay = QHBoxLayout(af)
        af_lay.setContentsMargins(10, 6, 10, 0)
        self.adapter_filter = QComboBox()
        self.adapter_filter.setObjectName("AdapterFilter")
        self.adapter_filter.addItem(self._tr("filter_all_adapters"))
        self.adapter_filter.currentTextChanged.connect(self._apply_profile_filters)
        af_lay.addWidget(self.adapter_filter)
        lay.addWidget(af)

        # Profile list — ExtendedSelection: Ctrl+Click несколько, Shift+Click диапазон
        self.list = QListWidget()
        self.list.setObjectName("ProfilesList")
        self.list.setSpacing(0)
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self._on_profile_selected)
        lay.addWidget(self.list, 1)

        # Actions block — 2+2+1
        actions = QFrame()
        actions.setObjectName("ActionsBlock")
        a_lay = QVBoxLayout(actions)
        a_lay.setContentsMargins(10, 8, 10, 28)
        a_lay.setSpacing(5)

        # Шрифт кнопок блока задан здесь явно (font-size=10pt).
        # Не зависит от QSS и от кнопок Save/Apply.
        _btn_font = QFont("Segoe UI", 10)
        _btn_font.setWeight(QFont.Weight.DemiBold)

        row1 = QHBoxLayout()
        row1.setSpacing(5)
        self.btn_new  = QPushButton("\u2795  Новый")
        self.btn_copy = QPushButton("\u29C9  Копировать")
        self.btn_new.setProperty("role", "primary")
        self.btn_copy.setProperty("role", "action")
        for b in (self.btn_new, self.btn_copy):
            b.setFixedHeight(28)
            b.setFont(_btn_font)
            row1.addWidget(b)
        a_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(5)
        self.btn_export = QPushButton("\u2191  Экспорт")
        self.btn_import = QPushButton("\u2193  Импорт")
        self.btn_export.setProperty("role", "action")
        self.btn_import.setProperty("role", "action")
        for b in (self.btn_export, self.btn_import):
            b.setFixedHeight(28)
            b.setFont(_btn_font)
            row2.addWidget(b)
        a_lay.addLayout(row2)

        self.btn_delete = QPushButton("\u2715  Удалить")
        self.btn_delete.setProperty("role", "delete")
        self.btn_delete.setFixedHeight(28)
        self.btn_delete.setFont(_btn_font)
        a_lay.addWidget(self.btn_delete)

        lay.addWidget(actions)

        self.btn_new.clicked.connect(self.facade.create_profile)
        self.btn_copy.clicked.connect(lambda: self.facade.duplicate_profile(self._selected_name()))
        self.btn_import.clicked.connect(self._on_import)
        self.btn_export.clicked.connect(self._on_export)
        self.btn_delete.clicked.connect(self._on_delete)

    # ── Right panel ───────────────────────────────────────────────────

    def _build_right(self) -> None:
        lay = QVBoxLayout(self._right)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # btn_save / btn_apply are now in _build_page_header()

        # Feedback bar — результат apply
        self._feedback_bar = QLabel("")
        self._feedback_bar.setObjectName("ProfileFeedbackBar")
        self._feedback_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._feedback_bar.setFixedHeight(28)
        self._feedback_bar.setVisible(False)
        lay.addWidget(self._feedback_bar)

        # Scrollable editor body
        scroll = QScrollArea()
        scroll.setObjectName("EditorScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("EditorBody")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 16, 16, 16)
        body_lay.setSpacing(12)

        # General section
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("EditorField")
        self.name_edit.setMaxLength(30)
        self.adapter_combo = QComboBox()
        self.adapter_combo.setObjectName("EditorCombo")
        _sec, self._lbl_sec_basic, _fl = self._section(
            "Основные",
            [("Название", self.name_edit), ("Адаптер", self.adapter_combo)],
        )
        self._lbl_name, self._lbl_adapter_field = _fl
        body_lay.addWidget(_sec)

        # Network section
        self.dhcp_ip_cb = ToggleSwitch("DHCP для IP")
        self.dhcp_ip_cb.setObjectName("DhcpCheck")
        self.ip_edit = QLineEdit()
        self.ip_edit.setObjectName("EditorField")
        self.mask_edit = QLineEdit()
        self.mask_edit.setObjectName("EditorField")
        self.gw_edit = QLineEdit()
        self.gw_edit.setObjectName("EditorField")
        _sec, self._lbl_sec_network, _fl = self._section(
            "Сеть",
            [("IP-адрес", self.ip_edit), ("Маска подсети", self.mask_edit), ("Шлюз", self.gw_edit)],
            top_widget=self.dhcp_ip_cb,
        )
        self._lbl_ip, self._lbl_mask, self._lbl_gw = _fl
        body_lay.addWidget(_sec)

        # DNS section
        self.dhcp_dns_cb = ToggleSwitch("DHCP для DNS")
        self.dhcp_dns_cb.setObjectName("DhcpCheck")
        self.dns1_edit = QLineEdit()
        self.dns1_edit.setObjectName("EditorField")
        self.dns2_edit = QLineEdit()
        self.dns2_edit.setObjectName("EditorField")
        _sec, self._lbl_sec_dns, _fl = self._section(
            "DNS",
            [("Основной DNS", self.dns1_edit), ("Резервный DNS", self.dns2_edit)],
            top_widget=self.dhcp_dns_cb,
        )
        self._lbl_dns1, self._lbl_dns2 = _fl
        body_lay.addWidget(_sec)

        body_lay.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)


        self.dhcp_ip_cb.toggled.connect(self._apply_dhcp_state)
        self.dhcp_dns_cb.toggled.connect(self._apply_dhcp_state)

        # Отслеживаем изменения в форме
        for field in (self.name_edit, self.ip_edit, self.mask_edit,
                      self.gw_edit, self.dns1_edit, self.dns2_edit):
            field.textChanged.connect(self._mark_dirty)
        self.adapter_combo.currentTextChanged.connect(self._mark_dirty)
        self.adapter_combo.activated.connect(lambda: self.adapter_combo.clearFocus())
        self.dhcp_ip_cb.toggled.connect(self._mark_dirty)
        self.dhcp_dns_cb.toggled.connect(self._mark_dirty)

    def _section(
        self, title: str, fields: list, top_widget: QWidget | None = None
    ) -> tuple:
        """Returns (frame, title_label, [field_labels])."""
        sec = QFrame()
        sec.setObjectName("SectionCard")
        lay = QVBoxLayout(sec)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)

        tr = QHBoxLayout()
        tr.setSpacing(8)
        t = QLabel(title.upper())
        t.setObjectName("SectionTitle")
        tr.addWidget(t)
        line = QFrame()
        line.setObjectName("SectionLine")
        line.setFrameShape(QFrame.Shape.HLine)
        tr.addWidget(line, 1)
        if top_widget:
            tr.addWidget(top_widget)   # toggle right-aligned in header row
        lay.addLayout(tr)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(9)
        grid.setColumnMinimumWidth(0, 110)
        grid.setColumnStretch(1, 1)
        field_lbls: list[QLabel] = []
        for i, (lbl_text, widget) in enumerate(fields):
            lbl = QLabel(lbl_text)
            lbl.setObjectName("FieldLabel")
            grid.addWidget(lbl, i, 0)
            grid.addWidget(widget, i, 1)
            field_lbls.append(lbl)
        lay.addLayout(grid)
        return sec, t, field_lbls

    # ── Slots ─────────────────────────────────────────────────────────

    def _render_profiles(self, items: List[ProfileListItem], selected: str) -> None:
        self._all_items = items
        self._selected_profile_name = selected
        self._count_pill.setText(str(len(items)))
        self._apply_profile_filters()

    def _apply_profile_filters(self) -> None:
        sel_adapter = self.adapter_filter.currentText()
        search_q = self.search.text().strip().lower()
        self.list.clear()
        for p in self._all_items:
            if self.adapter_filter.currentIndex() != 0 and p.adapter != sel_adapter:
                continue
            if search_q and search_q not in p.name.lower():
                continue
            li = QListWidgetItem()
            li.setData(Qt.ItemDataRole.UserRole, p.name)
            li.setSizeHint(QSize(0, 70))
            self.list.addItem(li)
            row = ProfileRowWidget(p, self._dark_mode)
            row.set_selected(p.name == self._selected_profile_name, self._dark_mode)
            self.list.setItemWidget(li, row)
            if p.name == self._selected_profile_name:
                li.setSelected(True)
                self.list.setCurrentItem(li)

    def _load_form(self, data: Dict) -> None:
        # Блокируем сигналы чтобы загрузка данных не помечала форму как грязную
        self._form_dirty = False
        for field in (self.name_edit, self.ip_edit, self.mask_edit,
                      self.gw_edit, self.dns1_edit, self.dns2_edit):
            field.blockSignals(True)
        self.adapter_combo.blockSignals(True)
        self.dhcp_ip_cb.blockSignals(True)
        self.dhcp_dns_cb.blockSignals(True)
        is_dhcp = data.get("dhcp_ip", False)
        self.name_edit.setText(data.get("name", ""))
        adapter = data.get("adapter", "")
        if adapter:
            self._set_combo(self.adapter_combo, adapter)
        self.dhcp_ip_cb.setChecked(bool(is_dhcp))
        self.ip_edit.setText(data.get("ip", ""))
        self.mask_edit.setText(data.get("mask", ""))
        self.gw_edit.setText(data.get("gateway", ""))
        self.dhcp_dns_cb.setChecked(bool(data.get("dhcp_dns", False)))
        self.dns1_edit.setText(data.get("dns_primary", ""))
        self.dns2_edit.setText(data.get("dns_secondary", ""))
        self._apply_dhcp_state()

        # Разблокируем сигналы и сбрасываем флаг
        for field in (self.name_edit, self.ip_edit, self.mask_edit,
                      self.gw_edit, self.dns1_edit, self.dns2_edit):
            field.blockSignals(False)
        self.adapter_combo.blockSignals(False)
        self.dhcp_ip_cb.blockSignals(False)
        self.dhcp_dns_cb.blockSignals(False)
        self._loaded_profile_name = data.get("name", "")  # фиксируем какой профиль загружен
        self._form_dirty = False
        self._initialized = True  # с этого момента изменения формы считаются dirty

    def _set_adapter_values(self, values: List[str]) -> None:
        _all_labels = {"Все адаптеров", "All adapters", "Все адаптеры"}
        cur = self.adapter_combo.currentText()
        self.adapter_combo.clear()
        self.adapter_combo.addItems([v for v in values if v and v not in _all_labels])
        # Восстанавливаем выбор только если значение есть в списке
        idx = self.adapter_combo.findText(cur)
        if idx >= 0:
            self.adapter_combo.setCurrentIndex(idx)
        cur_f = self.adapter_filter.currentText()
        self.adapter_filter.blockSignals(True)
        self.adapter_filter.clear()
        self.adapter_filter.addItem(self._tr("filter_all_adapters"))
        for v in values:
            if v and v not in _all_labels:
                self.adapter_filter.addItem(v)
        # Восстанавливаем выбор только если значение есть в списке
        idx = self.adapter_filter.findText(cur_f)
        self.adapter_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.adapter_filter.blockSignals(False)

    def _set_combo(self, combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif value:
            combo.addItem(value)
            combo.setCurrentText(value)

    def _selected_name(self) -> str:
        """Возвращает имя первого выделенного профиля (для Copy/Edit)."""
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _selected_names(self) -> List[str]:
        """Возвращает имена всех выделенных профилей."""
        return [
            self.list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list.count())
            if self.list.item(i).isSelected()
        ]

    def _on_profile_selected(self) -> None:
        selected = self.list.selectedItems()
        if not selected:
            return

        # При одиночном выборе — имя кликнутого профиля
        name = selected[0].data(Qt.ItemDataRole.UserRole) if len(selected) == 1 else self._selected_name()

        # Проверяем dirty: форма изменена И переходим на другой профиль
        # _loaded_profile_name — имя профиля реально загруженного в форму
        is_switching = name != self._loaded_profile_name
        if is_switching and self._form_dirty:
            if not self._confirm_discard():
                self._restore_selection()
                # Синхронизируем _selected_profile_name с реально загруженным профилем
                self._selected_profile_name = self._loaded_profile_name
                return

        self._form_dirty = False
        if name:
            self.facade.select_profile(name)
        for i in range(self.list.count()):
            li = self.list.item(i)
            w = self.list.itemWidget(li)
            if isinstance(w, ProfileRowWidget):
                w.set_selected(li.isSelected(), self._dark_mode)

    def _confirm_discard(self) -> bool:
        """Диалог подтверждения потери несохранённых изменений."""
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(self._tr("dlg_unsaved_title"))
        from PySide6.QtCore import Qt
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(16)
        lbl = QLabel(self._tr("dlg_unsaved_text"))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        btn_no = QPushButton(self._tr("btn_no"))
        btn_no.setProperty("role", "action")
        btn_no.setFixedSize(90, 32)
        btn_no.clicked.connect(dlg.reject)
        btn_yes = QPushButton(self._tr("btn_yes"))
        btn_yes.setProperty("role", "primary")
        btn_yes.setFixedSize(90, 32)
        btn_yes.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_yes)
        btn_row.addWidget(btn_no)
        lay.addLayout(btn_row)
        dlg.setFixedSize(380, 130)
        return dlg.exec() == QDialog.DialogCode.Accepted

    def _restore_selection(self) -> None:
        """Восстанавливает выделение на профиль реально загруженный в форму."""
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            li = self.list.item(i)
            is_cur = li.data(Qt.ItemDataRole.UserRole) == self._loaded_profile_name
            li.setSelected(is_cur)
            if is_cur:
                self.list.setCurrentItem(li)
        self.list.blockSignals(False)

    def _mark_dirty(self, *_) -> None:
        """Помечает форму как изменённую — только после первой инициализации."""
        if self._initialized:
            self._form_dirty = True

    def _on_delete(self) -> None:
        """Удаляет один или несколько выделенных профилей."""
        names = self._selected_names()
        if not names:
            return
        if len(names) == 1:
            msg = self._tr("dlg_delete_profile_q").format(name=names[0])
        else:
            msg = self._tr("dlg_delete_profiles_q").format(count=len(names))
        reply = QMessageBox.question(
            self, self._tr("dlg_confirm_delete_title"), msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.facade.delete_profiles(names)

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self._tr("dlg_export_title"), "", "JSON (*.json)")
        if path:
            self.facade.export_profiles(path)

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self._tr("dlg_import_title"), "", "JSON (*.json)")
        if path:
            self.facade.import_profiles(path)

    def _apply_dhcp_state(self) -> None:
        ip = self.dhcp_ip_cb.isChecked()
        auto_ip = self._tr("dhcp_auto_placeholder") if ip else ""
        for w in (self.ip_edit, self.mask_edit, self.gw_edit):
            w.setEnabled(not ip)
            w.setPlaceholderText(auto_ip)
        dns = self.dhcp_dns_cb.isChecked()
        auto_dns = self._tr("dhcp_auto_placeholder") if dns else ""
        for w in (self.dns1_edit, self.dns2_edit):
            w.setEnabled(not dns)
            w.setPlaceholderText(auto_dns)

    def show_apply_result(self, success: bool, profile_name: str, duration_ms: int = 0) -> None:
        """Показывает результат применения профиля в feedback bar."""
        if success:
            dur = f"  ({duration_ms} ms)" if duration_ms else ""
            text = f"✓  {profile_name} применён{dur}"
            color = semantic_color("STATUS_SUCCESS")
        else:
            text = f"✕  Не удалось применить {profile_name}"
            color = semantic_color("STATUS_ERROR")
        self._feedback_bar.setText(text)
        self._feedback_bar.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 500; background: transparent;"
        )
        self._feedback_bar.setVisible(True)
        QTimer.singleShot(5000, lambda: self._feedback_bar.setVisible(False))

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

    def refresh_theme(self, dark_mode: bool) -> None:
        self._dark_mode = dark_mode
        self._apply_profile_filters()
        self.dhcp_ip_cb.set_dark_mode(dark_mode)
        self.dhcp_dns_cb.set_dark_mode(dark_mode)

    # ── i18n ──────────────────────────────────────────────────────────

    def _tr(self, key: str) -> str:
        return self.facade._container.i18n.get(key)

    def retranslate(self) -> None:
        """Обновляет все видимые строки при смене языка."""
        self._lbl_profiles_header.setText(self._tr("profiles_header"))
        self.search.setPlaceholderText(self._tr("search_placeholder"))

        # Фильтр адаптеров — первый элемент
        cur_idx = self.adapter_filter.currentIndex()
        self.adapter_filter.blockSignals(True)
        self.adapter_filter.setItemText(0, self._tr("filter_all_adapters"))
        self.adapter_filter.blockSignals(False)
        self.adapter_filter.setCurrentIndex(cur_idx)

        # Кнопки панели списка
        self.btn_new.setText(self._tr("btn_new_profile"))
        self.btn_copy.setText(self._tr("btn_copy_profile"))
        self.btn_export.setText(self._tr("btn_export_profiles"))
        self.btn_import.setText(self._tr("btn_import_profiles"))
        self.btn_delete.setText(self._tr("btn_delete_profile"))

        # Кнопки редактора
        self.btn_save.setText(self._tr("btn_save_profile"))
        self.btn_apply.setText(self._tr("btn_apply_profile_form"))

        # Заголовки секций
        self._lbl_sec_basic.setText(self._tr("section_basic").upper())
        self._lbl_sec_network.setText(self._tr("section_network").upper())
        self._lbl_sec_dns.setText(self._tr("section_dns").upper())

        # Лейблы полей
        self._lbl_name.setText(self._tr("lbl_name"))
        self._lbl_adapter_field.setText(self._tr("lbl_adapter"))
        self._lbl_ip.setText(self._tr("lbl_ip"))
        self._lbl_mask.setText(self._tr("lbl_mask"))
        self._lbl_gw.setText(self._tr("lbl_gateway"))
        self._lbl_dns1.setText(self._tr("lbl_dns1"))
        self._lbl_dns2.setText(self._tr("lbl_dns2"))

        # ToggleSwitch labels
        self.dhcp_ip_cb.set_label(self._tr("dhcp_ip"))
        self.dhcp_dns_cb.set_label(self._tr("dhcp_dns"))
