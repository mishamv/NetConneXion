"""Tools feature — connections panel.

Displays active TCP/UDP connections in a ttk.Treeview table with
live polling, diff-update (only changed rows replaced), and a
right-click context menu for killing processes.
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from quickip.features.tools.services.connections import ConnectionEntry
    from quickip.features.tools.presenter import ToolsPresenter

logger = logging.getLogger(__name__)

_COLUMNS = ("pid", "process", "local", "remote", "host", "proto", "state")
_HEADINGS = {
    "pid":     "PID",
    "process": "Процесс",
    "local":   "Локальный адрес",
    "remote":  "Удалённый адрес",
    "host":    "Хост",
    "proto":   "Протокол",
    "state":   "Состояние",
}
_COL_WIDTH = {
    "pid": 60, "process": 130, "local": 155, "remote": 155,
    "host": 160, "proto": 65, "state": 100,
}


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


class ConnectionsPanel(ctk.CTkFrame):
    """Left-panel tab showing live connections table."""

    def __init__(self, parent, colors: dict, presenter: "ToolsPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._colors = colors
        self._presenter = presenter
        self._polling = False
        self._row_data: Dict[str, tuple] = {}  # iid → row values
        self._data_queue: queue.Queue = queue.Queue(maxsize=4)

        self._build()

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self._colors
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            top, text="Сетевые подключения", font=_f(14, "bold"),
            text_color=c["text"], anchor="w",
        ).pack(side="left")

        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.pack(side="right")

        self._btn_toggle = ctk.CTkButton(
            btn_frame, text="▶ Мониторинг", width=130, height=30,
            font=_f(12), command=self._toggle_polling,
            fg_color=c["primary"], hover_color=c["hover"], text_color="#FFFFFF",
        )
        self._btn_toggle.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="Очистить DNS", width=110, height=30,
            font=_f(12), command=self._flush_dns,
            fg_color=c["card"], hover_color=c["border"], text_color=c["text"],
            border_width=1, border_color=c["border"],
        ).pack(side="left")

        # ── Filter row ────────────────────────────────────────────
        flt = ctk.CTkFrame(self, fg_color="transparent")
        flt.pack(fill="x", padx=8, pady=(0, 4))

        ctk.CTkLabel(flt, text="Фильтр:", font=_f(12), text_color=c["text"]).pack(
            side="left", padx=(0, 4)
        )
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", self._on_filter_change)
        ctk.CTkEntry(
            flt, textvariable=self._filter_var, width=200, height=28,
            font=_f(12), fg_color=c["input_bg"], text_color=c["text"],
            border_color=c["border"],
        ).pack(side="left")

        self._count_lbl = ctk.CTkLabel(
            flt, text="", font=_f(11),
            text_color=c.get("text_secondary", c["text"]),
        )
        self._count_lbl.pack(side="right")

        # ── Treeview ──────────────────────────────────────────────
        tree_frame = tk.Frame(self, bg=c["list_bg"])
        tree_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        style = ttk.Style()
        style.configure(
            "Conn.Treeview",
            background=c["list_bg"], foreground=c["list_text"],
            fieldbackground=c["list_bg"], rowheight=22,
        )
        style.configure("Conn.Treeview.Heading",
                         background=c["card"], foreground=c["text"])
        style.map("Conn.Treeview",
                  background=[("selected", c["list_selected_bg"])],
                  foreground=[("selected", c["list_selected_text"])])

        self._tree = ttk.Treeview(
            tree_frame, columns=_COLUMNS, show="headings",
            style="Conn.Treeview", selectmode="browse",
        )
        for col in _COLUMNS:
            self._tree.heading(col, text=_HEADINGS[col],
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=_COL_WIDTH[col], minwidth=40)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self._tree.bind("<Button-3>", self._show_context_menu)

        self._menu = tk.Menu(self._tree, tearoff=0)
        self._menu.add_command(label="Завершить процесс", command=self._kill_selected)
        self._menu.add_command(label="Завершить дерево процессов",
                               command=lambda: self._kill_selected(tree=True))

        self._last_entries: List["ConnectionEntry"] = []
        self._sort_col: str = "pid"
        self._sort_reverse: bool = False

    # ── Polling ───────────────────────────────────────────────────

    def _toggle_polling(self) -> None:
        if self._polling:
            self._stop_polling()
        else:
            self._start_polling()

    def _start_polling(self) -> None:
        self._polling = True
        self._btn_toggle.configure(text="⏹ Стоп")
        self._presenter.start_connection_polling(self._on_data_bg)
        self._poll_queue()

    def _stop_polling(self) -> None:
        self._polling = False
        self._btn_toggle.configure(text="▶ Мониторинг")
        self._presenter.stop_connection_polling()

    def _on_data_bg(self, entries: List["ConnectionEntry"]) -> None:
        """Called from background thread — only touches thread-safe queue."""
        try:
            self._data_queue.put_nowait(entries)
        except queue.Full:
            # Drop oldest, put newest
            try:
                self._data_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._data_queue.put_nowait(entries)
            except queue.Full:
                pass

    def _poll_queue(self) -> None:
        """Main-thread poller: drains queue and updates table every 500 ms."""
        if not self._polling:
            return
        try:
            entries = self._data_queue.get_nowait()
            self._update_table(entries)
        except queue.Empty:
            pass
        self.after(500, self._poll_queue)

    # ── Table update (diff) ───────────────────────────────────────

    def _update_table(self, entries: List["ConnectionEntry"]) -> None:
        self._last_entries = entries
        flt = self._filter_var.get().lower()
        visible = [
            e for e in entries
            if not flt or flt in e.process_name.lower()
               or flt in e.local_addr or flt in e.remote_addr
               or flt in e.remote_host.lower()
        ]
        new_data: Dict[str, tuple] = {}
        for e in visible:
            iid = f"{e.pid}_{e.local_addr}_{e.local_port}_{e.protocol}"
            vals = (
                e.pid, e.process_name,
                f"{e.local_addr}:{e.local_port}",
                f"{e.remote_addr}:{e.remote_port}" if e.remote_addr else "",
                e.remote_host, e.protocol, e.state,
            )
            new_data[iid] = vals

        # Delete rows no longer present
        existing = set(self._tree.get_children())
        for iid in existing - set(new_data.keys()):
            self._tree.delete(iid)

        # Insert / update rows
        for iid, vals in new_data.items():
            if iid in self._row_data:
                if self._row_data[iid] != vals:
                    self._tree.item(iid, values=vals)
            else:
                self._tree.insert("", "end", iid=iid, values=vals)

        self._row_data = new_data
        self._count_lbl.configure(text=f"{len(visible)} подключений")

    def _on_filter_change(self, *_) -> None:
        if self._last_entries:
            self._update_table(self._last_entries)

    # ── Context menu ──────────────────────────────────────────────

    def _show_context_menu(self, event: tk.Event) -> None:
        row = self._tree.identify_row(event.y)
        if row:
            self._tree.selection_set(row)
            self._menu.post(event.x_root, event.y_root)

    def _kill_selected(self, tree: bool = False) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        vals = self._tree.item(sel[0], "values")
        try:
            pid = int(vals[0])
        except (IndexError, ValueError):
            return
        proc = vals[1] if len(vals) > 1 else str(pid)
        if not messagebox.askyesno(
            "Завершить процесс",
            f"Завершить {'дерево ' if tree else ''}процесса {proc} (PID {pid})?",
        ):
            return
        ok = self._presenter.kill_process(pid, kill_tree=tree)
        if not ok:
            messagebox.showerror("Ошибка", f"Не удалось завершить PID {pid}")

    def _flush_dns(self) -> None:
        self._presenter.flush_dns_cache()

    # ── Sorting ───────────────────────────────────────────────────

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = False
        rows = [(self._tree.set(iid, col), iid) for iid in self._tree.get_children()]
        try:
            rows.sort(key=lambda x: int(x[0]) if x[0].isdigit() else x[0].lower(),
                      reverse=self._sort_reverse)
        except Exception:
            rows.sort(reverse=self._sort_reverse)
        for idx, (_, iid) in enumerate(rows):
            self._tree.move(iid, "", idx)

    # ── Colors ────────────────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        self._colors = colors

    def on_hide(self) -> None:
        """Called when another tab is selected."""
        if self._polling:
            self._stop_polling()
