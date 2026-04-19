#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR" || exit

export PYTHONPATH=.

# Ativa o ambiente virtual Python caso exista
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "====================================================="
echo "Iniciando Simulação de Gasto Duplo (Double Spend)..."
echo "====================================================="

python3 -m producer.double_spend
