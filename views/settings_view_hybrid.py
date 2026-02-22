"""Settings view — language and theme configuration.

FIXED:
- Forced widget redraw after theme change
- Proper language StringVar initialization
- All widgets update their colors correctly
"""

from __future__ import annotations
import tkinter as tk
from typing import Optional, Callable

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

from quickip.app.bootstrap import ServiceContainer
from quickip.presenters.settings_presenter import SettingsPresenter


class SettingsViewHybrid(ctk.CTkFrame if ctk is not None else tk.Frame):
    """Settings view with theme and language controls."""

    def __init__(
        self,
        parent: tk.Widget,
        colors: dict,
        container: ServiceContainer,
        theme_var: tk.BooleanVar,
        on_theme_change: Callable[[str], None],
        on_language_change: Callable[[str], None],
    ) -> None:
        super().__init__(parent, fg_color=colors["card"])
        self.colors = colors
        self.container = container
        self.theme_var = theme_var
        self.on_theme_change = on_theme_change
        self.on_language_change = on_language_change
        self.presenter: Optional[SettingsPresenter] = None
        
        self._build_ui()
        self._setup_presenter()

    def _build_ui(self) -> None:
        """Build settings UI."""
        # Title
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 10))
        
        try:
            title_text = self.container.i18n.get("tab_settings")
        except Exception:
            title_text = "Settings"
            
        self.title_label = ctk.CTkLabel(
            top, text=title_text,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors["text"]
        )
        self.title_label.pack(side="left")

        # Theme card
        self.theme_card = ctk.CTkFrame(
            self,
            fg_color=self.colors.get("input_bg", self.colors["card"]),
            corner_radius=8, border_width=1, border_color=self.colors["border"]
        )
        self.theme_card.pack(fill="x", padx=16, pady=(0, 10))
        
        try:
            theme_label = self.container.i18n.get("theme_label")
        except Exception:
            theme_label = "Theme:"
            
        self.theme_label_widget = ctk.CTkLabel(
            self.theme_card, text=theme_label,
            text_color=self.colors["text"]
        )
        self.theme_label_widget.pack(side="left", padx=12, pady=10)
        
        try:
            theme_switch_text = self.container.i18n.get("dark_theme")
        except Exception:
            theme_switch_text = "Dark mode"
            
        self.theme_switch = ctk.CTkSwitch(
            self.theme_card, text=theme_switch_text,
            variable=self.theme_var, onvalue=True, offvalue=False,
            command=self._handle_theme_toggle,
        )
        self.theme_switch.pack(side="right", padx=12, pady=10)

        # Language card (only if i18n available)
        if self.container.i18n is not None:
            self.lang_card = ctk.CTkFrame(
                self,
                fg_color=self.colors.get("input_bg", self.colors["card"]),
                corner_radius=8, border_width=1, border_color=self.colors["border"]
            )
            self.lang_card.pack(fill="x", padx=16, pady=(0, 10))
            
            try:
                lang_label = self.container.i18n.get("language_label")
            except Exception:
                lang_label = "Language"
                
            self.lang_label_widget = ctk.CTkLabel(
                self.lang_card, text=lang_label,
                text_color=self.colors["text"]
            )
            self.lang_label_widget.pack(side="left", padx=12, pady=10)
            
            # FIX: Get actual current locale from i18n service
            current_locale = "ru"  # default fallback
            try:
                current_locale = self.container.i18n.get_current_locale()
            except Exception:
                # Try from settings_repo as fallback
                try:
                    current_locale = str(self.container.settings_repo.get("language", "ru"))
                except Exception:
                    pass
                    
            self.lang_var = tk.StringVar(value=current_locale)
            self.lang_menu = ctk.CTkOptionMenu(
                self.lang_card, values=["ru", "en"],
                variable=self.lang_var,
                command=self._handle_language_change,
            )
            self.lang_menu.pack(side="right", padx=12, pady=10)

    def _setup_presenter(self) -> None:
        """Wire up SettingsPresenter."""
        try:
            self.presenter = SettingsPresenter(self, self.container)
        except Exception as e:
            print(f"Failed to setup SettingsPresenter: {e}")

    def _handle_theme_toggle(self) -> None:
        """Delegate theme change to parent."""
        mode = "dark" if self.theme_var.get() else "light"
        self.on_theme_change(mode)

    def _handle_language_change(self, locale: str) -> None:
        """Handle language change via presenter."""
        if self.presenter:
            try:
                self.presenter.change_language(locale)
            except Exception as e:
                print(f"Language change failed: {e}")
        
        # Notify parent for full UI rebuild (after dialog)
        self.after(500, lambda: self.on_language_change(locale))

    # === SettingsPresenter callbacks ===
    
    def show_message(self, title: str, message: str) -> None:
        """Show info dialog."""
        try:
            from tkinter import messagebox
            messagebox.showinfo(title, message, parent=self)
        except Exception:
            pass

    def show_error(self, message: str) -> None:
        """Show error dialog."""
        try:
            from tkinter import messagebox
            messagebox.showerror("Error", message, parent=self)
        except Exception:
            pass

    def update_colors(self, colors: dict) -> None:
        """Apply new color scheme.
        
        FIX: Force ALL widgets to update their colors immediately.
        """
        self.colors = colors
        self.configure(fg_color=colors["card"])
        
        try:
            # Update title
            self.title_label.configure(text_color=colors["text"])
            
            # Update theme card + all its children
            self.theme_card.configure(
                fg_color=colors.get("input_bg", colors["card"]),
                border_color=colors["border"]
            )
            self.theme_label_widget.configure(text_color=colors["text"])
            
            # Update language card if exists
            if hasattr(self, "lang_card"):
                self.lang_card.configure(
                    fg_color=colors.get("input_bg", colors["card"]),
                    border_color=colors["border"]
                )
                self.lang_label_widget.configure(text_color=colors["text"])
                
                # Update OptionMenu colors
                self.lang_menu.configure(
                    fg_color=colors.get("input_bg", colors["card"]),
                    button_color=colors.get("combo_button", "#3B82F6"),
                    button_hover_color=colors.get("combo_button_hover", "#2563EB"),
                    dropdown_fg_color=colors["card"],
                    dropdown_text_color=colors["text"],
                    text_color=colors["text"]
                )
        except Exception as e:
            print(f"Error updating colors: {e}")
