"""History presenter – view/filter history, stats, rollback."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Protocol

from quickip.domain.models import ProfileHistoryEntry, HistoryStats

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)


# ── View contract ────────────────────────────────────────────────

class HistoryView(Protocol):
    """Callback interface for the history UI panel."""

    def show_history_entries(self, lines: List[str]) -> None:
        """Display formatted history lines in the text widget."""
        ...

    def show_history_stats(self, text: str) -> None:
        """Update the stats label."""
        ...

    def show_message(self, title: str, message: str) -> None:
        ...

    def get_history_search(self) -> str:
        """Return current search text."""
        ...

    def get_history_status_filter(self) -> str:
        """Return 'Все' | 'Успешные' | 'Ошибки'."""
        ...

    def refresh_related_panels(self) -> None:
        """Trigger refresh of home snapshot, profiles, etc."""
        ...


# ── Presenter ────────────────────────────────────────────────────

class HistoryPresenter:
    """Orchestrates history display, filtering, stats and rollback."""

    def __init__(self, container: "ServiceContainer", view: HistoryView) -> None:
        self.container = container
        self.view = view

    # ── Refresh ──────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload history from repo, apply filters, push to view."""
        entries = self.container.history_repo.list()
        query = self.view.get_history_search().strip().lower()
        status_filter = self.view.get_history_status_filter().strip()

        filtered: List[ProfileHistoryEntry] = []
        for entry in entries:
            if query and query not in entry.profile_name.lower():
                continue
            if status_filter == "Успешные" and not entry.success:
                continue
            if status_filter == "Ошибки" and entry.success:
                continue
            filtered.append(entry)

        # Stats
        stats = self._compute_stats(filtered)
        self.view.show_history_stats(
            f"Статистика: всего {stats.total_applies} | "
            f"OK {stats.successful_applies} | "
            f"FAIL {stats.failed_applies} | "
            f"avg {stats.avg_duration_ms:.0f} ms"
        )

        # Format entries (newest first, cap at 200)
        if not filtered:
            self.view.show_history_entries(
                ["История применений пока пуста для выбранных фильтров."]
            )
            return

        lines: List[str] = []
        for entry in reversed(filtered[-200:]):
            state = "OK" if entry.success else "FAIL"
            lines.append(
                f"[{state}] {entry.timestamp} | {entry.profile_name} | "
                f"{entry.adapter} | {entry.duration_ms}ms"
            )
            if entry.error_message:
                lines.append(f"  Ошибка: {entry.error_message}")

        self.view.show_history_entries(lines)

    # ── Rollback ─────────────────────────────────────────────────

    def rollback(self, profile_name: Optional[str] = None) -> None:
        """
        Rollback to the last successful profile snapshot.

        Args:
            profile_name: Optionally limit rollback to this profile.
        """
        try:
            entries = self.container.history_repo.list(success_only=True)
            if profile_name:
                entries = [e for e in entries if e.profile_name == profile_name]

            if not entries:
                raise ValueError("Нет успешных записей для отката.")

            last = entries[-1]
            if last.previous_config is None:
                raise ValueError("Нет сохранённого снимка предыдущей конфигурации.")

            # Re-apply previous config via profile_apply service
            result = self.container.profile_apply.rollback(last.id)

            self.refresh()
            self.view.refresh_related_panels()
            self.view.show_message(
                "Откат выполнен",
                f"Восстановлена конфигурация из записи '{last.profile_name}'.",
            )
        except Exception as exc:
            self.view.show_message("Откат не выполнен", str(exc))

    # ── Internals ────────────────────────────────────────────────

    @staticmethod
    def _compute_stats(entries: List[ProfileHistoryEntry]) -> HistoryStats:
        total = len(entries)
        success = sum(1 for e in entries if e.success)
        failed = total - success
        avg_ms = (
            sum(e.duration_ms for e in entries) / total if total > 0 else 0.0
        )
        return HistoryStats(
            total_applies=total,
            successful_applies=success,
            failed_applies=failed,
            avg_duration_ms=avg_ms,
        )
