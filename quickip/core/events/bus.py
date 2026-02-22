"""Thread-safe event bus for application-wide event dispatching."""

import threading
import logging
from typing import Callable, Dict, List, Type

from quickip.core.events.types import AppEvent


logger = logging.getLogger(__name__)


class Subscription:
    """Event subscription handle – call .unsubscribe() to remove."""

    def __init__(
        self,
        event_type: Type[AppEvent],
        handler: Callable[[AppEvent], None],
        bus: "EventBus",
    ) -> None:
        self.event_type = event_type
        self.handler = handler
        self._bus = bus

    def unsubscribe(self) -> None:
        """Remove this subscription from the bus."""
        self._bus.unsubscribe(self)


class EventBus:
    """Thread-safe in-process event bus."""

    def __init__(self) -> None:
        self._handlers: Dict[Type[AppEvent], List[Callable]] = {}
        self._lock = threading.RLock()

    def subscribe(
        self,
        event_type: Type[AppEvent],
        handler: Callable[[AppEvent], None],
    ) -> Subscription:
        """Subscribe *handler* to events of *event_type*.

        Returns a Subscription handle for later unsubscribing.
        """
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)
                logger.debug(f"Subscribed {handler.__name__} to {event_type.__name__}")
        return Subscription(event_type, handler, self)

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove subscription returned by subscribe()."""
        with self._lock:
            handlers = self._handlers.get(subscription.event_type, [])
            try:
                handlers.remove(subscription.handler)
                logger.debug(
                    f"Unsubscribed {subscription.handler.__name__} "
                    f"from {subscription.event_type.__name__}"
                )
            except ValueError:
                pass

    def publish(self, event: AppEvent) -> None:
        """Publish *event* to all registered handlers."""
        event_type = type(event)
        with self._lock:
            handlers = self._handlers.get(event_type, []).copy()

        if not handlers:
            logger.debug(f"No handlers for {event_type.__name__}")
            return

        logger.debug(f"Publishing {event_type.__name__} to {len(handlers)} handler(s)")
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.error(
                    f"Handler {handler.__name__} failed for {event_type.__name__}: {exc}",
                    exc_info=True,
                )

    def clear(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            self._handlers.clear()
            logger.debug("Cleared all event subscriptions")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_event_bus: EventBus | None = None
_event_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Return the application-wide EventBus singleton."""
    global _event_bus
    if _event_bus is None:
        with _event_bus_lock:
            if _event_bus is None:
                _event_bus = EventBus()
    return _event_bus
