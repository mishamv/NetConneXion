"""Shared CTk dialog helpers used across all views."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

if TYPE_CHECKING:
    pass


def center_dialog(parent: tk.Widget, dialog: tk.Widget, width: int, height: int) -> None:
    """Centre *dialog* over *parent*."""
    parent.update_idletasks()
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")


def show_message(parent: tk.Widget, title: str, message: str, colors: dict) -> None:
    """Simple OK dialog."""
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry("420x180")
    dialog.transient(parent)
    dialog.grab_set()
    ctk.CTkLabel(dialog, text=message, wraplength=380, justify="left").pack(
        fill="both", expand=True, padx=16, pady=16
    )
    ctk.CTkButton(dialog, text="OK", command=dialog.destroy).pack(pady=(0, 16))
    center_dialog(parent, dialog, 420, 180)


def ask_yes_no(parent: tk.Widget, title: str, message: str, colors: dict) -> bool:
    """Yes/No dialog; returns True if user clicked Yes."""
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry("460x210")
    dialog.transient(parent)
    dialog.grab_set()
    result = {"value": False}

    ctk.CTkLabel(dialog, text=message, wraplength=420, justify="left").pack(
        fill="both", expand=True, padx=16, pady=(16, 8)
    )
    bar = ctk.CTkFrame(dialog, fg_color="transparent")
    bar.pack(fill="x", padx=16, pady=(0, 16))
    ctk.CTkButton(
        bar, text="Да", width=110,
        command=lambda: (result.__setitem__("value", True), dialog.destroy()),
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        bar, text="Нет", width=110,
        fg_color=colors["input_bg"], text_color=colors["text"],
        border_width=1, border_color=colors["border"],
        command=dialog.destroy,
    ).pack(side="right")

    center_dialog(parent, dialog, 460, 210)
    dialog.wait_window()
    return result["value"]


def ask_rename_action(
    parent: tk.Widget, old_name: str, new_name: str, colors: dict
) -> str:
    """Three-button rename dialog; returns 'rename' | 'save_as_new' | 'cancel'."""
    dialog = ctk.CTkToplevel(parent)
    dialog.title("Переименование профиля")
    dialog.geometry("560x240")
    dialog.transient(parent)
    dialog.grab_set()
    result = {"value": "cancel"}

    ctk.CTkLabel(
        dialog,
        text=f"Переименовать текущий профиль \'{old_name}\' в \'{new_name}\'?\nВыберите действие:",
        wraplength=520, justify="left",
    ).pack(fill="both", expand=True, padx=16, pady=(16, 8))

    bar = ctk.CTkFrame(dialog, fg_color="transparent")
    bar.pack(fill="x", padx=16, pady=(0, 16))

    ctk.CTkButton(
        bar, text="Переименовать", width=130,
        command=lambda: (result.__setitem__("value", "rename"), dialog.destroy()),
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        bar, text="Сохранить как новый", width=170,
        fg_color=colors["input_bg"], text_color=colors["text"],
        border_width=1, border_color=colors["border"],
        command=lambda: (result.__setitem__("value", "save_as_new"), dialog.destroy()),
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        bar, text="Отмена", width=110,
        fg_color=colors["input_bg"], text_color=colors["text"],
        border_width=1, border_color=colors["border"],
        command=dialog.destroy,
    ).pack(side="right")

    center_dialog(parent, dialog, 560, 240)
    dialog.wait_window()
    return result["value"]
