# Gateway Kafka para Visualizacao

Gateway pronto para integrar Kafka com o painel de visualizacao da blockchain.

## O que este gateway faz

- Consome eventos Kafka dos topicos:
  - `blockchain.blocks`
  - `transactions_topic`
- Normaliza os payloads recebidos (`event` -> `type`, etc.).
- Mantem estado local da cadeia (blocos, mempool e status de cadeia principal).
- Faz broadcast para clientes por:
  - SSE: `/events/chain`
  - WebSocket: `/ws/chain`
- Envia `chain_snapshot` automaticamente quando um cliente conecta.
- Tenta reconectar automaticamente ao Kafka quando o broker fica indisponivel.

## Contrato de eventos para a UI

Eventos emitidos para o front:

- `chain_snapshot`
- `new_block`
- `mempool_update`
- `chain_reorg`

Estrutura base esperada para novo bloco:

```json
{
  "type": "new_block",
  "block": {
    "index": 10,
    "hash": "0000...",
    "previous_hash": "0000...",
    "nonce": 123,
    "tx_count": 4,
    "miner": "node-A",
    "is_main": true
  },
  "mempool_size": 17
}
```

## Como executar

Na raiz do repositorio:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r gateway/requirements.txt
cp gateway/.env.example .env
uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --reload
```

## Endpoints

- `GET /healthz` -> status do gateway
- `GET /snapshot` -> snapshot atual
- `GET /events/chain` -> stream SSE
- `WS /ws/chain` -> stream WebSocket

## Configuracoes por ambiente

Variaveis suportadas (em `.env`):

- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_GROUP_ID`
- `KAFKA_TOPIC_BLOCKS`
- `KAFKA_TOPIC_TRANSACTIONS`
- `KAFKA_AUTO_OFFSET_RESET`
- `KAFKA_RECONNECT_SECONDS`
- `KAFKA_SECURITY_PROTOCOL`
- `KAFKA_SASL_MECHANISM`
- `KAFKA_SASL_USERNAME`
- `KAFKA_SASL_PASSWORD`
- `CORS_ORIGINS` (separado por virgula)
- `SNAPSHOT_MAX_BLOCKS`
- `CLIENT_QUEUE_SIZE`
- `HEARTBEAT_SECONDS`
- `LOG_LEVEL`

## Integracao com o painel Angular

No painel, configure:

- SSE: `http://localhost:8000/events/chain`
- WebSocket: `ws://localhost:8000/ws/chain`

## Observacoes importantes

- O navegador nao deve conectar direto ao Kafka.
- Use `chain_id` como chave das mensagens nos produtores Kafka para manter ordenacao por particao.
- Para forks reais, publique `chain_reorg` ao aplicar regra de cadeia principal.
