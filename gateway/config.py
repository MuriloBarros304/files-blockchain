from __future__ import annotations

from dataclasses import dataclass, field
import os


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return default

    parts = [item.strip() for item in value.split(',') if item.strip()]
    return parts or default


@dataclass(frozen=True)
class GatewaySettings:
    kafka_bootstrap_servers: str = 'localhost:9092'
    kafka_group_id: str = 'gateway-visualizacao'
    kafka_topic_blocks: str = 'blockchain.blocks'
    kafka_topic_transactions: str = 'transactions_topic'
    kafka_auto_offset_reset: str = 'latest'
    kafka_reconnect_seconds: int = 5
    kafka_security_protocol: str = 'PLAINTEXT'
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: str | None = None

    cors_origins: list[str] = field(default_factory=lambda: ['*'])

    snapshot_max_blocks: int = 2000
    client_queue_size: int = 500
    heartbeat_seconds: int = 15
    log_level: str = 'INFO'

    @classmethod
    def from_env(cls) -> 'GatewaySettings':
        return cls(
            kafka_bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
            kafka_group_id=os.getenv('KAFKA_GROUP_ID', 'gateway-visualizacao'),
            kafka_topic_blocks=os.getenv('KAFKA_TOPIC_BLOCKS', 'blockchain.blocks'),
            kafka_topic_transactions=os.getenv('KAFKA_TOPIC_TRANSACTIONS', 'transactions_topic'),
            kafka_auto_offset_reset=os.getenv('KAFKA_AUTO_OFFSET_RESET', 'latest'),
            kafka_reconnect_seconds=int(os.getenv('KAFKA_RECONNECT_SECONDS', '5')),
            kafka_security_protocol=os.getenv('KAFKA_SECURITY_PROTOCOL', 'PLAINTEXT'),
            kafka_sasl_mechanism=os.getenv('KAFKA_SASL_MECHANISM'),
            kafka_sasl_username=os.getenv('KAFKA_SASL_USERNAME'),
            kafka_sasl_password=os.getenv('KAFKA_SASL_PASSWORD'),
            cors_origins=_split_csv(os.getenv('CORS_ORIGINS'), ['*']),
            snapshot_max_blocks=int(os.getenv('SNAPSHOT_MAX_BLOCKS', '2000')),
            client_queue_size=int(os.getenv('CLIENT_QUEUE_SIZE', '500')),
            heartbeat_seconds=int(os.getenv('HEARTBEAT_SECONDS', '15')),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
        )
