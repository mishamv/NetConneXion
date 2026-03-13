"""Right panel — profile form and action buttons."""

from __future__ import annotations

import tkinter as tk
from typing import List, Optional, TYPE_CHECKING

import customtkinter as ctk

from quickip.core.models import Profile, IPMode, DNSMode
from quickip.core.ui.dialogs import show_message, ask_yes_no, ask_save_changes, bind_entry_menu

if TYPE_CHECKING:
    from quickip.features.profiles.presenter import ProfilesPresenter


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


def _setup_entry_keys(entry: ctk.CTkEntry) -> None:
    """Make Ctrl+C/X/V/A work in CTkEntry regardless of keyboard layout.

    Problem 1 — Focus: CTkEntry's canvas has no <Button-1> handler, so clicking
    the border area does NOT move focus to the inner tk.Entry.  Keyboard focus
    stays on whatever widget was active before (e.g. a sidebar button), so key
    events never reach the entry.

    Problem 2 — Non-Latin layouts (Russian, etc.): Tk maps <<Copy>> to the
    <Control-Key-c> pattern using the *keysym* "c".  With a Cyrillic layout the
    same physical key produces keysym "Cyrillic_es", so <<Copy>> is never
    generated and the shortcut silently does nothing.

    Fix:
      • <Button-1> / <FocusIn> on canvas → inner.focus_set()
      • Canvas clipboard events forwarded to inner via event_generate.
      • <Control-Key> bound on BOTH inner and canvas; uses event.keycode
        (Windows Virtual Key code = key *position*, layout-independent) to
        perform the operation directly — bypassing the keysym mismatch entirely.
    """
    try:
        inner: tk.Entry = entry._entry
        canvas = entry._canvas
    except AttributeError:
        return

    # ── Canvas focus redirect ─────────────────────────────────────────────────
    canvas.bind("<FocusIn>",  lambda e: inner.focus_set(), add="+")
    canvas.bind("<Button-1>", lambda e: inner.focus_set(), add="+")

    # ── Canvas: forward <<Virtual>> events to inner (English layout fallback) ─
    for ev in ("<<Copy>>", "<<Cut>>", "<<Paste>>", "<<SelectAll>>"):
        def _make_fwd(name: str):
            def _fwd(e=None):
                inner.focus_set()
                inner.event_generate(name)
                return "break"
            return _fwd
        canvas.bind(ev, _make_fwd(ev), add="+")

    # ── Keycode-based handler — works with ANY keyboard layout ────────────────
    # Windows VK codes: A=65, C=67, V=86, X=88.
    # event.keycode equals the VK code regardless of which layout is active,
    # so Ctrl+С (Cyrillic) and Ctrl+C (Latin) both produce keycode 67.
    def _ctrl_key(e: tk.Event) -> str | None:
        inner.focus_set()
        kc = e.keycode
        if kc == 67:                        # C → Copy
            try:
                sel = inner.selection_get()
                inner.clipboard_clear()
                inner.clipboard_append(sel)
            except tk.TclError:
                pass
        elif kc == 88:                      # X → Cut
            try:
                sel = inner.selection_get()
                inner.clipboard_clear()
                inner.clipboard_append(sel)
                inner.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                pass
        elif kc == 86:                      # V → Paste
            try:
                text = inner.clipboard_get()
                try:
                    inner.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except tk.TclError:
                    pass
                inner.insert(tk.INSERT, text)
            except tk.TclError:
                pass
        elif kc == 65:                      # A → Select All
            inner.select_range(0, "end")
            inner.icursor("end")
        else:
            return None                     # not our key — let Tk handle it
        return "break"

    for widget in (inner, canvas):
        widget.bind("<Control-Key>", _ctrl_key, add="+")


class FormPanel(ctk.CTkFrame):
    """Right-side panel: profile form fields and action buttons."""

    def __init__(
        self,
        parent: tk.Widget,
        colors: dict,
        presenter: "ProfilesPresenter",
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._colors = colors
        self._presenter = presenter
        self._dirty = False
        self._loading = False
        self._selected_name: Optional[str] = None

        # StringVars for form fields — trace fires on any change
        self._name_var = tk.StringVar()
        self._ip_var   = tk.StringVar()
        self._mask_var = tk.StringVar()
        self._gw_var   = tk.StringVar()
        self._dns1_var = tk.StringVar()
        self._dns2_var = tk.StringVar()
        for v in (self._name_var, self._ip_var, self._mask_var,
                  self._gw_var, self._dns1_var, self._dns2_var):
            v.trace_add("write", self._on_var_change)

        self.dhcp_ip  = tk.BooleanVar(value=False)
        self.dhcp_dns = tk.BooleanVar(value=False)

        self._build()

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self._colors

        # Top bar: action buttons (right-aligned)
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top_bar.grid_columnconfigure(0, weight=1)

        self._btn_apply = ctk.CTkButton(
            top_bar, text="▶  Применить профиль",
            height=40, width=210, font=_f(13, "bold"),
            text_color="#FFFFFF", command=self._on_apply_click,
        )
        self._btn_apply.grid(row=0, column=1, padx=(0, 8))

        self._btn_save = ctk.CTkButton(
            top_bar, text="💾  Сохранить",
            height=40, width=150, font=_f(13, "bold"),
            text_color="#FFFFFF", command=self._on_save_click,
        )
        self._btn_save.grid(row=0, column=2)
        self._style_action_buttons()

        # Profile form card
        self._form_frame = ctk.CTkFrame(
            self,
            fg_color=c.get("card_inner", c["input_bg"]),
            corner_radius=int(c.get("card_radius", 16)), border_width=1,
            border_color=c.get("card_border", c["border"]),
        )
        self._form_frame.grid_columnconfigure(1, weight=1)
        self._form_frame.grid(row=1, column=0, sticky="nsew")
        self._build_form(self._form_frame)

    def _build_form(self, parent: tk.Widget) -> None:
        c = self._colors
        row = 0

        def lbl(text: str) -> ctk.CTkLabel:
            return ctk.CTkLabel(parent, text=text, font=_f(14),
                                text_color=c["text"], anchor="w", width=160)

        def entry(**kw) -> ctk.CTkEntry:
            return ctk.CTkEntry(parent, height=38, corner_radius=int(c.get("input_radius", 10)), font=_f(14),
                                border_color=c["border"], fg_color=c["input_bg"],
                                text_color=c["text"],
                                placeholder_text_color=c.get("input_placeholder", c.get("text_secondary", c["text"])),
                                **kw)

        def sep() -> None:
            nonlocal row
            ctk.CTkFrame(parent, height=1, fg_color=c["border"]).grid(
                row=row, column=0, columnspan=2, sticky="ew", padx=14, pady=4)
            row += 1

        # Profile name
        lbl("Имя профиля").grid(row=row, column=0, sticky="w", padx=(14, 8), pady=10)
        self.name_entry = entry(textvariable=self._name_var)
        self.name_entry.grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=10)
        _setup_entry_keys(self.name_entry)
        bind_entry_menu(self.name_entry, c)
        row += 1

        # Adapter
        lbl("Адаптер").grid(row=row, column=0, sticky="w", padx=(14, 8), pady=10)
        self.adapter_combo = ctk.CTkComboBox(
            parent, state="readonly", values=["Ethernet", "Wi-Fi"],
            height=38, font=_f(14), corner_radius=int(c.get("input_radius", 10)),
            border_color=c["border"], fg_color=c["input_bg"],
            button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            text_color=c["text"], text_color_disabled=c["text"],
            command=lambda _: self._mark_dirty(),
        )
        self.adapter_combo.grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=10)
        row += 1
        sep()

        # DHCP IP
        self._dhcp_ip_cb = ctk.CTkCheckBox(
            parent, text="Получить IP автоматически (DHCP)",
            variable=self.dhcp_ip, command=self._toggle_ip,
            font=_f(14), text_color=c["text"],
        )
        self._dhcp_ip_cb.grid(row=row, column=0, columnspan=2, sticky="w", padx=14, pady=10)
        row += 1

        ip_entries = [("IP адрес", "_ip_var", "ip_entry"),
                      ("Маска подсети", "_mask_var", "mask_entry"),
                      ("Шлюз",         "_gw_var",   "gw_entry")]
        for label_text, var_name, attr in ip_entries:
            lbl(label_text).grid(row=row, column=0, sticky="w", padx=(14, 8), pady=10)
            e = entry(textvariable=getattr(self, var_name))
            e.grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=10)
            _setup_entry_keys(e)
            bind_entry_menu(e, c)
            setattr(self, attr, e)
            row += 1

        sep()

        # DHCP DNS
        self._dhcp_dns_cb = ctk.CTkCheckBox(
            parent, text="Получить DNS автоматически",
            variable=self.dhcp_dns, command=self._toggle_dns,
            font=_f(14), text_color=c["text"],
        )
        self._dhcp_dns_cb.grid(row=row, column=0, columnspan=2, sticky="w", padx=14, pady=10)
        row += 1

        dns_entries = [("DNS основной",       "_dns1_var", "dns1_entry"),
                       ("DNS альтернативный", "_dns2_var", "dns2_entry")]
        for label_text, var_name, attr in dns_entries:
            lbl(label_text).grid(row=row, column=0, sticky="w", padx=(14, 8), pady=10)
            e = entry(textvariable=getattr(self, var_name))
            e.grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=10)
            _setup_entry_keys(e)
            bind_entry_menu(e, c)
            setattr(self, attr, e)
            row += 1

    def _style_action_buttons(self) -> None:
        c = self._colors
        self._btn_apply.configure(
            fg_color=c.get("btn_primary_bg", c["accent"]),
            hover_color=c.get("btn_primary_hover", c["hover"]),
            text_color=c.get("btn_primary_text", "#FFFFFF"),
            corner_radius=10,
        )
        self._btn_save.configure(
            fg_color=c.get("btn_outline_bg", c["input_bg"]),
            hover_color=c["bg"],
            text_color=c.get("btn_outline_text", c["text"]),
            border_width=1,
            border_color=c.get("btn_outline_border", c["border"]),
            corner_radius=10,
        )

    # ── Dirty state ───────────────────────────────────────────────

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def clear_dirty(self) -> None:
        self._dirty = False

    def _mark_dirty(self) -> None:
        if not self._loading:
            self._dirty = True

    def _on_var_change(self, *_) -> None:
        self._mark_dirty()

    # ── Toggle helpers ────────────────────────────────────────────

    def _toggle_ip(self) -> None:
        state = "disabled" if self.dhcp_ip.get() else "normal"
        for e in (self.ip_entry, self.mask_entry, self.gw_entry):
            e.configure(state=state)
        self._mark_dirty()

    def _toggle_dns(self) -> None:
        state = "disabled" if self.dhcp_dns.get() else "normal"
        for e in (self.dns1_entry, self.dns2_entry):
            e.configure(state=state)
        self._mark_dirty()

    # ── Button handlers ───────────────────────────────────────────

    def _on_save_click(self) -> None:
        if self._dirty:
            name = self._name_var.get() or (self._selected_name or "")
            root = self.winfo_toplevel()
            action = ask_save_changes(root, name, self._colors)
            if action == "cancel":
                return
            if action == "discard":
                if self._selected_name:
                    self._presenter.on_select(self._selected_name)
                else:
                    self.clear_dirty()
                return
            if action == "save_as_new":
                self._presenter.save_as_new_profile(self.read_form())
                return
            # action == "save" → fall through
        self._presenter.save_profile(self.read_form())

    def _on_apply_click(self) -> None:
        root = self.winfo_toplevel()
        confirmed = ask_yes_no(
            root, "Применить профиль",
            "Параметры сетевого адаптера будут изменены.\nПродолжить?",
            self._colors,
        )
        if confirmed:
            self._presenter.apply_profile(self.read_form())

    # ── Public interface ──────────────────────────────────────────

    def load(self, profile: Profile, adapters: List[str], focus: bool = False) -> None:
        """Populate form from *profile*; updates are suppressed from dirty tracking."""
        self._loading = True
        try:
            self._selected_name = profile.name
            self._name_var.set(profile.name)

            if adapters:
                self.adapter_combo.configure(values=adapters)
            self.adapter_combo.set(profile.adapter or (adapters[0] if adapters else ""))

            self.dhcp_ip.set(profile.ip_mode == IPMode.DHCP)
            self._toggle_ip()
            self._ip_var.set(profile.ipv4 or "")
            self._mask_var.set(profile.mask or "")
            self._gw_var.set(profile.gateway or "")

            self.dhcp_dns.set(profile.dns_mode == DNSMode.DHCP)
            self._toggle_dns()
            self._dns1_var.set(profile.dns_primary or "")
            self._dns2_var.set(profile.dns_secondary or "")
        finally:
            self._loading = False

        self.clear_dirty()
        # Move keyboard focus into the form only when user explicitly selected a profile
        if focus:
            self.after(50, self._focus_name_entry)

    def _focus_name_entry(self) -> None:
        try:
            self.name_entry._entry.focus_set()
        except Exception:
            pass

    def read_form(self) -> dict:
        return {
            "name":          self.name_entry.get(),
            "adapter":       self.adapter_combo.get(),
            "dhcp_ip":       self.dhcp_ip.get(),
            "ip":            self.ip_entry.get(),
            "mask":          self.mask_entry.get(),
            "gateway":       self.gw_entry.get(),
            "dhcp_dns":      self.dhcp_dns.get(),
            "dns_primary":   self.dns1_entry.get(),
            "dns_secondary": self.dns2_entry.get(),
        }

    def check_unsaved(self) -> bool:
        """Show dirty-state dialog; return False only if user cancels."""
        if not self._dirty:
            return True
        name = self._name_var.get() or (self._selected_name or "")
        root = self.winfo_toplevel()
        action = ask_save_changes(root, name, self._colors)
        if action == "cancel":
            return False
        if action == "discard":
            self.clear_dirty()
            return True
        if action == "save":
            self._presenter.save_profile(self.read_form())
            self.clear_dirty()
            return True
        if action == "save_as_new":
            self._presenter.save_as_new_profile(self.read_form())
            self.clear_dirty()
            return True
        return False

    def update_colors(self, colors: dict) -> None:
        self._colors = colors
        c = colors

        def _cfg(w, **kw):
            try:
                w.configure(**kw)
            except Exception:
                pass

        _cfg(self._form_frame,
             fg_color=c.get("card_inner", c["input_bg"]),
             border_color=c.get("card_border", c["border"]),
             corner_radius=int(c.get("card_radius", 16)))

        entry_kw = dict(
            fg_color=c["input_bg"],
            border_color=c["border"],
            text_color=c["text"],
            border_width=1,
            corner_radius=int(c.get("input_radius", 10)),
            placeholder_text_color=c.get("input_placeholder", c.get("text_secondary", c["text"])),
        )
        for e in (self.name_entry, self.ip_entry, self.mask_entry,
                  self.gw_entry, self.dns1_entry, self.dns2_entry):
            _cfg(e, **entry_kw)

        _cfg(self.adapter_combo,
             fg_color=c["input_bg"], border_color=c["border"],
             button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
             dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
             text_color=c["text"], text_color_disabled=c["text"],
             corner_radius=int(c.get("input_radius", 10)))

        for cb in (self._dhcp_ip_cb, self._dhcp_dns_cb):
            _cfg(cb, text_color=c["text"])

        self._style_action_buttons()
