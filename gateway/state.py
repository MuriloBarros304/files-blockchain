from __future__ import annotations

import asyncio
from typing import Any


def _como_int(value: Any, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _zeros_iniciais(hash_value: str) -> int:
    zeros = 0
    for char in hash_value:
        if char != '0':
            break
        zeros += 1
    return zeros


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
        self._garantir_genesis_para_cadeia_locked()
        self._recalcular_cadeia_principal_locked()
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

        self._garantir_genesis_para_bloco_locked(block)
        parent = self._blocks.get(block['previous_hash'])
        if block['previous_hash'] != '0' and parent is None:
            return None

        explicit_main = raw_block.get('is_main')
        block['is_main'] = bool(explicit_main) if isinstance(explicit_main, bool) else False

        self._blocks[block['hash']] = block
        self._recalcular_cadeia_principal_locked()
        self._podar_blocos_locked()

        updated_block = self._blocks.get(block['hash'], block)
        return {
            'type': 'new_block',
            'block': dict(updated_block),
            'mempool_size': self._mempool_size,
            'main_chain_hashes': list(self._main_chain_hashes),
        }

    def _criar_genesis_sintetico_locked(self, genesis_hash: str) -> None:
        if not genesis_hash or genesis_hash in self._blocks:
            return

        self._blocks[genesis_hash] = {
            'index': 0,
            'hash': genesis_hash,
            'previous_hash': '0',
            'nonce': 0,
            'tx_count': 0,
            'miner': 'GENESIS',
            'is_main': True,
        }
        self._main_chain_hashes.add(genesis_hash)

    def _garantir_genesis_para_bloco_locked(self, block: dict[str, Any]) -> None:
        if block.get('index') != 1:
            return

        previous_hash = block.get('previous_hash')
        if not isinstance(previous_hash, str) or previous_hash == '0':
            return

        if previous_hash not in self._blocks:
            self._criar_genesis_sintetico_locked(previous_hash)

    def _garantir_genesis_para_cadeia_locked(self) -> None:
        for block in list(self._blocks.values()):
            self._garantir_genesis_para_bloco_locked(block)

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

    def _recalcular_cadeia_principal_locked(self) -> None:
        if not self._blocks:
            self._main_chain_hashes.clear()
            return

        hashes_pais = {
            block.get('previous_hash')
            for block in self._blocks.values()
            if isinstance(block.get('previous_hash'), str) and block.get('previous_hash') != '0'
        }

        pontas = [
            block
            for block_hash, block in self._blocks.items()
            if block_hash not in hashes_pais
        ]
        if not pontas:
            pontas = list(self._blocks.values())

        melhor_ponta = max(
            pontas,
            key=lambda item: (
                item.get('index', -1),
                _zeros_iniciais(item.get('hash', '')),
                item.get('hash', ''),
            ),
        )

        caminho_hashes: list[str] = []
        visitados: set[str] = set()
        atual = melhor_ponta

        while atual and isinstance(atual.get('hash'), str):
            atual_hash = atual['hash']
            if atual_hash in visitados:
                break

            visitados.add(atual_hash)
            caminho_hashes.append(atual_hash)

            previous_hash = atual.get('previous_hash')
            if not isinstance(previous_hash, str) or previous_hash == '0':
                break

            atual = self._blocks.get(previous_hash)

        self._main_chain_hashes = set(caminho_hashes)
        for block_hash, block in self._blocks.items():
            block['is_main'] = block_hash in self._main_chain_hashes

    def _snapshot_locked(self) -> dict[str, Any]:
        blocks = sorted(
            (dict(block) for block in self._blocks.values()),
            key=lambda item: (item.get('index', -1), item.get('hash', '')),
        )
        return {'type': 'chain_snapshot', 'mempool_size': self._mempool_size, 'blocks': blocks}