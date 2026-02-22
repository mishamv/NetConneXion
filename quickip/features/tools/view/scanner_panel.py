"""Tools feature — scanner panel.

Subnet / IP-range scanner with three modes (ICMP / ARP / TCP),
a progress bar, a results Treeview, and CSV export.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, ttk
from typing import List, Optional, TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from quickip.features.tools.services.scanner import ScanResult
    from quickip.features.tools.presenter import ToolsPresenter

logger = logging.getLogger(__name__)

_COL_IDS   = ("ip", "hostname", "reachable", "ports", "latency")
_COL_HEADS = {
    "ip": "IP-адрес", "hostname": "Хост", "reachable": "Доступен",
    "ports": "Открытые порты", "latency": "Задержка (мс)",
}
_COL_W = {"ip": 120, "hostname": 180, "reachable": 80, "ports": 160, "latency": 100}


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


class ScannerPanel(ctk.CTkFrame):
    """Network scanner tab: mode selector, progress bar, results table."""

    def __init__(self, parent, colors: dict, presenter: "ToolsPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._colors = colors
        self._presenter = presenter
        self._scanning = False
        self._results: List["ScanResult"] = []
        self._done = 0
        self._total = 0
        self._build()

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self._colors

        # ── Controls ──────────────────────────────────────────────
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=8, pady=(8, 4))
        ctrl.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            ctrl, text="Цель (CIDR / IP):", font=_f(12), text_color=c["text"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))

        self._target_var = tk.StringVar(value="192.168.1.0/24")
        ctk.CTkEntry(
            ctrl, textvariable=self._target_var,
            width=220, height=32, font=_f(12),
            fg_color=c["input_bg"], text_color=c["text"],
            border_color=c["border"],
        ).grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(
            ctrl, text="Режим:", font=_f(12), text_color=c["text"],
        ).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(8, 0))

        mode_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        mode_frame.grid(row=1, column=1, sticky="w", pady=(8, 0))

        self._mode_var = tk.StringVar(value="icmp")
        for mode, label in (("icmp", "ICMP (Ping)"), ("arp", "ARP"), ("tcp", "TCP порты")):
            ctk.CTkRadioButton(
                mode_frame, text=label, value=mode, variable=self._mode_var,
                font=_f(12), text_color=c["text"],
                fg_color=c["accent"], hover_color=c["hover"],
            ).pack(side="left", padx=(0, 14))

        # ── Action buttons ────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(4, 4))

        self._scan_btn = ctk.CTkButton(
            btn_row, text="▶ Сканировать", width=140, height=32, font=_f(12),
            fg_color=c["primary"], hover_color=c["hover"], text_color="#FFFFFF",
            command=self._start_scan,
        )
        self._scan_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            btn_row, text="⏹ Стоп", width=80, height=32, font=_f(12),
            fg_color=c["card"], hover_color=c["border"], text_color=c["text"],
            border_width=1, border_color=c["border"],
            command=self._stop_scan, state="disabled",
        )
        self._stop_btn.pack(side="left", padx=(0, 8))

        self._export_btn = ctk.CTkButton(
            btn_row, text="⬇ CSV", width=80, height=32, font=_f(12),
            fg_color=c["card"], hover_color=c["border"], text_color=c["text"],
            border_width=1, border_color=c["border"],
            command=self._export_csv, state="disabled",
        )
        self._export_btn.pack(side="left")

        self._status_lbl = ctk.CTkLabel(
            btn_row, text="", font=_f(11),
            text_color=c.get("text_secondary", c["text"]),
        )
        self._status_lbl.pack(side="right")

        # ── Progress bar ──────────────────────────────────────────
        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress = ctk.CTkProgressBar(
            self, variable=self._progress_var,
            fg_color=c["border"], progress_color=c["accent"],
        )
        self._progress.pack(fill="x", padx=8, pady=(0, 4))

        # ── Results table ─────────────────────────────────────────
        tree_wrap = tk.Frame(self, bg=c["list_bg"])
        tree_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        style = ttk.Style()
        style.configure(
            "Scan.Treeview",
            background=c["list_bg"], foreground=c["list_text"],
            fieldbackground=c["list_bg"], rowheight=22,
        )
        style.configure("Scan.Treeview.Heading",
                         background=c["card"], foreground=c["text"])
        style.map("Scan.Treeview",
                  background=[("selected", c["list_selected_bg"])],
                  foreground=[("selected", c["list_selected_text"])])

        self._tree = ttk.Treeview(
            tree_wrap, columns=_COL_IDS, show="headings",
            style="Scan.Treeview", selectmode="browse",
        )
        for col in _COL_IDS:
            self._tree.heading(col, text=_COL_HEADS[col])
            self._tree.column(col, width=_COL_W[col], minwidth=40)

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        hsb = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self._tree.xview)
        self._tree.configure(xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)

        # Tag reachable rows green
        self._tree.tag_configure("up", foreground="#22C55E")

    # ── Scan control ──────────────────────────────────────────────

    def _start_scan(self) -> None:
        if self._scanning:
            return
        target = self._target_var.get().strip()
        if not target:
            return
        mode = self._mode_var.get()
        self._scanning = True
        self._results.clear()
        self._done = 0
        self._total = 0
        self._progress_var.set(0.0)
        self._status_lbl.configure(text="Сканирование…")
        self._scan_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._export_btn.configure(state="disabled")
        # Clear table
        for iid in self._tree.get_children():
            self._tree.delete(iid)

        self._presenter.start_scan(
            target, mode,
            on_progress=self._on_progress,
            on_complete=self._on_complete,
        )

    def _stop_scan(self) -> None:
        self._presenter.stop_scan()

    def _on_progress(self, done: int, total: int, result: "ScanResult") -> None:
        """Called from worker thread — marshal to UI."""
        self.after(0, self._update_progress, done, total, result)

    def _update_progress(self, done: int, total: int, result: "ScanResult") -> None:
        self._done = done
        self._total = total
        pct = done / total if total else 0
        self._progress_var.set(pct)
        self._status_lbl.configure(text=f"{done}/{total}")
        if result.reachable:
            self._insert_result(result)

    def _on_complete(self, results: List["ScanResult"]) -> None:
        self.after(0, self._finish, results)

    def _finish(self, results: List["ScanResult"]) -> None:
        self._results = results
        self._scanning = False
        live = sum(1 for r in results if r.reachable)
        self._status_lbl.configure(
            text=f"Готово: {live} активных из {len(results)}"
        )
        self._progress_var.set(1.0)
        self._scan_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        if results:
            self._export_btn.configure(state="normal")

    def _insert_result(self, r: "ScanResult") -> None:
        ports_str = ";".join(str(p) for p in r.open_ports) if r.open_ports else ""
        self._tree.insert(
            "", "end",
            values=(r.ip, r.hostname, "Да", ports_str, f"{r.latency_ms:.1f}"),
            tags=("up",),
        )

    # ── Export ────────────────────────────────────────────────────

    def _export_csv(self) -> None:
        if not self._results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Сохранить результаты сканирования",
        )
        if not path:
            return
        try:
            self._presenter.export_scan_csv(self._results, path)
            self._status_lbl.configure(text=f"Сохранено: {path}")
        except Exception as exc:
            logger.exception("CSV export error")
            self._status_lbl.configure(text=f"Ошибка: {exc}")

    # ── Colors ────────────────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        self._colors = colors
