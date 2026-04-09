#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR" || exit

echo "Iniciando simulação de ataque de Gasto Duplo (Double Spend)..."

KAFKA_BOOTSTRAP_SERVERS=localhost:9092 PYTHONUNBUFFERED=1 PYTHONPATH=. python3 -m producer.double_spend
