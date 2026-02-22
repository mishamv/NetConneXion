"""History feature presenter — display, filter, stats, rollback."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Protocol

from quickip.core.models import ProfileHistoryEntry, HistoryStats
from quickip.core.paths import get_history_file
from quickip.core.events.types import ProfileApplied, ProfileApplyFailed
from quickip.features.history.repository import HistoryRepository

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)


# ── View protocol ─────────────────────────────────────────────────

class HistoryViewProtocol(Protocol):
    def show_history_entries(self, lines: List[str]) -> None: ...
    def show_history_stats(self, text: str) -> None: ...
    def show_message(self, title: str, message: str) -> None: ...
    def get_history_search(self) -> str: ...
    def get_history_status_filter(self) -> str: ...


# ── Presenter ─────────────────────────────────────────────────────

class HistoryPresenter:
    """Orchestrates history display, filtering and rollback.

    Subscribes to ProfileApplied / ProfileApplyFailed events so the
    history list refreshes automatically without callback wiring.
    """

    def __init__(self, container: "ServiceContainer") -> None:
        self._container = container
        self._repo = HistoryRepository(get_history_file())
        self._view: Optional[HistoryViewProtocol] = None

        # Auto-refresh when a profile apply result arrives
        bus = container.event_bus
        bus.subscribe(ProfileApplied, self._on_applied)
        bus.subscribe(ProfileApplyFailed, self._on_applied)

    def bind_view(self, view: HistoryViewProtocol) -> None:
        self._view = view

    # ── Event handlers ────────────────────────────────────────────

    def _on_applied(self, _event) -> None:
        """Called via EventBus after any profile apply attempt."""
        if self._view is not None:
            self.refresh()

    # ── Refresh ───────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload history from repo, apply filters, push to view."""
        if self._view is None:
            return

        entries = self._repo.list()
        query = self._view.get_history_search().strip().lower()
        status_filter = self._view.get_history_status_filter().strip()

        filtered: List[ProfileHistoryEntry] = []
        for entry in entries:
            if query and query not in entry.profile_name.lower():
                continue
            if status_filter == "Успешные" and not entry.success:
                continue
            if status_filter == "Ошибки" and entry.success:
                continue
            filtered.append(entry)

        stats = self._compute_stats(filtered)
        self._view.show_history_stats(
            f"Статистика: всего {stats.total_applies} | "
            f"OK {stats.successful_applies} | "
            f"FAIL {stats.failed_applies} | "
            f"avg {stats.avg_duration_ms:.0f} ms"
        )

        if not filtered:
            self._view.show_history_entries(
                ["История применений пуста для выбранных фильтров."]
            )
            return

        lines: List[str] = []
        for entry in filtered[:200]:            # already newest-first from repo.list()
            state = "OK" if entry.success else "FAIL"
            lines.append(
                f"[{state}] {entry.timestamp} | {entry.profile_name} | "
                f"{entry.adapter} | {entry.duration_ms}ms"
            )
            if entry.error_message:
                lines.append(f"  Ошибка: {entry.error_message}")

        self._view.show_history_entries(lines)

    # ── Rollback ──────────────────────────────────────────────────

    def rollback(self, profile_name: Optional[str] = None) -> None:
        """Rollback to the last successful profile snapshot."""
        if self._view is None:
            return
        try:
            entries = self._repo.list(success_only=True)
            if profile_name:
                entries = [e for e in entries if e.profile_name == profile_name]
            if not entries:
                raise ValueError("Нет успешных записей для отката.")
            last = entries[0]                       # newest-first
            if last.previous_config is None:
                raise ValueError("Нет снимка предыдущей конфигурации.")

            # Delegate actual rollback to the container service (kept until Step 3+)
            self._container.profile_apply.rollback(last.id)
            self.refresh()
            self._view.show_message(
                "Откат выполнен",
                f"Восстановлена конфигурация из '{last.profile_name}'.",
            )
        except Exception as exc:
            self._view.show_message("Откат не выполнен", str(exc))

    # ── Internals ─────────────────────────────────────────────────

    @staticmethod
    def _compute_stats(entries: List[ProfileHistoryEntry]) -> HistoryStats:
        total = len(entries)
        ok = sum(1 for e in entries if e.success)
        avg_ms = sum(e.duration_ms for e in entries) / total if total else 0.0
        return HistoryStats(
            total_applies=total,
            successful_applies=ok,
            failed_applies=total - ok,
            avg_duration_ms=avg_ms,
        )
