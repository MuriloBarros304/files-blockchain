from __future__ import annotations

import asyncio
from typing import Any


class EventBroadcaster:
    def __init__(self, queue_maxsize: int = 500) -> None:
        self._queue_maxsize = queue_maxsize
        self._clients: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self._counter = 0

    async def registrar_cliente(self) -> tuple[str, asyncio.Queue[dict[str, Any]]]:
        async with self._lock:
            self._counter += 1
            client_id = f'cliente-{self._counter}'
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_maxsize)
            self._clients[client_id] = queue
            return client_id, queue

    async def remover_cliente(self, client_id: str) -> None:
        async with self._lock:
            self._clients.pop(client_id, None)

    async def transmitir(self, event: dict[str, Any]) -> None:
        async with self._lock:
            for client_id, queue in list(self._clients.items()):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    self._clients.pop(client_id, None)

    async def quantidade_clientes(self) -> int:
        async with self._lock:
            return len(self._clients)
