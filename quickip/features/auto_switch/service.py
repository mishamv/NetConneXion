"""AutoSwitchService — applies an IP profile automatically when a Wi-Fi SSID matches.

Subscribes to NetworkSsidChanged events and searches for a Profile with
matching auto_switch_ssid. On match: applies the profile via ProfileService,
fires AutoSwitchTriggered, and shows a toast notification.

⚠️  SECURITY NOTE — SSID-only matching:
  Auto-switch matches by Wi-Fi network name (SSID) only. SSID is not a
  cryptographically authenticated identifier: an attacker or rogue AP can
  broadcast any SSID (classic "evil twin" attack, T1557).

  This means a rogue AP named "MyCorpWiFi" near the user could trigger
  automatic application of a corporate IP profile (static IP, gateway, DNS).

  Mitigations to consider before using this in high-security environments:
    1. Require WPA2/WPA3-Enterprise auth (rogue APs can't complete 802.1X).
    2. Extend matching to include BSSID allowlist (store trusted BSSIDs per profile).
    3. Show a user-confirmation dialog on first match for each BSSID.
    4. Disable auto-switch on open or WPA-Personal networks.

  For corporate-grade deployment, option 2+3 is strongly recommended.
  The current implementation is appropriate for home/office environments where
  the risk of a targeted evil twin attack is low.

Edge cases handled:
  - Multiple profiles with the same SSID → applies the first match (list order).
  - Empty SSID (disconnect) → no action taken.
  - Profile apply failure → logs error, fires no AutoSwitchTriggered event.
  - auto_switch cooldown: won't re-apply the same profile for 60s after success
    (prevents thrashing on unstable connections).

MITRE ATT&CK:
  - T1557 (Adversary-in-the-Middle / Evil Twin) — known limitation above.
  - T1078 (Valid Accounts) — ensures correct IP config for sensitive networks.
  - D3FEND D3-NTA — network state awareness.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, TYPE_CHECKING

from quickip.core.events.types import NetworkSsidChanged, AutoSwitchTriggered

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer
    from quickip.events.bus import Subscription

logger = logging.getLogger(__name__)

_COOLDOWN_SECONDS = 60.0  # не применять тот же профиль повторно N секунд


class AutoSwitchService:
    """Listens for SSID changes and applies matching IP profiles.

    Args:
        container: DI-контейнер.
    """

    def __init__(self, container: "ServiceContainer") -> None:
        self._container = container
        self._subscription: Optional["Subscription"] = None
        # cooldown: {profile_id: timestamp последнего успешного apply}
        self._last_applied: dict[str, float] = {}

    # ── Public API ────────────────────────────────────────────────

    def start(self) -> None:
        """Подписаться на события SSID-изменений."""
        self._subscription = self._container.event_bus.subscribe(
            NetworkSsidChanged, self._on_ssid_changed
        )
        logger.info("AutoSwitchService started")

    def stop(self) -> None:
        """Отписаться от событий."""
        if self._subscription:
            self._subscription.unsubscribe()
            self._subscription = None
        logger.info("AutoSwitchService stopped")

    # ── Internal ──────────────────────────────────────────────────

    def _on_ssid_changed(self, event: NetworkSsidChanged) -> None:
        """Обработчик события NetworkSsidChanged."""
        if not event.connected or not event.ssid:
            logger.debug("AutoSwitch: ignoring disconnect event")
            return

        profile = self._find_matching_profile(event.ssid)
        if profile is None:
            logger.debug("AutoSwitch: no profile for SSID=%r", event.ssid)
            return

        # Cooldown: не применять тот же профиль слишком часто
        last = self._last_applied.get(profile.id, 0.0)
        if time.monotonic() - last < _COOLDOWN_SECONDS:
            logger.debug(
                "AutoSwitch: cooldown active for profile %r (%.0fs ago)",
                profile.name, time.monotonic() - last,
            )
            return

        logger.info(
            "AutoSwitch: SSID=%r → applying profile %r on adapter=%r",
            event.ssid, profile.name, profile.adapter,
        )
        self._apply_profile(profile, event.ssid)

    def _find_matching_profile(self, ssid: str):
        """Находит первый Profile с auto_switch_ssid == ssid."""
        try:
            profiles = self._container.profile_repo.list()
        except Exception:
            logger.exception("AutoSwitch: failed to load profiles")
            return None
        for p in profiles:
            if p.auto_switch_ssid and p.auto_switch_ssid == ssid:
                return p
        return None

    def _apply_profile(self, profile, ssid: str) -> None:
        """Применяет профиль и публикует событие AutoSwitchTriggered."""
        from quickip.features.profiles.service import ProfileService
        try:
            svc = ProfileService(self._container)
            result = svc.apply(profile)
        except Exception:
            logger.exception("AutoSwitch: exception during profile apply")
            return

        if result.success:
            self._last_applied[profile.id] = time.monotonic()
            self._container.event_bus.publish(AutoSwitchTriggered(  # type: ignore[arg-type]
                profile_id=profile.id,
                profile_name=profile.name,
                ssid=ssid,
            ))
            # Toast уведомление (best-effort).
            # ⚠️ Совпадение только по SSID — без проверки BSSID.
            # Для повышения безопасности в будущем добавить BSSID allowlist.
            try:
                self._container.toast.show(
                    title="Профиль применён автоматически",
                    message=(
                        f"Wi-Fi: {ssid}\nПрофиль: {profile.name}\n"
                        "⚠ Совпадение только по имени сети."
                    ),
                )
            except Exception:
                pass
        else:
            logger.error(
                "AutoSwitch: failed to apply profile %r: %s",
                profile.name, result.error,
            )
