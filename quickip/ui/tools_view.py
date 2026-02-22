"""Tools view – CTk widgets implementing ToolsView protocol."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

from quickip.ui.dialogs import ask_yes_no

if TYPE_CHECKING:
    from quickip.presenters.tools_presenter import ToolsPresenter


class ToolsView:
    """
    Builds the network tools panel and implements the
    :class:`ToolsPresenter.ToolsView` protocol.
    """

    def __init__(self, parent: tk.Widget, colors: dict, root: tk.Widget) -> None:
        self.parent = parent
        self.colors = colors
        self.root = root
        self.presenter: ToolsPresenter | None = None
        self._build(parent)

    def bind_presenter(self, presenter: "ToolsPresenter") -> None:
        self.presenter = presenter

    # ── Build ────────────────────────────────────────────────────

    def _build(self, parent: tk.Widget) -> None:
        ctk.CTkLabel(parent, text="Сетевые инструменты", text_color=self.colors["text"],
                      font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(top, text="Host/DNS", text_color=self.colors["text"]).pack(side="left", padx=(0, 8))
        self.target_entry = ctk.CTkEntry(
            top, height=34, corner_radius=6,
            border_color=self.colors["border"], fg_color=self.colors["input_bg"],
            text_color=self.colors["text"],
        )
        self.target_entry.pack(side="left", fill="x", expand=True)
        self.target_entry.insert(0, "8.8.8.8")

        buttons = ctk.CTkFrame(parent, fg_color="transparent")
        buttons.pack(fill="x", padx=16, pady=(0, 8))
        for text, tool in [("Ping", "ping"), ("DNS check", "dns"), ("Netstat", "netstat"),
                           ("Flush DNS", "flushdns"), ("TCP/IP reset", "tcpreset")]:
            ctk.CTkButton(buttons, text=text, height=34,
                          command=lambda t=tool: self._on_run(t)).pack(side="left", padx=(0, 6))

        self.output_text = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=12))
        self.output_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    # ── Protocol implementation ──────────────────────────────────

    def show_tool_output(self, text: str) -> None:
        self.output_text.delete("1.0", "end")
        self.output_text.insert("end", text)

    def ask_yes_no(self, title: str, message: str) -> bool:
        return ask_yes_no(self.root, title, message, self.colors)

    def get_tool_target(self) -> str:
        return self.target_entry.get()

    # ── Event handlers ───────────────────────────────────────────

    def _on_run(self, tool: str) -> None:
        if self.presenter:
            self.presenter.run_tool(tool)

    def update_colors(self, colors: dict) -> None:
        self.colors = colors
