import pytest
from gateway.normalizer import normalize_kafka_event

def test_normalize_kafka_event_new_block():
    payload = {
        'index': 1,
        'hash': 'hash1',
        'previous_hash': '0',
        'mempool_size': 5
    }
    result = normalize_kafka_event('blocks', payload)
    assert result is not None
    assert result['type'] == 'new_block'
    assert result['mempool_size'] == 5
    assert result['block'] == payload

def test_normalize_kafka_event_invalid_payload():
    result = normalize_kafka_event('blocks', "not a dict")
    assert result is None

def test_normalize_kafka_event_transaction():
    payload = {
        'type': 'new_transaction',
        'mempool_size': 10
    }
    result = normalize_kafka_event('transactions', payload)
    assert result is not None
    assert result['type'] == 'mempool_update'
    assert result['size'] == 10

def test_normalize_kafka_event_transaction_delta():
    payload = {
        'type': 'transaction',
        'id': 'tx1'
    }
    result = normalize_kafka_event('transactions', payload)
    assert result is not None
    assert result['type'] == 'mempool_delta'
    assert result['delta'] == 1
    assert result['transaction']['id'] == 'tx1'
