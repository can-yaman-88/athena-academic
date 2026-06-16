"""Process-wide live log bus for streaming logs to the dashboard.

A single :class:`LogBus` keeps a bounded ring buffer of recent records and
fan-outs every new record to any number of async subscribers (each backed by its
own :class:`asyncio.Queue`). A :class:`logging.Handler` (``LogBusHandler``)
attached to the ``"jarvis"`` logger feeds the bus, so anything the backend or the
PDF engine logs becomes available at ``GET /logs/stream`` in real time.

The handler is sync (logging calls are sync) but the bus is consumed from async
endpoints, so the handler schedules the fan-out onto the running event loop when
one is available, and otherwise just keeps the record in the ring buffer.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Optional


class LogBus:
    """Ring buffer + async pub/sub for structured log records."""

    def __init__(self, capacity: int = 500) -> None:
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the event loop used to schedule thread-safe fan-out."""
        self._loop = loop

    def recent(self, n: int = 100) -> list[dict[str, Any]]:
        return list(self._buffer)[-n:]

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)

    def publish(self, record: dict[str, Any]) -> None:
        """Append to the buffer and fan-out to subscribers (loop-safe)."""
        self._buffer.append(record)

        def _deliver() -> None:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(record)
                except asyncio.QueueFull:  # slow consumer: drop the oldest, retry
                    try:
                        q.get_nowait()
                        q.put_nowait(record)
                    except Exception:
                        pass

        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(_deliver)
                return
            except RuntimeError:
                pass
        # No running loop bound (e.g. import-time logging): buffer only.


class LogBusHandler(logging.Handler):
    """A logging handler that forwards records to a :class:`LogBus`."""

    def __init__(self, bus: LogBus) -> None:
        super().__init__()
        self._bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # "jarvis.pdf_engine.ai" -> stage "pdf_engine.ai"
            name = record.name
            stage = name.split(".", 1)[1] if "." in name else name
            self._bus.publish(
                {
                    "ts": time.time(),
                    "level": record.levelname,
                    "stage": stage,
                    "message": record.getMessage(),
                }
            )
        except Exception:  # logging must never crash the app
            pass


__all__ = ["LogBus", "LogBusHandler"]
