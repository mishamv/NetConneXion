"""Shared CTk dialog helpers — compact, card-style, consistent.

All dialogs:
  • Centered over parent
  • Non-resizable
  • Modal (grab_set + wait_window)
  • Button order (left → right): primary action first, destructive last
  • Buttons right-aligned inside dialog

Also exports:
  bind_entry_menu(entry, colors)  — attaches right-click Copy/Cut/Paste menu.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk


# ── Internal helpers ──────────────────────────────────────────────────────────

def _font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


def _place(parent: tk.Widget, dialog: tk.Widget, w: int, h: int) -> None:
    """Center *dialog* (w×h) over *parent*, then fix the size."""
    parent.update_idletasks()
    px = parent.winfo_rootx() + parent.winfo_width() // 2
    py = parent.winfo_rooty() + parent.winfo_height() // 2
    dialog.geometry(f"{w}x{h}+{px - w // 2}+{py - h // 2}")
    dialog.minsize(w, h)
    dialog.maxsize(w, h)


def _base(
    parent: tk.Widget,
    title: str,
    colors: dict,
    w: int,
    h: int,
) -> tuple[ctk.CTkToplevel, ctk.CTkFrame, ctk.CTkFrame]:
    """Build and return (dialog, body_frame, btn_frame)."""
    c = colors
    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.configure(fg_color=c["bg"])
    dlg.attributes("-topmost", True)

    # ── Outer card ────────────────────────────────────────────────
    card = ctk.CTkFrame(
        dlg,
        fg_color=c["card"],
        border_width=1,
        border_color=c["border"],
        corner_radius=10,
    )
    card.pack(fill="both", expand=True, padx=10, pady=10)
    card.grid_columnconfigure(0, weight=1)
    card.grid_rowconfigure(1, weight=1)

    # ── Body (message area) ───────────────────────────────────────
    body = ctk.CTkFrame(card, fg_color="transparent")
    body.grid(row=0, column=0, sticky="nsew", padx=20, pady=(18, 8))

    # ── Button row ────────────────────────────────────────────────
    sep = ctk.CTkFrame(card, fg_color=c["border"], height=1)
    sep.grid(row=1, column=0, sticky="ew", padx=0)

    btn_row = ctk.CTkFrame(card, fg_color="transparent")
    btn_row.grid(row=2, column=0, sticky="ew", padx=16, pady=12)

    _place(parent, dlg, w, h)
    return dlg, body, btn_row


def _btn_primary(parent, text: str, colors: dict, cmd) -> ctk.CTkButton:
    c = colors
    return ctk.CTkButton(
        parent, text=text, width=100, height=34,
        font=_font(13), corner_radius=7,
        fg_color=c["primary"], hover_color=c["hover"], text_color="#FFFFFF",
        command=cmd,
    )


def _btn_secondary(parent, text: str, width: int, colors: dict, cmd) -> ctk.CTkButton:
    c = colors
    return ctk.CTkButton(
        parent, text=text, width=width, height=34,
        font=_font(13), corner_radius=7,
        fg_color="transparent",
        text_color=c["text"],
        border_width=1, border_color=c["border"],
        hover_color=c["border"],
        command=cmd,
    )


def _btn_danger(parent, text: str, colors: dict, cmd) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, width=100, height=34,
        font=_font(13), corner_radius=7,
        fg_color="transparent",
        text_color="#EF4444",
        border_width=1, border_color="#EF4444",
        hover_color="#FEE2E2",
        command=cmd,
    )


# ── Context-menu helper ───────────────────────────────────────────────────────

def bind_entry_menu(entry: ctk.CTkEntry, colors: dict) -> None:
    """Attach a right-click Copy / Cut / Paste / Select-all menu to *entry*.

    Works by accessing the underlying tk.Entry via CTkEntry._entry.
    Falls back silently if the attribute is unavailable.
    """
    try:
        inner: tk.Entry = entry._entry  # internal widget of CTkEntry
    except AttributeError:
        return

    c = colors
    menu = tk.Menu(inner, tearoff=0,
                   font=("Segoe UI", 15),
                   bg=c["card"], fg=c["text"],
                   activebackground=c["primary"], activeforeground="#FFFFFF",
                   relief="flat", bd=0)

    def _copy():
        try:
            text = inner.selection_get()
            inner.clipboard_clear()
            inner.clipboard_append(text)
        except tk.TclError:
            pass

    def _cut():
        try:
            text = inner.selection_get()
            inner.clipboard_clear()
            inner.clipboard_append(text)
            inner.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass

    def _paste():
        try:
            text = inner.clipboard_get()
            try:
                inner.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                pass
            inner.insert(tk.INSERT, text)
        except tk.TclError:
            pass

    def _select_all():
        inner.select_range(0, "end")
        inner.icursor("end")

    menu.add_command(label="Вырезать",     command=_cut)
    menu.add_command(label="Копировать",   command=_copy)
    menu.add_command(label="Вставить",     command=_paste)
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=_select_all)

    def _show(event: tk.Event) -> None:
        inner.focus_set()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # Bind to both the CTkFrame shell and the inner tk.Entry
    entry.bind("<Button-3>", _show)
    inner.bind("<Button-3>", _show)


# ── Public API ────────────────────────────────────────────────────────────────

def show_message(
    parent: tk.Widget,
    title: str,
    message: str,
    colors: dict,
    icon: str = "ℹ",
) -> None:
    """Single OK button info/error dialog."""
    c = colors
    dlg, body, btn_row = _base(parent, title, colors, w=420, h=175)

    # Title + message
    ctk.CTkLabel(
        body, text=f"{icon}  {title}",
        font=_font(14, "bold"), text_color=c["text"], anchor="w",
    ).pack(anchor="w")
    ctk.CTkLabel(
        body, text=message,
        font=_font(13), text_color=c.get("text_secondary", c["text"]),
        wraplength=370, justify="left", anchor="w",
    ).pack(anchor="w", pady=(6, 0))

    # Buttons — right-aligned
    _btn_primary(btn_row, "ОК", colors, dlg.destroy).pack(side="right")

    dlg.lift()
    dlg.focus_force()
    dlg.wait_window()


def ask_yes_no(
    parent: tk.Widget,
    title: str,
    message: str,
    colors: dict,
    icon: str = "⚠",
) -> bool:
    """Да / Нет dialog. Returns True if user clicked Да."""
    c = colors
    result = {"value": False}
    dlg, body, btn_row = _base(parent, title, colors, w=420, h=180)

    ctk.CTkLabel(
        body, text=f"{icon}  {title}",
        font=_font(14, "bold"), text_color=c["text"], anchor="w",
    ).pack(anchor="w")
    ctk.CTkLabel(
        body, text=message,
        font=_font(13), text_color=c.get("text_secondary", c["text"]),
        wraplength=370, justify="left", anchor="w",
    ).pack(anchor="w", pady=(6, 0))

    def _yes():
        result["value"] = True
        dlg.destroy()

    # Buttons — right-aligned: Да | Нет
    _btn_danger(btn_row, "Нет", colors, dlg.destroy).pack(side="right")
    _btn_primary(btn_row, "Да", colors, _yes).pack(side="right", padx=(0, 8))

    dlg.lift()
    dlg.focus_force()
    dlg.wait_window()
    return result["value"]


def ask_save_changes(
    parent: tk.Widget,
    name: str,
    colors: dict,
) -> str:
    """Да | Сохранить как новый | Нет dialog for unsaved profile changes.

    Returns: 'save' | 'save_as_new' | 'discard' | 'cancel'
    """
    c = colors
    result = {"value": "cancel"}
    dlg, body, btn_row = _base(parent, "Несохранённые изменения", colors, w=500, h=185)

    ctk.CTkLabel(
        body, text="💾  Несохранённые изменения",
        font=_font(14, "bold"), text_color=c["text"], anchor="w",
    ).pack(anchor="w")
    ctk.CTkLabel(
        body,
        text=f"Профиль «{name}» был изменён. Сохранить изменения?",
        font=_font(13), text_color=c.get("text_secondary", c["text"]),
        wraplength=450, justify="left", anchor="w",
    ).pack(anchor="w", pady=(6, 0))

    def _save():
        result["value"] = "save"
        dlg.destroy()

    def _save_new():
        result["value"] = "save_as_new"
        dlg.destroy()

    def _discard():
        result["value"] = "discard"
        dlg.destroy()

    # Buttons — right-aligned: Да | Сохранить как новый | Нет
    _btn_danger(btn_row, "Нет", colors, _discard).pack(side="right")
    _btn_secondary(btn_row, "Сохранить как новый", 185, colors, _save_new).pack(
        side="right", padx=(0, 8)
    )
    _btn_primary(btn_row, "Да", colors, _save).pack(side="right", padx=(0, 8))

    dlg.lift()
    dlg.focus_force()
    dlg.wait_window()
    return result["value"]
