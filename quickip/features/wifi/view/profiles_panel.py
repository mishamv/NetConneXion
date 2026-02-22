"""Wi-Fi feature — profiles panel.

Left: scrollable list of saved WifiProfiles.
Right: full edit form — SSID, auth, cipher, password (with eye toggle),
       auto-connect, hidden SSID, ad-hoc checkboxes, import/export buttons.

Password is encrypted via DPAPI vault on save; the Save button is disabled
if vault is unavailable.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import List, Optional, TYPE_CHECKING

import customtkinter as ctk

from quickip.features.wifi.repository import (
    WifiProfile, AUTH_OPTIONS, CIPHER_OPTIONS,
)

if TYPE_CHECKING:
    from quickip.features.wifi.presenter import WifiPresenter

logger = logging.getLogger(__name__)


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


class ProfilesPanel(ctk.CTkFrame):
    """Profiles panel: list + edit form + import/export."""

    def __init__(self, parent, colors: dict, presenter: "WifiPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._colors = colors
        self._presenter = presenter
        self._selected_id: Optional[str] = None
        self._profiles: List[WifiProfile] = []
        self._build()
        self.after(100, self._refresh)

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self._colors
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Left list ─────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=c["card"], width=210, corner_radius=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=6)
        left.grid_propagate(False)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(left, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            hdr, text="Профили", font=_f(13, "bold"), text_color=c["text"],
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="+", width=28, height=28, font=_f(16),
            fg_color="transparent", hover_color=c["border"],
            text_color=c["text"], command=self._new_profile,
        ).pack(side="right")

        self._list_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))

        # Import / Export
        ie_frame = ctk.CTkFrame(left, fg_color="transparent")
        ie_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 8))
        ctk.CTkButton(
            ie_frame, text="Импорт", width=90, height=26, font=_f(11),
            fg_color=c["card"], hover_color=c["border"], text_color=c["text"],
            border_width=1, border_color=c["border"], command=self._import,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            ie_frame, text="Экспорт", width=90, height=26, font=_f(11),
            fg_color=c["card"], hover_color=c["border"], text_color=c["text"],
            border_width=1, border_color=c["border"], command=self._export,
        ).pack(side="left")

        # ── Right form ────────────────────────────────────────────
        right_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        right_scroll.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=6)
        right_scroll.grid_columnconfigure(1, weight=1)
        self._form = right_scroll

        rows = [
            ("SSID:",            "_ssid_var",   "entry",  None),
            ("Аутентификация:",  "_auth_var",   "combo",  AUTH_OPTIONS),
            ("Шифрование:",      "_cipher_var", "combo",  ["AES"]),
            ("Пароль:",          "_pwd_var",    "pwd",    None),
        ]
        for i, (label, attr, kind, opts) in enumerate(rows):
            ctk.CTkLabel(
                right_scroll, text=label, font=_f(12), text_color=c["text"], anchor="w",
            ).grid(row=i, column=0, sticky="w", padx=(10, 6), pady=4)

            var = tk.StringVar()
            setattr(self, attr, var)

            if kind == "entry":
                ctk.CTkEntry(
                    right_scroll, textvariable=var, height=32, font=_f(12),
                    fg_color=c["input_bg"], text_color=c["text"],
                    border_color=c["border"],
                ).grid(row=i, column=1, sticky="ew", padx=(0, 10), pady=4)

            elif kind == "combo":
                menu = ctk.CTkOptionMenu(
                    right_scroll, values=opts or ["AES"],
                    variable=var, height=32, font=_f(12),
                    fg_color=c["input_bg"], text_color=c["text"],
                    button_color=c["combo_button"],
                    button_hover_color=c["combo_button_hover"],
                    dropdown_fg_color=c["card"],
                    dropdown_text_color=c["text"],
                    command=self._on_auth_change if attr == "_auth_var" else None,
                )
                menu.grid(row=i, column=1, sticky="ew", padx=(0, 10), pady=4)
                if attr == "_cipher_var":
                    self._cipher_menu = menu

            elif kind == "pwd":
                pwd_row = ctk.CTkFrame(right_scroll, fg_color="transparent")
                pwd_row.grid(row=i, column=1, sticky="ew", padx=(0, 10), pady=4)
                pwd_row.grid_columnconfigure(0, weight=1)
                self._pwd_entry = ctk.CTkEntry(
                    pwd_row, textvariable=var, show="*", height=32, font=_f(12),
                    fg_color=c["input_bg"], text_color=c["text"],
                    border_color=c["border"],
                )
                self._pwd_entry.grid(row=0, column=0, sticky="ew")
                ctk.CTkButton(
                    pwd_row, text="👁", width=32, height=32, font=_f(14),
                    fg_color="transparent", hover_color=c["border"],
                    text_color=c["text"], command=self._toggle_pwd,
                ).grid(row=0, column=1, padx=(4, 0))

        # Checkboxes
        self._auto_var = tk.BooleanVar(value=True)
        self._hidden_var = tk.BooleanVar(value=False)
        self._adhoc_var = tk.BooleanVar(value=False)

        for i, (label, attr) in enumerate([
            ("Подключаться автоматически", "_auto_var"),
            ("Скрытая сеть (Hidden SSID)", "_hidden_var"),
            ("Ad-hoc сеть", "_adhoc_var"),
        ], start=4):
            ctk.CTkCheckBox(
                right_scroll, text=label, variable=getattr(self, attr),
                font=_f(12), text_color=c["text"],
                fg_color=c["accent"] if hasattr(c, "accent") else c["primary"],
                hover_color=c.get("hover", c["primary"]),
            ).grid(row=i, column=0, columnspan=2, sticky="w", padx=10, pady=2)

        # Action buttons
        btn_row = ctk.CTkFrame(right_scroll, fg_color="transparent")
        btn_row.grid(row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))

        vault_ok = self._presenter.vault_available
        self._save_btn = ctk.CTkButton(
            btn_row, text="Сохранить", width=110, height=32, font=_f(12),
            fg_color=c["primary"], hover_color=c["hover"], text_color="#FFFFFF",
            command=self._save,
            state="normal" if vault_ok else "disabled",
        )
        self._save_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Удалить", width=90, height=32, font=_f(12),
            fg_color=c["card"], hover_color="#EF4444", text_color=c["text"],
            border_width=1, border_color=c["border"],
            command=self._delete,
        ).pack(side="left")

        if not vault_ok:
            ctk.CTkLabel(
                right_scroll,
                text="⚠ Шифрование паролей недоступно (pywin32 не установлен). Сохранение невозможно.",
                font=_f(10),
                text_color="#EF4444",
                wraplength=320, anchor="w",
            ).grid(row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))

        self._msg_lbl = ctk.CTkLabel(
            right_scroll, text="", font=_f(11),
            text_color=c.get("text_secondary", c["text"]),
        )
        self._msg_lbl.grid(row=9, column=0, columnspan=2, sticky="w", padx=10)

    # ── Data ──────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._profiles = self._presenter.load_profiles()
        for w in self._list_frame.winfo_children():
            w.destroy()
        c = self._colors
        for p in self._profiles:
            row = ctk.CTkFrame(self._list_frame, fg_color="transparent", corner_radius=6,
                               cursor="hand2")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row, text=f"📶 {p.ssid}", font=_f(12), text_color=c["text"], anchor="w",
            ).pack(side="left", padx=(8, 0), pady=4, fill="x", expand=True)
            ctk.CTkLabel(
                row, text=p.auth, font=_f(10),
                text_color=c.get("text_secondary", c["text"]), anchor="e",
            ).pack(side="right", padx=6)
            row.bind("<Button-1>", lambda _e, pid=p.id: self._select(pid))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda _e, pid=p.id: self._select(pid))
        if not self._profiles:
            ctk.CTkLabel(
                self._list_frame, text="Нет профилей", font=_f(11),
                text_color=c.get("text_secondary", c["text"]),
            ).pack(pady=12)

    def _select(self, profile_id: str) -> None:
        self._selected_id = profile_id
        p = next((x for x in self._profiles if x.id == profile_id), None)
        if not p:
            return
        self._ssid_var.set(p.ssid)
        self._auth_var.set(p.auth)
        self._on_auth_change(p.auth)
        self._cipher_var.set(p.cipher)
        self._pwd_var.set("")         # never pre-fill password
        self._auto_var.set(p.auto_connect)
        self._hidden_var.set(p.connect_hidden)
        self._adhoc_var.set(p.is_adhoc)
        self._msg_lbl.configure(text="")

    def _new_profile(self) -> None:
        self._selected_id = None
        self._ssid_var.set("")
        self._auth_var.set("WPA2-Personal")
        self._on_auth_change("WPA2-Personal")
        self._pwd_var.set("")
        self._auto_var.set(True)
        self._hidden_var.set(False)
        self._adhoc_var.set(False)
        self._msg_lbl.configure(text="")

    # ── Actions ───────────────────────────────────────────────────

    def _on_auth_change(self, auth: str) -> None:
        options = self._presenter.get_cipher_options(auth)
        self._cipher_menu.configure(values=options)
        self._cipher_var.set(options[0] if options else "AES")

    def _toggle_pwd(self) -> None:
        current = self._pwd_entry.cget("show")
        self._pwd_entry.configure(show="" if current == "*" else "*")

    def _save(self) -> None:
        ssid = self._ssid_var.get().strip()
        if not ssid:
            self._msg_lbl.configure(text="Укажите SSID", text_color="#EF4444")
            return
        try:
            self._presenter.save_profile(
                ssid=ssid,
                auth=self._auth_var.get(),
                cipher=self._cipher_var.get(),
                password=self._pwd_var.get(),
                auto_connect=self._auto_var.get(),
                connect_hidden=self._hidden_var.get(),
                is_adhoc=self._adhoc_var.get(),
                profile_id=self._selected_id,
            )
            self._msg_lbl.configure(
                text=f"Сохранено: {ssid}",
                text_color=self._colors.get("text_secondary", self._colors["text"]),
            )
            self._refresh()
        except Exception as exc:
            self._msg_lbl.configure(text=str(exc), text_color="#EF4444")

    def _delete(self) -> None:
        if not self._selected_id:
            return
        ssid = self._ssid_var.get() or "?"
        if not messagebox.askyesno("Удалить профиль",
                                   f"Удалить профиль для «{ssid}»?"):
            return
        self._presenter.delete_profile(self._selected_id)
        self._selected_id = None
        self._new_profile()
        self._refresh()

    def _import(self) -> None:
        path = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Импорт профилей Wi-Fi",
        )
        if not path:
            return
        try:
            count, errors = self._presenter.import_profiles(path)
            msg = f"Импортировано: {count}"
            if errors:
                msg += f"\nОшибки ({len(errors)}): " + "; ".join(errors[:3])
            messagebox.showinfo("Импорт завершён", msg)
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Ошибка импорта", str(exc))

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Экспорт профилей Wi-Fi",
        )
        if not path:
            return
        try:
            self._presenter.export_profiles(path)
            self._msg_lbl.configure(text=f"Экспортировано в: {path}")
        except Exception as exc:
            messagebox.showerror("Ошибка экспорта", str(exc))

    # ── Colors ────────────────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        self._colors = colors
