"""Tools view — network diagnostic tools.

FIXED:
- Removed TYPE_CHECKING to avoid import errors
- Added i18n fallbacks
"""

from __future__ import annotations
import tkinter as tk
from typing import Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

# Direct imports
from quickip.app.bootstrap import ServiceContainer
from quickip.presenters.tools_presenter import ToolsPresenter


class ToolsViewHybrid(ctk.CTkFrame if ctk is not None else tk.Frame):
    """Tools view with presenter integration."""

    def __init__(
        self,
        parent: tk.Widget,
        colors: dict,
        container: ServiceContainer,
    ) -> None:
        super().__init__(parent, fg_color=colors["card"])
        self.colors = colors
        self.container = container
        self.presenter: Optional[ToolsPresenter] = None
        
        self._build_ui()
        self._setup_presenter()

    def _build_ui(self) -> None:
        """Build tools UI."""
        # Title with i18n fallback
        try:
            title_text = self.container.i18n.get("tools_title")
        except Exception:
            title_text = "Network tools"
            
        ctk.CTkLabel(
            self, text=title_text,
            text_color=self.colors["text"],
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", padx=16, pady=(16, 8))

        # Target input
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(0, 8))
        
        ctk.CTkLabel(top, text="Host/DNS", text_color=self.colors["text"]).pack(
            side="left", padx=(0, 8)
        )
        
        self.target_entry = ctk.CTkEntry(
            top, height=34, corner_radius=6,
            border_color=self.colors["border"],
            fg_color=self.colors["input_bg"],
            text_color=self.colors["text"]
        )
        self.target_entry.pack(side="left", fill="x", expand=True)
        self.target_entry.insert(0, "8.8.8.8")

        # Tool buttons
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=16, pady=(0, 8))
        
        tools = [
            ("Ping", "ping"),
            ("DNS check", "dns"),
            ("Netstat", "netstat"),
            ("Flush DNS", "flushdns"),
            ("TCP/IP reset", "tcpreset")
        ]
        
        for text, tool_id in tools:
            ctk.CTkButton(
                buttons, text=text, height=34,
                command=lambda t=tool_id: self._handle_tool_click(t)
            ).pack(side="left", padx=(0, 6))

        # Output textbox
        self.output_text = ctk.CTkTextbox(
            self, font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.output_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def _setup_presenter(self) -> None:
        """Wire up ToolsPresenter."""
        try:
            self.presenter = ToolsPresenter(self.container, self)
        except Exception as e:
            print(f"Failed to setup ToolsPresenter: {e}")

    def _handle_tool_click(self, tool: str) -> None:
        """Delegate tool execution to presenter."""
        if self.presenter:
            try:
                self.presenter.run_tool(tool)
            except Exception as e:
                self.show_tool_output(f"Error: {e}")

    # === ToolsPresenter callbacks ===
    
    def show_tool_output(self, text: str) -> None:
        """Display command output."""
        try:
            self.output_text.delete("1.0", "end")
            self.output_text.insert("1.0", text)
        except Exception:
            pass

    def ask_yes_no(self, title: str, message: str) -> bool:
        """Show confirmation dialog."""
        try:
            from tkinter import messagebox
            return messagebox.askyesno(title, message, parent=self)
        except Exception:
            return False

    def get_tool_target(self) -> str:
        """Return target host/IP from input field."""
        try:
            return self.target_entry.get().strip()
        except Exception:
            return "8.8.8.8"

    def update_colors(self, colors: dict) -> None:
        """Apply new color scheme."""
        self.colors = colors
        self.configure(fg_color=colors["card"])
        
        try:
            self.target_entry.configure(
                border_color=colors["border"],
                fg_color=colors["input_bg"],
                text_color=colors["text"]
            )
            self.output_text.configure(
                fg_color=colors.get("input_bg", colors["card"]),
                text_color=colors.get("text", "#000000")
            )
        except Exception:
            pass
