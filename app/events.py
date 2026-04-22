from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Any, Callable

from loguru import logger

EventCallback = Callable[[dict[str, Any]], None]


class EventBus:
    """Thread-safe in-process event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventCallback]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, event_name: str, callback: EventCallback) -> Callable[[], None]:
        with self._lock:
            self._subscribers[event_name].append(callback)
            logger.debug("Subscribed callback to event {}", event_name)

        def unsubscribe() -> None:
            with self._lock:
                callbacks = self._subscribers.get(event_name)
                if not callbacks:
                    return
                if callback in callbacks:
                    callbacks.remove(callback)
                    logger.debug("Unsubscribed callback from event {}", event_name)

        return unsubscribe

    def publish(self, event_name: str, payload: dict[str, Any] | None = None) -> None:
        event_payload = payload or {}
        with self._lock:
            callbacks = list(self._subscribers.get(event_name, []))

        logger.debug("Publishing event {} with payload keys {}", event_name, list(event_payload.keys()))
        for callback in callbacks:
            try:
                callback(event_payload)
            except Exception:
                logger.exception("Event callback failed for {}", event_name)
