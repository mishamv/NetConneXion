"""Dashboard view — hybrid implementation for migration phase.

FIXED:
- Force complete widget color update on theme change
- All widgets properly redrawn with correct theme colors
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


class DashboardViewHybrid(ctk.CTkFrame if ctk is not None else tk.Frame):
    """Dashboard view with presenter integration."""

    def __init__(
        self,
        parent: tk.Widget,
        colors: dict,
        container: ServiceContainer,
        on_theme_change: Callable[[str], None],
    ) -> None:
        super().__init__(parent, fg_color=colors["card"])
        self.colors = colors
        self.container = container
        self.on_theme_change = on_theme_change
        self.presenter: Optional[SettingsPresenter] = None
        
        theme_setting = str(container.settings_repo.get("ui_theme", "light")).lower()
        self.theme_var = tk.BooleanVar(value=theme_setting == "dark")
        
        self._build_ui()
        self._setup_presenter()

    def _build_ui(self) -> None:
        """Build dashboard UI widgets."""
        # Title + theme toggle
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(fill="x", padx=16, pady=(16, 10))
        
        try:
            title_text = self.container.i18n.get("tab_dashboard")
        except Exception:
            title_text = "Dashboard"
            
        self.title_label = ctk.CTkLabel(
            self.top_frame, text=title_text,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors["text"],
        )
        self.title_label.pack(side="left")
        
        try:
            theme_text = self.container.i18n.get("dark_theme")
        except Exception:
            theme_text = "Dark mode"
            
        self.theme_switch = ctk.CTkSwitch(
            self.top_frame, text=theme_text,
            variable=self.theme_var,
            onvalue=True, offvalue=False,
            command=self._handle_theme_toggle,
        )
        self.theme_switch.pack(side="right")
        
        # Network snapshot textbox
        self.snapshot_text = ctk.CTkTextbox(
            self, state="normal",
            fg_color=self.colors.get("input_bg", self.colors["card"]),
            text_color=self.colors.get("text", "#000000"),
            border_color=self.colors.get("border", "#555555"),
            border_width=1
        )
        self.snapshot_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.snapshot_text.insert("1.0", "Loading network information...")

    def _setup_presenter(self) -> None:
        """Wire up SettingsPresenter."""
        try:
            self.presenter = SettingsPresenter(self, self.container)
            self.presenter.refresh_home_snapshot()
        except Exception as e:
            error_msg = f"Failed to initialize presenter: {e}\n\nPlease check logs."
            self.snapshot_text.delete("1.0", "end")
            self.snapshot_text.insert("1.0", error_msg)

    def _handle_theme_toggle(self) -> None:
        """Delegate theme change to parent."""
        mode = "dark" if self.theme_var.get() else "light"
        self.on_theme_change(mode)

    # === SettingsPresenter callbacks ===
    
    def set_network_snapshot(self, text: str) -> None:
        """Update network snapshot display."""
        try:
            self.snapshot_text.delete("1.0", "end")
            self.snapshot_text.insert("1.0", text)
        except Exception:
            pass

    def show_message(self, title: str, message: str) -> None:
        """Show message dialog."""
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
        """Apply new color scheme after theme change.
        
        FIX: Update ALL widgets with correct colors for light/dark theme.
        """
        self.colors = colors
        self.configure(fg_color=colors["card"])
        
        try:
            # Update title label
            self.title_label.configure(text_color=colors["text"])
            
            # Update textbox with proper theme colors
            self.snapshot_text.configure(
                fg_color=colors.get("input_bg", colors["card"]),
                text_color=colors.get("text", "#000000"),
                border_color=colors.get("border", "#555555")
            )
        except Exception as e:
            print(f"Error updating dashboard colors: {e}")
