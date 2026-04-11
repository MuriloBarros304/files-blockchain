import pytest
import asyncio
from gateway.state import ChainState

@pytest.mark.asyncio
async def test_chain_state_snapshot_and_genesis_mock():
    state = ChainState(max_blocks=10)
    
    event = {
        'type': 'new_block',
        'block': {
            'index': 1,
            'hash': 'hash_do_bloco_1',
            'previous_hash': 'hash_genesis',
            'is_main': True
        },
        'mempool_size': 15
    }
    
    result = await state.apply_event(event)
    assert result['mempool_size'] == 15
    
    snapshot = await state.generate_snapshot()
    
    # Because the index is 1 and previous_hash is not '0', 
    # the state manager should automatically create a mock genesis block.
    assert len(snapshot['blocks']) == 2
    hashes = [b['hash'] for b in snapshot['blocks']]
    assert 'hash_genesis' in hashes
    assert 'hash_do_bloco_1' in hashes

@pytest.mark.asyncio
async def test_mempool_delta_updates():
    state = ChainState()
    
    await state.apply_event({'type': 'mempool_delta', 'delta': 5})
    snapshot = await state.generate_snapshot()
    assert snapshot['mempool_size'] == 5
    
    # Simulating transactions being packed into a block (mempool shrinks)
    await state.apply_event({'type': 'mempool_delta', 'delta': -2})
    snapshot = await state.generate_snapshot()
    assert snapshot['mempool_size'] == 3