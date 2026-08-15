"""Central colour registry for the Qt UI.

EN: All QSS and custom-painted widget colours live in this module.
RU: Все цвета QSS и вручную рисуемых виджетов находятся в этом модуле.
"""

from __future__ import annotations

from typing import Final

SEMANTIC_COLORS: Final[dict[str, str]] = {
    # EN: Theme-independent feedback and state colours.
    # RU: Независимые от темы цвета обратной связи и состояний.
    # EN/RU token map:
    # ACCENT — primary accent / основной акцент.
    # STATUS_* — operation result / результат операции.
    # TEXT_MUTED* — secondary text / вторичный текст.
    # ELEVATION_* — administrator banner / баннер администратора.
    # LIGHT_* — light-theme selection helpers / выделение в светлой теме.
    "ACCENT": "#6C7BFF",
    "STATUS_SUCCESS": "#22C55E",
    "STATUS_WARNING": "#F59E0B",
    "STATUS_ERROR": "#EF4444",
    "TEXT_MUTED": "#94A3B8",
    "TEXT_MUTED_STRONG": "#64748B",
    "ELEVATION_BG": "#7C5800",
    "ELEVATION_BG_HOVER": "#A07000",
    "ELEVATION_TEXT": "#FFE08A",
    "LIGHT_SELECTION_BG": "#F0F4FF",
    "LIGHT_SELECTION_BORDER": "#C7D2FE",
    "LIGHT_ICON_BG": "#EEF4FF",
    "LIGHT_CONNECTED": "#6366F1",
}

LIGHT_COLORS: Final[dict[str, str]] = {
    # EN: Custom-painted controls, graph canvas and signal cards.
    # RU: Вручную рисуемые переключатели, холст графика и карточки сигнала.
    "LIGHT_CUSTOM_TOGGLE_BORDER": "#CBD5E1",
    "LIGHT_CUSTOM_TOGGLE_KNOB": "#FFFFFF",
    "LIGHT_CUSTOM_TOGGLE_OFF": "#E2E8F0",
    "LIGHT_CUSTOM_TOGGLE_ON": "#6366F1",
    "LIGHT_CUSTOM_TOGGLE_TEXT": "#64748B",
    "LIGHT_CUSTOM_GRAPH_BG": "#FFFFFF",
    "LIGHT_CUSTOM_GRAPH_GRID": "#000000",
    "LIGHT_CUSTOM_GRAPH_TEXT": "#64748B",
    "LIGHT_CUSTOM_SIGNAL_CARD_BG": "#EEF2FF",
    "LIGHT_CUSTOM_SIGNAL_CARD_KEY": "#6366F1",
    "LIGHT_CUSTOM_SIGNAL_CARD_VALUE": "#1E293B",
    "LIGHT_CUSTOM_PROFILE_ICON": "#4F46E5",
    "LIGHT_CUSTOM_CONNECTED_ROW": "#6366F1",
    "LIGHT_CUSTOM_TOPBAR_PLACEHOLDER": "#1E293B",
    "LIGHT_TEXT_PRIMARY": "#1E293B",
    "LIGHT_STATUS_SUCCESS": "#22C55E",
    "LIGHT_TEXT_STRONG": "#334155",
    "LIGHT_ACCENT_DEEP": "#3730A3",
    "LIGHT_ACCENT_PRESSED": "#4338CA",
    "LIGHT_TEXT_SECONDARY": "#475569",
    "LIGHT_ACCENT": "#4F46E5",
    "LIGHT_ACCENT_HOVER": "#6366F1",
    "LIGHT_TEXT_FAINT": "#64748B",
    "LIGHT_TEXT_MUTED": "#94A3B8",
    "LIGHT_SCROLL_HANDLE": "#9FA8DA",
    "LIGHT_ACCENT_TEXT": "#A5B4FC",
    "LIGHT_STATUS_ERROR_STRONG": "#B91C1C",
    "LIGHT_CONTROL_BORDER": "#C5CAE9",
    "LIGHT_CARD_BORDER": "#C7D2FE",
    "LIGHT_BORDER_SUBTLE": "#CBD5E1",
    "LIGHT_STATE_HOVER_BG": "#D1D5F0",
    "LIGHT_STATUS_ERROR": "#DC2626",
    "LIGHT_SECTION_DIVIDER": "#DDE2F0",
    "LIGHT_STATE_ACTIVE_BG": "#E0E7FF",
    "LIGHT_BORDER_DEFAULT": "#E2E8F0",
    "LIGHT_WIFI_TABLE_BG": "#E8EAF6",
    "LIGHT_DATA_SURFACE": "#E8EDF5",
    "LIGHT_INPUT_BG": "#EEF2FF",
    "LIGHT_SIDE_SURFACE": "#F0F4FA",
    "LIGHT_PROFILE_CARD_BG": "#F0F4FF",
    "LIGHT_PANEL_BG": "#F1F5F9",
    "LIGHT_APP_BG": "#F8FAFC",
    "LIGHT_PAGE_CANVAS": "#FAFAFE",
    "LIGHT_ERROR_TEXT": "#FCA5A5",
    "LIGHT_ERROR_BORDER": "#FECACA",
    "LIGHT_ERROR_BG_HOVER": "#FEE2E2",
    "LIGHT_ERROR_BG": "#FEF2F2",
    "LIGHT_CARD_SURFACE": "#FFFFFF",
    "LIGHT_TEXT_ON_ACCENT": "#FFFFFF",
    "LIGHT_RGBA_15_23_42_0_12": "rgba(15, 23, 42, 0.12)",
    "LIGHT_RGBA_15_23_42_0_22": "rgba(15, 23, 42, 0.22)",
    "LIGHT_RGBA_99_102_241_0_12": "rgba(99, 102, 241, 0.12)",
}

DARK_COLORS: Final[dict[str, str]] = {
    # EN: Approved dark-theme palette from the Profiles and Wi-Fi mock-ups.
    # RU: Утверждённая палитра тёмной темы из макетов «Профили» и «Wi-Fi».
    #
    # EN: Custom-painted widgets use the same surfaces as the QSS theme.
    # RU: Вручную рисуемые виджеты используют те же поверхности, что и QSS.
    "DARK_CUSTOM_BACKDROP": "#11151D",
    "DARK_CUSTOM_GRAPH_BG": "#1B2230",
    "DARK_CUSTOM_GRAPH_GRID": "#303B50",
    "DARK_CUSTOM_GRAPH_TEXT": "#B4BED2",
    "DARK_CUSTOM_SIGNAL_CARD_BG": "rgba(255,255,255,0.06)",
    "DARK_CUSTOM_SIGNAL_CARD_KEY": "#B4BED2",
    "DARK_CUSTOM_SIGNAL_CARD_VALUE": "#EEF1F8",
    "DARK_CUSTOM_PROFILE_ICON": "#B4BED2",
    "DARK_CUSTOM_TOPBAR_PLACEHOLDER": "#EEF1F8",
    "DARK_CUSTOM_TREE_HOVER": "rgba(116,124,255,0.12)",
    "DARK_CUSTOM_TREE_HOVER_TEXT": "#EEF1F8",
    "DARK_CUSTOM_TREE_SELECTED": "#6C75F6",
    "DARK_CUSTOM_TREE_SELECTED_TEXT": "#FFFFFF",
    "DARK_CUSTOM_TOGGLE_BORDER": "#303B50",
    "DARK_CUSTOM_TOGGLE_KNOB": "#FFFFFF",
    "DARK_CUSTOM_TOGGLE_OFF": "#303B50",
    "DARK_CUSTOM_TOGGLE_ON": "#6C75F6",
    "DARK_CUSTOM_TOGGLE_TEXT": "#B4BED2",
    # EN: Semantic QSS tokens grouped by role instead of literal hex names.
    # RU: Смысловые токены QSS сгруппированы по роли, а не по HEX-значению.
    "DARK_PAGE_CANVAS": "#11151D",
    "DARK_EDITOR_INPUT_BG": "#20293A",
    "DARK_APP_BG": "#11151D",
    "DARK_CONTROL_DISABLED_BG": "#181E29",
    "DARK_SIDEBAR_MATCH_BG": "#151A24",
    "DARK_HEADER_BG": "#11151D",
    "DARK_SIDE_SURFACE": "#181E29",
    "DARK_SIDEBAR_BG": "#151A24",
    "DARK_PANEL_BG": "#181E29",
    "DARK_DATA_SURFACE": "#1B2230",
    "DARK_RESULT_SURFACE": "#1B2230",
    "DARK_CARD_SURFACE": "#1B2230",
    "DARK_BUTTON_BG": "#1B2230",
    "DARK_POPUP_BG": "#20293A",
    "DARK_INPUT_BG": "#20293A",
    "DARK_SURFACE_RAISED": "#1B2230",
    # EN: Page-specific surfaces keep Profiles and Wi-Fi visually layered
    # without changing the denser Tools workspace.
    # RU: Отдельные поверхности сохраняют иерархию Профилей и Wi-Fi,
    # не изменяя более плотное оформление раздела Инструменты.
    "DARK_PROFILE_CARD_BG": "#161C27",
    "DARK_PROFILE_INPUT_BG": "#1C2534",
    "DARK_WIFI_TABLE_BG": "#151A24",
    "DARK_WIFI_ROW_ALT_BG": "#181E29",
    "DARK_WIFI_ROW_HOVER_BG": "#20293A",
    "DARK_BORDER_SHELL": "#252E3E",
    # EN: Neutral divider used below card headings.
    # RU: Нейтральный разделитель под заголовками карточек.
    "DARK_SECTION_DIVIDER": "#303B50",
    "DARK_CONTROL_FOCUS_BG": "#29334D",
    "DARK_BUTTON_HOVER_BG": "#252F42",
    "DARK_CONTROL_DISABLED_BORDER": "#252E3E",
    "DARK_STATE_HOVER_BG": "#252F42",
    "DARK_STATE_ACTIVE_MATCH_BG": "#29334D",
    "DARK_CARD_BORDER": "#303B50",
    "DARK_PANEL_MATCH_BORDER": "#303B50",
    "DARK_BORDER_SUBTLE": "#252E3E",
    "DARK_STATE_ACTIVE_BG": "#29334D",
    "DARK_CONTROL_BORDER": "#303B50",
    "DARK_BORDER_DEFAULT": "#303B50",
    "DARK_LOGO_GREEN": "#3DDC84",
    "DARK_SCROLL_HANDLE": "#44516A",
    "DARK_STATUS_SUCCESS": "#3DDC84",
    "DARK_LOGO_BLUE": "#5E7CFF",
    "DARK_TEXT_FAINT": "#818DA8",
    "DARK_ACCENT_PRESSED": "#5962DE",
    "DARK_TEXT_DISABLED": "#818DA8",
    "DARK_ACCENT": "#6C75F6",
    "DARK_TEXT_MUTED": "#B4BED2",
    "DARK_ACCENT_HOVER": "#7E86FF",
    "DARK_TAB_ACTIVE_TEXT": "#9299FF",
    "DARK_ACCENT_TEXT": "#AEB3FF",
    "DARK_TEXT_SECONDARY": "#D6DCE9",
    "DARK_TEXT_PRIMARY": "#EEF1F8",
    "DARK_STATUS_ERROR": "#FF6678",
    "DARK_STATUS_ERROR_SOFT": "#FF7D8C",
    "DARK_STATUS_WARNING": "#F5B942",
    "DARK_ERROR_TEXT": "#fca5a5",
    "DARK_TEXT_ON_ACCENT": "#ffffff",
    "DARK_ERROR_BG": "rgba(239, 68, 68, 0.12)",
    "DARK_ERROR_BG_HOVER": "rgba(239, 68, 68, 0.22)",
    "DARK_ERROR_BORDER_STRONG": "rgba(239, 68, 68, 0.30)",
    "DARK_ERROR_BORDER": "rgba(239, 68, 68, 0.50)",
    "DARK_HOVER_OVERLAY": "rgba(255, 255, 255, 0.035)",
    "DARK_HOVER_OVERLAY_STRONG": "rgba(255, 255, 255, 0.055)",
}

PALETTES: Final[dict[str, dict[str, str]]] = {
    "light": LIGHT_COLORS,
    "dark": DARK_COLORS,
}


def palette(theme_mode: str) -> dict[str, str]:
    """Return the complete colour dictionary for a theme."""
    return PALETTES["dark" if str(theme_mode).lower() == "dark" else "light"]


def color(theme_mode: str, token: str) -> str:
    """Return one colour token, raising a clear error if it is unknown."""
    return palette(theme_mode)[token]


def semantic_color(token: str) -> str:
    """Return a theme-independent semantic colour."""
    return SEMANTIC_COLORS[token]


def inject_qss_colors(qss: str) -> str:
    """Replace every light and dark colour placeholder in loaded QSS."""
    for values in PALETTES.values():
        for token, value in values.items():
            qss = qss.replace("{" + token + "}", value)
    return qss
