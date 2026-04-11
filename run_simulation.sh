#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR" || exit

echo "Iniciando infraestrutura do Kafka..."

# Encerra processos anteriores para evitar conflitos
pkill -f "miner.miner"
pkill -f "gateway.main:app"
pkill -f "producer.generator"

# Recria os contêineres limpos
docker-compose down -v
docker-compose up -d

# Aguarda o Kafka responder na porta 9092 em vez de um sleep fixo
echo "Aguardando o Kafka inicializar na porta 9092..."
while ! nc -z localhost 9092; do   
  sleep 1 
done
echo "Kafka está pronto!"

# Função para limpar processos filhos quando o script for encerrado (Ctrl+C)
cleanup() {
    echo "Encerrando simulação e limpando processos..."
    pkill -P $$
    # FIX: Aponta diretamente para o compose file usando caminho absoluto
    docker-compose -f "$SCRIPT_DIR/docker-compose.yml" down
    exit 0
}
trap cleanup SIGINT SIGTERM

# Variáveis de ambiente compartilhadas
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export KAFKA_TOPIC_BLOCKS=blocks
export KAFKA_TOPIC_TRANSACTIONS=transactions
export PYTHONUNBUFFERED=1
export PYTHONPATH=.

# Ativa o ambiente virtual Python caso exista no SCRIPT_DIR
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "Iniciando a API Gateway..."
python3 -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000 &

echo "Iniciando os Mineradores (Dificuldade 5)..."
MINER_ID=miner-a MINER_DIFFICULTY=5 python3 -m miner.miner &
MINER_ID=miner-b MINER_DIFFICULTY=5 python3 -m miner.miner &
MINER_ID=miner-c MINER_DIFFICULTY=5 python3 -m miner.miner &

echo "Iniciando o Produtor de Transações (Seed 50)..."
python3 -m producer.generator --seed 50 &

echo "Iniciando o Painel Frontend..."
# Navega até o diretório do front e sobe o servidor Angular
cd "../painel-blockchain-pow" || exit

# Carrega o NVM para o npm funcionar no script bash não interativo
if [ -f "$HOME/.nvm/nvm.sh" ]; then
    source "$HOME/.nvm/nvm.sh"
fi
npm start -- --host 0.0.0.0 --port 4200 &

echo "====================================================="
echo "Simulação iniciada com sucesso!"
echo "Acesse o painel em: http://localhost:4200"
echo "Acesse a API em: http://localhost:8000"
echo "Para encerrar completamente os processos, aperte Ctrl+C."
echo "====================================================="

# Aumentado para 15 segundos para dar tempo ao Angular de compilar
(sleep 15 && python3 -m webbrowser "http://localhost:4200" 2>/dev/null) &

# Espera os processos rodarem em segundo plano
wait