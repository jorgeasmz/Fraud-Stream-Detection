"""Pushes each alert to whoever is watching, reading the same stream the sinks write."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from redis.asyncio import Redis as AsyncRedis

from stream.config import ALERT_STREAM, BLOCK_MS, REDIS_URL

log = logging.getLogger(__name__)


class Broadcaster:
    """Holds the open sockets and the reader task that feeds them."""

    def __init__(self, url: str = REDIS_URL, stream: str = ALERT_STREAM) -> None:
        self.url = url
        self.stream = stream
        self.clients: set = set()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._read())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    def register(self, socket) -> None:
        self.clients.add(socket)

    def unregister(self, socket) -> None:
        self.clients.discard(socket)

    async def _read(self) -> None:
        client = AsyncRedis.from_url(self.url)
        # Reading from "$" means a socket sees what arrives while it is open, not
        # the backlog, which the alerts endpoint serves instead.
        last = "$"
        try:
            while True:
                batches = await client.xread({self.stream: last}, count=50, block=BLOCK_MS)
                for _, messages in batches or ():
                    for message_id, raw in messages:
                        last = message_id
                        await self.publish(
                            {
                                key.decode(): value.decode()
                                for key, value in raw.items()
                            }
                        )
        except asyncio.CancelledError:
            raise
        finally:
            await client.aclose()

    async def publish(self, alert: dict[str, str]) -> None:
        stale = []
        for socket in list(self.clients):
            try:
                await socket.send_json(alert)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.unregister(socket)
