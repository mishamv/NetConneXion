from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from quickip.domain.interfaces import IServiceContainer

class DashboardView(ctk.CTkFrame):
    """Settings tab view.

    Notes:
    - This view must receive ServiceContainer (i18n + settings repo), not MainWindow.
    - Theme changes are delegated to MainWindow via a callback so palette/tokens update everywhere.
    """

    def __init__(self, master, colors: dict[str, str], context: IServiceContainer):
        super().__init__(master, fg_color=colors["card"])
        self.context = context
        self.colors = colors
        self.presenter = None
        self._theme_callback = None
        self._setup_ui()

    def bind_presenter(self, presenter) -> None:
        self.presenter = presenter

    def _setup_ui(self):
        # Title
        title_label = ctk.CTkLabel(
            self,
            text=self.context.i18n.get("tab_settings"),
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["text"],
        )
        title_label.pack(pady=(20, 10), padx=20, anchor="w")
        self._title_label = title_label

        # Language Section
        lang_frame = ctk.CTkFrame(self, fg_color=self.colors["card"], border_width=1, border_color=self.colors["border"], corner_radius=10)
        lang_frame.pack(fill="x", padx=20, pady=10)
        self._lang_label = ctk.CTkLabel(lang_frame, text=self.context.i18n.get("label_language") + ":", text_color=self.colors["text"])
        self._lang_label.pack(side="left", padx=10, pady=10)

        current_lang = self.context.i18n.get_current_locale()
        self.lang_var = tk.StringVar(value=current_lang)
        self.lang_menu = ctk.CTkOptionMenu(
            lang_frame,
            values=["ru", "en"],
            variable=self.lang_var,
            command=self._on_language_change,
            fg_color=self.colors["input_bg"],
            button_color=self.colors["combo_button"],
            button_hover_color=self.colors["combo_button_hover"],
            dropdown_fg_color=self.colors["card"],
            dropdown_text_color=self.colors["text"],
            text_color=self.colors["text"],
        )
        self.lang_menu.pack(side="right", padx=10, pady=10)

        # Theme Section
        theme_frame = ctk.CTkFrame(self, fg_color=self.colors["card"], border_width=1, border_color=self.colors["border"], corner_radius=10)
        theme_frame.pack(fill="x", padx=20, pady=10)
        self._theme_label = ctk.CTkLabel(theme_frame, text=self.context.i18n.get("label_theme") + ":", text_color=self.colors["text"])
        self._theme_label.pack(side="left", padx=10, pady=10)

        # Persisted theme in app is palette-driven: light/dark.
        # Keep "System" option, but treat it as "Light" unless you decide otherwise later.
        _saved = str(self.context.settings_repo.get("ui_theme", "light")).lower()
        self.theme_var = tk.StringVar(value="Dark" if _saved == "dark" else "Light")
        self.theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            values=["Light", "Dark"],
            variable=self.theme_var,
            command=self._on_theme_change,
            fg_color=self.colors["input_bg"],
            button_color=self.colors["combo_button"],
            button_hover_color=self.colors["combo_button_hover"],
            dropdown_fg_color=self.colors["card"],
            dropdown_text_color=self.colors["text"],
            text_color=self.colors["text"],
        )
        self.theme_menu.pack(side="right", padx=10, pady=10)

    def _on_theme_change(self, value: str) -> None:
        if self.presenter is None:
            return
        self.presenter.change_theme(value)

    def _on_language_change(self, value: str) -> None:
        if self.presenter is None:
            return
        self.presenter.change_language(value)

    def show_message(self, title: str, message: str):
        from tkinter import messagebox
        messagebox.showinfo(title, message)

    def update_colors(self, colors):
        self.colors = colors
        self.configure(fg_color=colors["card"])

        # Re-theme widgets created in _setup_ui
        for frame in (getattr(self, "_lang_label", None), getattr(self, "_theme_label", None), getattr(self, "_title_label", None)):
            if frame is not None:
                try:
                    frame.configure(text_color=colors["text"])
                except Exception:
                    pass

        for opt in (getattr(self, "lang_menu", None), getattr(self, "theme_menu", None)):
            if opt is not None:
                try:
                    opt.configure(
                        fg_color=colors["input_bg"],
                        button_color=colors["combo_button"],
                        button_hover_color=colors["combo_button_hover"],
                        dropdown_fg_color=colors["card"],
                        dropdown_text_color=colors["text"],
                        text_color=colors["text"],
                    )
                except Exception:
                    pass

    # Methods that are wired by MainWindow
    def set_network_info_target(self, target):
        self._network_info_target = target

    def set_theme_toggle_callback(self, callback):
        # callback: (mode: str) -> None, where mode is "light"/"dark"
        self._theme_callback = callback

    def apply_theme(self, mode: str) -> None:
        if self._theme_callback is None:
            return
        self._theme_callback(mode)

    def refresh_home_snapshot(self):
        # no snapshot in Settings tab yet
        return
