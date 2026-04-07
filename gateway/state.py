from __future__ import annotations

import asyncio
from typing import Any


def _como_int(value: Any, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


class ChainState:
    def __init__(self, max_blocks: int = 2000) -> None:
        self._max_blocks = max_blocks
        self._blocks: dict[str, dict[str, Any]] = {}
        self._main_chain_hashes: set[str] = set()
        self._mempool_size = 0
        self._lock = asyncio.Lock()

    async def gerar_snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return self._snapshot_locked()

    async def aplicar_evento(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = event.get('type')
        if not isinstance(event_type, str):
            return None

        async with self._lock:
            if event_type == 'chain_snapshot':
                return self._aplicar_snapshot_locked(event)
            if event_type == 'new_block':
                return self._aplicar_novo_bloco_locked(event)
            if event_type == 'mempool_update':
                return self._aplicar_mempool_locked(event)
            if event_type == 'mempool_delta':
                return self._aplicar_mempool_delta_locked(event)
            if event_type == 'chain_reorg':
                return self._aplicar_reorg_locked(event)
            return None

    def _aplicar_snapshot_locked(self, event: dict[str, Any]) -> dict[str, Any] | None:
        raw_blocks = event.get('blocks')
        if not isinstance(raw_blocks, list):
            return None

        blocks = [block for raw in raw_blocks if (block := self._normalizar_bloco(raw))]
        self._blocks = {block['hash']: block for block in blocks}
        self._main_chain_hashes = {block['hash'] for block in blocks if block['is_main']}
        self._mempool_size = _como_int(event.get('mempool_size'), self._mempool_size) or 0
        self._podar_blocos_locked()
        return self._snapshot_locked()

    def _aplicar_novo_bloco_locked(self, event: dict[str, Any]) -> dict[str, Any] | None:
        raw_block = event.get('block') if isinstance(event.get('block'), dict) else event
        block = self._normalizar_bloco(raw_block)
        if block is None:
            return None

        mempool_size = _como_int(event.get('mempool_size'))
        if mempool_size is not None:
            self._mempool_size = mempool_size

        explicit_main = raw_block.get('is_main')
        if isinstance(explicit_main, bool):
            block['is_main'] = explicit_main
        else:
            parent = self._blocks.get(block['previous_hash'])
            tem_filho_principal = any(
                existing.get('previous_hash') == block['previous_hash'] and existing.get('is_main')
                for existing in self._blocks.values()
            )
            block['is_main'] = (
                block['hash'] in self._main_chain_hashes
                or block['previous_hash'] == '0'
                or bool(parent and parent.get('is_main') and not tem_filho_principal)
            )

        self._blocks[block['hash']] = block
        if block['is_main']:
            self._main_chain_hashes.add(block['hash'])
        self._podar_blocos_locked()

        return {'type': 'new_block', 'block': dict(block), 'mempool_size': self._mempool_size}

    def _aplicar_mempool_locked(self, event: dict[str, Any]) -> dict[str, Any] | None:
        mempool_size = _como_int(event.get('size'))
        if mempool_size is None:
            mempool_size = _como_int(event.get('mempool_size'))
        if mempool_size is None:
            return None

        self._mempool_size = mempool_size
        return {'type': 'mempool_update', 'size': self._mempool_size}

    def _aplicar_mempool_delta_locked(self, event: dict[str, Any]) -> dict[str, Any] | None:
        delta = _como_int(event.get('delta'), 1)
        if delta is None:
            return None

        self._mempool_size = max(0, self._mempool_size + delta)
        return {'type': 'mempool_update', 'size': self._mempool_size}

    def _aplicar_reorg_locked(self, event: dict[str, Any]) -> dict[str, Any] | None:
        raw_hashes = event.get('main_chain_hashes')
        if not isinstance(raw_hashes, list):
            return None

        hashes = [item for item in raw_hashes if isinstance(item, str)]
        self._main_chain_hashes = set(hashes)
        for block_hash, block in self._blocks.items():
            block['is_main'] = block_hash in self._main_chain_hashes

        new_tip = event.get('new_tip')
        if not isinstance(new_tip, str):
            new_tip = hashes[-1] if hashes else ''

        return {'type': 'chain_reorg', 'new_tip': new_tip, 'main_chain_hashes': hashes}

    def _normalizar_bloco(self, raw_block: Any) -> dict[str, Any] | None:
        if not isinstance(raw_block, dict):
            return None

        index = _como_int(raw_block.get('index'))
        block_hash = raw_block.get('hash')
        previous_hash = raw_block.get('previous_hash')
        if index is None or not isinstance(block_hash, str) or not block_hash or not isinstance(previous_hash, str):
            return None

        miner = raw_block.get('miner') if isinstance(raw_block.get('miner'), str) else 'n/d'
        is_main = raw_block.get('is_main') if isinstance(raw_block.get('is_main'), bool) else False
        return {
            'index': index,
            'hash': block_hash,
            'previous_hash': previous_hash,
            'nonce': _como_int(raw_block.get('nonce'), 0) or 0,
            'tx_count': _como_int(raw_block.get('tx_count'), 0) or 0,
            'miner': miner,
            'is_main': is_main,
        }

    def _podar_blocos_locked(self) -> None:
        if len(self._blocks) <= self._max_blocks:
            return

        keep = {
            block['hash']
            for block in sorted(
                self._blocks.values(),
                key=lambda item: (item.get('index', -1), item.get('hash', '')),
                reverse=True,
            )[: self._max_blocks]
        }
        self._blocks = {block_hash: block for block_hash, block in self._blocks.items() if block_hash in keep}
        self._main_chain_hashes.intersection_update(keep)

    def _snapshot_locked(self) -> dict[str, Any]:
        blocks = sorted(
            (dict(block) for block in self._blocks.values()),
            key=lambda item: (item.get('index', -1), item.get('hash', '')),
        )
        return {'type': 'chain_snapshot', 'mempool_size': self._mempool_size, 'blocks': blocks}