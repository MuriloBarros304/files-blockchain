from __future__ import annotations

from typing import Any


def _tipo_evento(topic: str, payload: dict[str, Any]) -> str | None:
    for key in ('type', 'event'):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value

    if topic.endswith('blocks'):
        return 'new_block'
    if topic.endswith('transactions') or topic == 'transactions_topic':
        return 'transaction_received'
    return None


def _eh_payload_bloco(payload: dict[str, Any]) -> bool:
    index = payload.get('index')
    return (
        isinstance(index, int)
        and not isinstance(index, bool)
        and isinstance(payload.get('hash'), str)
        and isinstance(payload.get('previous_hash'), str)
    )


def normalizar_evento_kafka(topic: str, payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    event_type = _tipo_evento(topic, payload)

    if not event_type:
        return None

    normalized = dict(payload)
    normalized['type'] = event_type
    normalized.pop('event', None)

    if event_type == 'new_block':
        block = normalized.get('block')
        if not isinstance(block, dict):
            block = normalized.get('data')
        if isinstance(block, dict):
            normalized['block'] = block
            return normalized

        if _eh_payload_bloco(payload):
            return {
                'type': 'new_block',
                'block': payload,
                'mempool_size': payload.get('mempool_size'),
            }

        return None

    if event_type == 'mempool_update':
        if 'size' not in normalized and isinstance(normalized.get('mempool_size'), int):
            normalized['size'] = normalized['mempool_size']
        return normalized

    if event_type in {'transaction', 'new_transaction', 'transaction_received'}:
        if isinstance(normalized.get('mempool_size'), int):
            return {'type': 'mempool_update', 'size': normalized['mempool_size']}
        return {'type': 'mempool_delta', 'delta': 1, 'transaction': normalized}

    return normalized
