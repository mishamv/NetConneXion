"""Tools feature — console panel.

Lets the user select a whitelisted diagnostic tool (ping, tracert, …),
optionally pick a preset target, type a custom target, and run the
command — output is shown in a scrollable read-only text box.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import List, Optional, TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from quickip.features.tools.presenter import ToolsPresenter

logger = logging.getLogger(__name__)


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


class ConsolePanel(ctk.CTkFrame):
    """Network console: tool picker + target entry + output box."""

    def __init__(self, parent, colors: dict, presenter: "ToolsPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._colors = colors
        self._presenter = presenter
        self._running = False
        self._build()

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self._colors
        tools = self._presenter.get_console_tools()

        # ── Top controls ──────────────────────────────────────────
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=8, pady=(8, 4))
        ctrl.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            ctrl, text="Инструмент:", font=_f(12), text_color=c["text"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))

        self._tool_var = tk.StringVar(value=tools[0] if tools else "ping")
        self._tool_menu = ctk.CTkOptionMenu(
            ctrl,
            values=tools,
            variable=self._tool_var,
            command=self._on_tool_change,
            width=130, height=32, font=_f(12),
            fg_color=c["input_bg"], text_color=c["text"],
            button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
        )
        self._tool_menu.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(
            ctrl, text="Пресет:", font=_f(12), text_color=c["text"],
        ).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(6, 0))

        self._preset_var = tk.StringVar(value="Вручную")
        self._preset_menu = ctk.CTkOptionMenu(
            ctrl,
            values=["Вручную"],
            variable=self._preset_var,
            command=self._on_preset_change,
            width=180, height=32, font=_f(12),
            fg_color=c["input_bg"], text_color=c["text"],
            button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
        )
        self._preset_menu.grid(row=1, column=1, sticky="w", pady=(6, 0))

        ctk.CTkLabel(
            ctrl, text="Цель:", font=_f(12), text_color=c["text"],
        ).grid(row=2, column=0, sticky="w", padx=(0, 6), pady=(6, 0))

        self._target_var = tk.StringVar()
        self._target_entry = ctk.CTkEntry(
            ctrl, textvariable=self._target_var,
            width=220, height=32, font=_f(12),
            fg_color=c["input_bg"], text_color=c["text"],
            border_color=c["border"], placeholder_text="IP или hostname",
        )
        self._target_entry.grid(row=2, column=1, sticky="w", pady=(6, 0))
        self._target_entry.bind("<Return>", lambda _: self._run())

        # ── Run / Clear buttons ───────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(4, 4))

        self._run_btn = ctk.CTkButton(
            btn_row, text="▶ Выполнить", width=130, height=32, font=_f(12),
            fg_color=c["primary"], hover_color=c["hover"], text_color="#FFFFFF",
            command=self._run,
        )
        self._run_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Очистить", width=90, height=32, font=_f(12),
            fg_color=c["card"], hover_color=c["border"], text_color=c["text"],
            border_width=1, border_color=c["border"],
            command=self._clear,
        ).pack(side="left")

        self._status_lbl = ctk.CTkLabel(
            btn_row, text="", font=_f(11),
            text_color=c.get("text_secondary", c["text"]),
        )
        self._status_lbl.pack(side="right")

        # ── Output box ────────────────────────────────────────────
        self._output = ctk.CTkTextbox(
            self, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=c["list_bg"], text_color=c["list_text"],
            border_color=c["border"], border_width=1,
            wrap="none", state="disabled",
        )
        self._output.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Populate presets for initial tool
        self._on_tool_change(self._tool_var.get())

    # ── Handlers ──────────────────────────────────────────────────

    def _on_tool_change(self, tool: str) -> None:
        presets = self._presenter.get_console_presets(tool)
        options = ["Вручную"] + list(presets.keys())
        self._preset_menu.configure(values=options)
        self._preset_var.set("Вручную")
        self._target_var.set("")

    def _on_preset_change(self, label: str) -> None:
        if label == "Вручную":
            self._target_var.set("")
            return
        presets = self._presenter.get_console_presets(self._tool_var.get())
        self._target_var.set(presets.get(label, ""))

    def _run(self) -> None:
        if self._running:
            return
        tool = self._tool_var.get()
        target = self._target_var.get().strip()
        self._running = True
        self._run_btn.configure(state="disabled", text="⏳ Выполнение…")
        self._status_lbl.configure(text="")
        threading.Thread(target=self._execute, args=(tool, target), daemon=True).start()

    def _execute(self, tool: str, target: str) -> None:
        try:
            result = self._presenter.run_console(tool, target)
            self.after(0, self._show_output, result.output, result.success)
        except ValueError as exc:
            self.after(0, self._show_output, f"Ошибка: {exc}", False)
        except Exception as exc:
            logger.exception("ConsolePanel execute error")
            self.after(0, self._show_output, f"Ошибка: {exc}", False)
        finally:
            self.after(0, self._done)

    def _show_output(self, text: str, success: bool) -> None:
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.insert("end", text)
        self._output.configure(state="disabled")
        color = self._colors["text"] if success else "#EF4444"
        self._status_lbl.configure(
            text="Успешно" if success else "Ошибка", text_color=color,
        )

    def _done(self) -> None:
        self._running = False
        self._run_btn.configure(state="normal", text="▶ Выполнить")

    def _clear(self) -> None:
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.configure(state="disabled")
        self._status_lbl.configure(text="")

    # ── Colors ────────────────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        self._colors = colors
