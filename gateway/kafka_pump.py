from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer

from .broadcaster import EventBroadcaster
from .config import GatewaySettings
from .normalizer import normalizar_evento_kafka
from .state import ChainState

logger = logging.getLogger(__name__)


class KafkaEventPump:
    def __init__(self, settings: GatewaySettings, chain_state: ChainState, broadcaster: EventBroadcaster) -> None:
        self._settings = settings
        self._chain_state = chain_state
        self._broadcaster = broadcaster
        self._consumer: AIOKafkaConsumer | None = None
        self._runner_task: asyncio.Task[None] | None = None
        self._kafka_conectado = False

    @property
    def em_execucao(self) -> bool:
        return self._runner_task is not None and not self._runner_task.done()

    @property
    def kafka_conectado(self) -> bool:
        return self._kafka_conectado

    async def iniciar(self) -> None:
        if not self.em_execucao:
            self._runner_task = asyncio.create_task(self._executar_com_reconexao(), name='kafka-gateway-runner')

    async def parar(self) -> None:
        if self._runner_task is not None:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
            self._runner_task = None
        await self._desconectar_consumer()

    async def _executar_com_reconexao(self) -> None:
        while True:
            try:
                await self._conectar_consumer()
                await self._loop_consumo()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('Falha no loop de consumo Kafka; nova tentativa em %ss', self._settings.kafka_reconnect_seconds)
            finally:
                await self._desconectar_consumer()
            await asyncio.sleep(self._settings.kafka_reconnect_seconds)

    async def _conectar_consumer(self) -> None:
        if self._consumer is not None:
            return

        kwargs = {
            'bootstrap_servers': self._settings.kafka_bootstrap_servers,
            'group_id': self._settings.kafka_group_id,
            'auto_offset_reset': self._settings.kafka_auto_offset_reset,
            'enable_auto_commit': True,
            'security_protocol': self._settings.kafka_security_protocol,
        }
        for key, value in (
            ('sasl_mechanism', self._settings.kafka_sasl_mechanism),
            ('sasl_plain_username', self._settings.kafka_sasl_username),
            ('sasl_plain_password', self._settings.kafka_sasl_password),
        ):
            if value:
                kwargs[key] = value

        topics = list(
            dict.fromkeys(
                topic
                for topic in (
                    self._settings.kafka_topic_blocks,
                    self._settings.kafka_topic_transactions,
                )
                if topic
            )
        )

        self._consumer = AIOKafkaConsumer(
            *topics,
            **kwargs,
        )
        await self._consumer.start()
        self._kafka_conectado = True
        logger.info('Kafka consumer conectado ao broker %s', self._settings.kafka_bootstrap_servers)

    async def _desconectar_consumer(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            logger.info('Kafka consumer finalizado')
            self._consumer = None
        self._kafka_conectado = False

    async def _loop_consumo(self) -> None:
        assert self._consumer is not None
        async for message in self._consumer:
            try:
                payload = self._decode_payload(message.value)
                if payload is None:
                    continue

                event = normalizar_evento_kafka(message.topic, payload)
                if event is None:
                    continue

                applied_event = await self._chain_state.aplicar_evento(event)
                if applied_event is None:
                    continue

                applied_event.update(
                    {
                        'source_topic': message.topic,
                        'source_partition': message.partition,
                        'source_offset': message.offset,
                    }
                )
                await self._broadcaster.transmitir(applied_event)
            except Exception:
                logger.exception('Falha ao processar mensagem Kafka')

    def _decode_payload(self, value: bytes | Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if not isinstance(value, (bytes, bytearray)):
            logger.warning('Mensagem Kafka ignorada: payload nao suportado')
            return None

        try:
            parsed = json.loads(value.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning('Mensagem Kafka ignorada: JSON invalido')
            return None

        if not isinstance(parsed, dict):
            logger.warning('Mensagem Kafka ignorada: payload nao e objeto JSON')
            return None
        return parsed