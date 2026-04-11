import pytest
import asyncio
from gateway.broadcaster import EventBroadcaster

@pytest.mark.asyncio
async def test_broadcaster_lifecycle():
    broadcaster = EventBroadcaster(queue_maxsize=10)
    
    client_id, queue = await broadcaster.append_client()
    assert await broadcaster.quantidade_clientes() == 1
    
    await broadcaster.broadcast({'type': 'mempool_update', 'size': 99})
    
    event = await queue.get()
    assert event['type'] == 'mempool_update'
    assert event['size'] == 99
    
    await broadcaster.remove_client(client_id)
    assert await broadcaster.quantidade_clientes() == 0

@pytest.mark.asyncio
async def test_broadcaster_new_block_special_message():
    broadcaster = EventBroadcaster()
    client_id, queue = await broadcaster.append_client()
    
    await broadcaster.broadcast({'type': 'new_block', 'block': {'index': 42}})
    
    # The logic dictates it pushes a 'network_message' FIRST if it's a new_block
    msg_event = await queue.get()
    assert msg_event['type'] == 'network_message'
    assert '42' in msg_event['message']
    
    # Then it pushes the actual block event
    block_event = await queue.get()
    assert block_event['type'] == 'new_block'