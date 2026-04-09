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

echo "Aguardando 15 segundos para o Kafka inicializar..."
sleep 15

# Função para limpar processos filhos quando o script for encerrado (Ctrl+C)
cleanup() {
    echo "Encerrando simulação e limpando processos..."
    pkill -P $$
    docker-compose down
    exit 0
}
trap cleanup SIGINT SIGTERM

# Variáveis de ambiente compartilhadas
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export KAFKA_TOPIC_BLOCKS=blocks
export KAFKA_TOPIC_TRANSACTIONS=transactions
export PYTHONUNBUFFERED=1
export PYTHONPATH=.

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

# Aguarda 5 segundos para o frontend compilar e depois abre no navegador
(sleep 5 && python3 -m webbrowser "http://localhost:4200" 2>/dev/null) &

# Espera os processos rodarem em segundo plano
wait
