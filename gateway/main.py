from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import time
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.websockets import WebSocketState

from .broadcaster import EventBroadcaster
from .config import GatewaySettings
from .kafka_pump import KafkaEventPump
from .state import ChainState

load_dotenv()
settings = GatewaySettings.from_env()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
)
logger = logging.getLogger('gateway.main')

chain_state = ChainState(max_blocks=settings.snapshot_max_blocks)
broadcaster = EventBroadcaster(queue_maxsize=settings.client_queue_size)
kafka_pump = KafkaEventPump(settings, chain_state, broadcaster)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    await kafka_pump.iniciar()
    try:
        yield
    finally:
        await kafka_pump.parar()


app = FastAPI(
    title='Gateway Kafka de Visualizacao Blockchain',
    version='1.0.0',
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def _formatar_sse(event: dict[str, Any]) -> str:
    event_name = event.get('type', 'message')
    data = json.dumps(event, ensure_ascii=False)
    return f'event: {event_name}\ndata: {data}\n\n'


@app.get('/healthz')
async def healthz() -> dict[str, Any]:
    return {
        'status': 'ok',
        'kafka_consumindo': kafka_pump.em_execucao,
        'kafka_conectado': kafka_pump.kafka_conectado,
        'clientes_conectados': await broadcaster.quantidade_clientes(),
    }


@app.get('/snapshot')
async def snapshot() -> dict[str, Any]:
    return await chain_state.gerar_snapshot()


@app.get('/events/chain')
async def events_chain(request: Request) -> StreamingResponse:
    client_id, queue = await broadcaster.registrar_cliente()
    snapshot_event = await chain_state.gerar_snapshot()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            yield _formatar_sse(snapshot_event)

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=settings.heartbeat_seconds)
                    yield _formatar_sse(event)
                except asyncio.TimeoutError:
                    yield ': keepalive\n\n'
        finally:
            await broadcaster.remover_cliente(client_id)

    headers = {
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
    }
    return StreamingResponse(event_generator(), media_type='text/event-stream', headers=headers)


@app.websocket('/ws/chain')
async def ws_chain(websocket: WebSocket) -> None:
    await websocket.accept()

    client_id, queue = await broadcaster.registrar_cliente()

    try:
        await websocket.send_json(await chain_state.gerar_snapshot())

        while websocket.application_state == WebSocketState.CONNECTED:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=settings.heartbeat_seconds)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({'type': 'heartbeat', 'timestamp': int(time.time())})
    except WebSocketDisconnect:
        logger.info('Cliente websocket desconectado: %s', client_id)
    finally:
        await broadcaster.remover_cliente(client_id)
