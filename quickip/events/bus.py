"""Thread-safe event bus for application-wide event dispatching."""

import threading
import logging
from typing import Callable, Dict, List, Type
from dataclasses import dataclass
from quickip.events.event_types import AppEvent


logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    """Event subscription handle."""
    event_type: Type[AppEvent]
    handler: Callable[[AppEvent], None]
    _bus: 'EventBus'

    def unsubscribe(self) -> None:
        """Unsubscribe from events."""
        self._bus.unsubscribe(self)


class EventBus:
    """Thread-safe in-process event bus."""

    def __init__(self):
        self._handlers: Dict[Type[AppEvent], List[Callable]] = {}
        self._lock = threading.RLock()

    def subscribe(
        self, 
        event_type: Type[AppEvent], 
        handler: Callable[[AppEvent], None]
    ) -> Subscription:
        """
        Subscribe to events of specific type.
        
        Args:
            event_type: Type of event to listen for
            handler: Callback function to handle event
            
        Returns:
            Subscription handle for unsubscribing
        """
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)
                logger.debug(f"Subscribed {handler.__name__} to {event_type.__name__}")
        
        return Subscription(event_type, handler, self)

    def unsubscribe(self, subscription: Subscription) -> None:
        """
        Unsubscribe from events.
        
        Args:
            subscription: Subscription handle returned from subscribe()
        """
        with self._lock:
            event_type = subscription.event_type
            handler = subscription.handler
            
            if event_type in self._handlers:
                try:
                    self._handlers[event_type].remove(handler)
                    logger.debug(f"Unsubscribed {handler.__name__} from {event_type.__name__}")
                except ValueError:
                    pass

    def publish(self, event: AppEvent) -> None:
        """
        Publish event to all subscribers.
        
        Args:
            event: Event instance to publish
        """
        event_type = type(event)
        
        # Get handlers snapshot to avoid holding lock during callbacks
        with self._lock:
            handlers = self._handlers.get(event_type, []).copy()
        
        if not handlers:
            logger.debug(f"No handlers for {event_type.__name__}")
            return
        
        logger.debug(f"Publishing {event_type.__name__} to {len(handlers)} handler(s)")
        
        # Call handlers without lock to prevent deadlocks
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Error in event handler {handler.__name__} "
                    f"for {event_type.__name__}: {e}",
                    exc_info=True
                )

    def clear(self) -> None:
        """Clear all subscriptions."""
        with self._lock:
            self._handlers.clear()
            logger.debug("Cleared all event subscriptions")


# Global event bus instance
_event_bus: EventBus | None = None
_event_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Get global event bus instance (singleton)."""
    global _event_bus
    
    if _event_bus is None:
        with _event_bus_lock:
            if _event_bus is None:
                _event_bus = EventBus()
    
    return _event_bus
