from __future__ import annotations

import asyncio
from typing import Any


class EventBroadcaster:
    def __init__(self, queue_maxsize: int = 500) -> None:
        self._queue_maxsize = queue_maxsize
        self._clients: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self._counter = 0

    async def append_client(self) -> tuple[str, asyncio.Queue[dict[str, Any]]]:
        async with self._lock:
            self._counter += 1
            client_id = f'cliente-{self._counter}'
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
                maxsize=self._queue_maxsize
                )
            self._clients[client_id] = queue
            return client_id, queue

    async def remove_client(self, client_id: str) -> None:
        async with self._lock:
            self._clients.pop(client_id, None)

    async def broadcast(self, event: dict[str, Any]) -> None:
        # Se for um novo bloco, trasnmite uma mensagem especial para a rede
        if event.get('type') == 'new_block':
            block_idx = event.get('block', {}).get('index', event.get('index', \
                                                                'Desconhecido'))
            message_event = {
                'type': 'network_message',
                'message': f'Um novo bloco (#{block_idx}) foi minerado!'
            }
            async with self._lock:
                for client_id, queue in list(self._clients.items()):
                    try:
                        queue.put_nowait(message_event)
                    except asyncio.QueueFull:
                        self._clients.pop(client_id, None)

        async with self._lock:
            for client_id, queue in list(self._clients.items()):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    self._clients.pop(client_id, None)

    async def quantidade_clientes(self) -> int:
        async with self._lock:
            return len(self._clients)
