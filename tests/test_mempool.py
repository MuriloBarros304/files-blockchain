import pytest
import time
from miner.mempool import Mempool

class MockTx:
    def __init__(self, tx_id, fee, timestamp=None, valid=True):
        self.tx_id = tx_id
        self.fee = fee
        self.timestamp = timestamp or time.time()
        self.valid = valid

    def validate(self):
        return self.valid

    def generate_hash(self):
        return self.tx_id

def test_mempool_initialization():
    mempool = Mempool(max_size=50)
    assert mempool.max_size == 50
    assert len(mempool) == 0

def test_add_tx():
    mempool = Mempool()
    tx = MockTx("tx1", 10.0)
    result = mempool.add_tx(tx)
    assert result is True
    assert len(mempool) == 1
    assert "tx1" in mempool.tx_map

def test_add_invalid_tx():
    mempool = Mempool()
    tx = MockTx("tx2", 10.0, valid=False)
    result = mempool.add_tx(tx)
    assert result is False
    assert len(mempool) == 0

def test_get_transactions():
    mempool = Mempool()
    mempool.add_tx(MockTx("tx1", 5.0))
    mempool.add_tx(MockTx("tx2", 20.0))
    mempool.add_tx(MockTx("tx3", 10.0))
    
    txs = mempool.get_transactions(max_count=2)
    assert len(txs) == 2
    assert txs[0].tx_id == "tx2"  # Highest fee
    assert txs[1].tx_id == "tx3"  # Second highest

def test_remove_transactions():
    mempool = Mempool()
    tx1 = MockTx("tx1", 5.0)
    tx2 = MockTx("tx2", 10.0)
    mempool.add_tx(tx1)
    mempool.add_tx(tx2)
    
    mempool.remove_transactions([tx1])
    assert len(mempool) == 1
    assert "tx2" in mempool.tx_map
