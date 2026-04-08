# Files Blockchain

Um motor de blockchain em Python construído do zero para gerenciar, auditar e registrar o compartilhamento seguro de arquivos em uma rede distribuída. 

Este projeto não armazena os arquivos pesados na cadeia (on-chain), mas atua como um **livro-razão imutável e descentralizado** de permissões de acesso, utilizando criptografia híbrida e um sistema econômico nativo para incentivar a manutenção da rede.

## Estrutura do Projeto

Atualmente, o projeto está focado no módulo de domínio (`core`), que contém as regras de negócio implacáveis da blockchain:

```text
├── core/
│   ├── transaction.py   # Modelagem de transações, taxas e assinaturas digitais
│   ├── block.py         # Estrutura do bloco, Árvore de Hashes e Proof of Work
│   ├── blockchain.py    # Orquestrador: Consenso global e Validações da Cadeia
├── miner/
│   ├── miner.py         # Worker de mineração, integra Kafka e Prova de Trabalho
│   ├── consensus.py     # Consenso Local, resolução de Forks e Regra de Finalização
│   ├── network.py       # Listeners, Broadcasters e manipulação com Apache Kafka
│   ├── mempool.py       # Seleção de transações na fila com prioridade por taxas
│   └── utils.py         # Classes de suporte e geração de chaves
├── gateway/
│   ├── main.py          # API FastAPI (SSE/WebSocket) para visualização em tempo real
│   ├── kafka_pump.py    # Consumer Kafka e broadcast para clientes conectados
│   ├── state.py         # Estado global em memória para snapshots e eventos
│   └── README.md        # Guia de execução e configuração do gateway
├── producer/
│   └── generator.py     # Simulador contínuo de tráfego de transações
├── tests/               # Suíte de testes unitários e de integração (pytest)
└── README.md
```

## Regras de Negócio e Arquitetura

O sistema foi desenhado com regras rígidas para garantir segurança, disponibilidade e alinhamento econômico entre os nós.

### 1. Compartilhamento de Arquivos (Criptografia Híbrida)
A blockchain atua como um cartório de acessos. O fluxo de compartilhamento segue a regra:
* **Off-chain:** O arquivo real é criptografado pelo remetente com uma chave simétrica (ex: AES) e hospedado externamente (ex: IPFS, AWS S3).
* **On-chain:** A transação registra o URI do arquivo e a chave simétrica **criptografada com a Chave Pública do destinatário**. Apenas o dono da Chave Privada correspondente consegue resgatar a chave e abrir o arquivo.

### 2. O Sistema Econômico
Para evitar ataques de *Spam/DDoS* e incentivar o processamento da rede, o sistema possui uma economia nativa baseada em "Tokens de Registro":
* **Taxas (Gas Fees):** Todo usuário que deseja registrar o compartilhamento de um arquivo deve pagar uma taxa (`fee`) estipulada na transação.
* **Recompensa do Minerador:** O nó que resolver o *Proof of Work* primeiro tem o direito de criar uma transação especial (Coinbase) injetada obrigatoriamente no índice `0` do bloco.
* **Matemática do Bloco:** A recompensa do minerador é estritamente fixada em: `Recompensa Base (5.0) + Soma das Taxas das transações do bloco`. Se um minerador cobrar um valor diferente, o bloco é sumariamente rejeitado pela rede.

### 3. Validação e Estado (Saldos)
O sistema não possui um banco de dados central com o saldo dos usuários.
* O saldo é calculado em tempo real varrendo o histórico imutável da cadeia (`get_balance`).
* Transações são rejeitadas e barradas da *Mempool* caso a assinatura digital (`cryptography`) seja inválida ou o remetente não possua saldo suficiente para cobrir a taxa (`fee`).

### 4. Consenso e Resolução de Conflitos (Forks)
Em um ambiente distribuído, divergências ocorrem. O Core implementa a regra da cadeia mais longa (*Longest Chain Rule*):
* Se um nó recebe uma cadeia válida e maior que a sua, ele substitui a cadeia local.
* **Recuperação de Órfãos:** Blocos descartados durante a resolução de um *fork* são auditados. Transações legítimas de usuários que estavam nesses blocos são devolvidas à *Mempool* para não haver perda de dados (acessos pendentes).

### 5. Imutabilidade e Encadeamento
* As propriedades críticas do bloco (`index`, `previous_hash`, `hash`) são atributos de leitura (*Read-Only*).
* Qualquer alteração em um dado histórico (como alterar a taxa de uma transação passada) altera o hash da transação, que por sua vez invalida o hash do bloco, quebrando a corrente criptográfica instantaneamente.

---

## Rodando os Testes

O Core é coberto por uma suíte rigorosa de testes orientada ao comportamento (TDD), garantindo que a matemática financeira e criptográfica funcione perfeitamente.

Para rodar as validações:
```bash
# Na raiz do projeto
python -m pytest -v tests/
```

---

## Camada de Rede e Integração
**[ Status: Gateway Kafka disponível ]**

A arquitetura de rede (Nodes) é responsável por:
* Disponibilizar uma API (HTTP/REST) para clientes enviarem transações e consultarem arquivos.
* Conectar os nós através de um *Message Broker* (ex: Apache Kafka) para realizar o *broadcast* de novos blocos e transações pendentes, garantindo o estado global do livro-razão.

### Gateway de Visualização (Kafka -> SSE/WebSocket)

Foi adicionado um gateway de visualização em `gateway/` que:
* Consome os tópicos Kafka de blocos, mempool e reorg.
* Mantém um estado local para geração de `chain_snapshot`.
* Publica eventos em tempo real para a interface via SSE e WebSocket.

Para executar:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r gateway/requirements.txt
cp gateway/.env.example .env
uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --reload
```

Consulte `gateway/README.md` para o contrato de eventos e variáveis de ambiente.

---

## Como Executar o Sistema Completo

Esta seção traz um passo a passo consolidado para subir toda a stack (Broker Kafka, Gateway API, Produtor de Tráfego, múltiplos Mineradores e o Painel Frontend).

### 1. Preparação Inicial e Arquivo `.env`

No diretório do backend (onde este arquivo está), crie e ative seu ambiente virtual (recomendado):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r gateway/requirements.txt
```

Atribua as variáveis de configuração primárias. Se for a primeira vez:
```bash
cp .env.example .env
```
*(O sistema carregará o `.env` automaticamente em sua base no `miner.py` e em outros modulos via `python-dotenv`.)*

### 2. Iniciando o Broker de Mensageria (Kafka)

Você precisará de um container Kafka operante para orquestrar as transações e blocos.
```bash
# Via compose:
docker-compose up -d broker

# Ou fallback direto:
docker rm -f broker >/dev/null 2>&1 || true
docker run -d --name broker -p 9092:9092 --restart unless-stopped apache/kafka:latest
```

### 3. Rodando a Stack (Terminais Isolados)

Execute cada um dos comandos abaixo em terminais separados. Sinta-se livre para ajustar `--difficulty` ou instanciar ainda mais mineradores conforme desejar avaliar simulações de "rede" e "forks".

**Terminal 1: Gateway e API de Streaming**
```bash
PYTHONPATH=. python3 -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2: Simulador/Produtor de Transações Contínuas**
```bash
PYTHONPATH=. python3 -m producer.generator
```

**Terminal 3: Minerador A (Janela de finalização default = 6, confira `.env`)**
```bash
PYTHONUNBUFFERED=1 PYTHONPATH=. MINER_ID=miner-a MINER_DIFFICULTY=5 python3 -m miner.miner
```

**Terminal 4: Minerador B**
```bash
PYTHONUNBUFFERED=1 PYTHONPATH=. MINER_ID=miner-b MINER_DIFFICULTY=5 python3 -m miner.miner
```

*(Sinta-se à vontade para executar Miners extras se tiver núcleos/concorrência para testes de Fork).*

**Terminal 5: Frontend Angular**
Abra o diretório do frontend e inicie a interface:
```bash
cd ../painel-blockchain-pow
npm install
npm start -- --host 0.0.0.0 --port 4200
```

Se tudo ocorreu bem, abra o navegador em `http://localhost:4200` para acompanhar a criação do grafo em tempo real e em `http://localhost:8000/docs` para visualizar a API do Gateway.

---

## Flags Avançadas do Minerador

Para sobrescrever qualquer configuração definida no `.env` globalmente, aplique as flags no processo do `miner.py`:

* Reajuste de dificuldade:
```bash
PYTHONPATH=. python3 -m miner.miner --difficulty 4
```
* Customização da janela de finalização (Quantidade restrita de nós antigos até a exclusão sumária. Ajuda contra ataques de *Time Warp* global):
```bash
PYTHONPATH=. python3 -m miner.miner --finalization-confirmations 10
```

---

## Interrompendo todos os serviços

Para encerrar o Backend, Miners, Gateway, e Frontend de forma massiva sem acessar os terminais individualmente:

```bash
pkill -f 'python3 -m uvicorn gateway.main:app' || true
pkill -f 'python3 -m producer.generator' || true
pkill -f 'python3 -m miner.miner' || true
pkill -f 'ng serve --host 0.0.0.0 --port 4200' || true
pkill -f 'npm start' || true

# Derrube o Kafka
docker rm -f broker >/dev/null 2>&1 || true
```
