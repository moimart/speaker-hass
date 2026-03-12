"""Simple async event bus for inter-component communication."""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class EventBus:
    """Publish-subscribe event bus using asyncio."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[..., Coroutine]]] = defaultdict(list)
        self._state: dict[str, Any] = {}

    def subscribe(self, event_type: str, callback: Callable[..., Coroutine]) -> None:
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[..., Coroutine]) -> None:
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)

    async def publish(self, event_type: str, data: Any = None) -> None:
        if event_type == "state.changed":
            self._state["current"] = data
        self._state[event_type] = data

        for callback in self._subscribers.get(event_type, []):
            try:
                await callback(event_type, data)
            except Exception:
                logger.exception("Error in event handler for %s", event_type)

    def get_state(self, key: str) -> Any:
        return self._state.get(key)
