#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR" || exit

echo "Iniciando infraestrutura do Kafka..."

# Encerra processos backend anteriores para evitar conflitos de porta
pkill -f "miner.miner"
pkill -f "gateway.main:app"
pkill -f "producer.generator"

# Recria os contêineres limpos
docker compose down -v
docker compose up -d

# Aguarda o Kafka responder na porta 9092 usando socket nativo do Bash
echo "Aguardando o Kafka inicializar na porta 9092..."
while ! bash -c 'true < /dev/tcp/localhost/9092' 2>/dev/null; do
    sleep 1
done

# TEMPO DE ESPERA CRÍTICO: Dá tempo para a JVM do Kafka carregar internamente
# Isso evita que o uvicorn (Gateway) crashe com "NoBrokersAvailable"
echo "Porta 9092 aberta. Aguardando a JVM do Kafka inicializar (10s)..."
sleep 10
echo "Kafka está pronto!"

# Função para limpar processos filhos quando o script for encerrado (Ctrl+C)
cleanup() {
    echo -e "\nEncerrando simulação do backend e limpando processos..."
    pkill -P $$
    docker compose -f "$SCRIPT_DIR/docker-compose.yaml" down
    exit 0
}
trap cleanup SIGINT SIGTERM

# Variáveis de ambiente compartilhadas
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export KAFKA_TOPIC_BLOCKS=blocks
export KAFKA_TOPIC_TRANSACTIONS=transactions
export PYTHONUNBUFFERED=1
export PYTHONPATH=.

# Ativa o ambiente virtual Python caso exista
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "Iniciando a API Gateway..."
python3 -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000 &

echo "Iniciando os Mineradores (Dificuldade 6)..."
MINER_ID=miner-a MINER_DIFFICULTY=6 python3 -m miner.miner &
MINER_ID=miner-b MINER_DIFFICULTY=6 python3 -m miner.miner &
MINER_ID=miner-c MINER_DIFFICULTY=6 python3 -m miner.miner &
MINER_ID=miner-d MINER_DIFFICULTY=6 python3 -m miner.miner &

echo "Iniciando o Produtor de Transações aleatórias (Seed 50)..."
python3 -m producer.generator --seed 50 &

echo "Iniciando o Painel Blockchain PoW..."
(cd "$SCRIPT_DIR/../painel-blockchain-pow" && npm start) &
(sleep 5 && google-chrome http://localhost:4200) &

echo "====================================================="
echo "Simulação completa iniciada com sucesso!"
echo "Acesse a API Gateway em: http://localhost:8000"
echo "Acesse o Frontend em http://localhost:4200"
echo "Para encerrar completamente os processos, aperte Ctrl+C."
echo "====================================================="

# Espera os processos rodarem em segundo plano
wait

