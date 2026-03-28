"""
Teste de unidade e integração para a classe Blockchain, cobrindo:
- Inicialização da cadeia e bloco gênese
- Adição de transações e blocos, incluindo validação de transações e recompensas
- Cálculo de saldo para endereços, considerando taxas e recompensas
- Validação de cadeias e consenso, incluindo recuperação de blocos órfãos e detecção de fraudes em recompensas de mineradores
"""

import pytest
from unittest.mock import patch
from core.blockchain import Blockchain
from core.block import Block
from core.transaction import Transaction

@pytest.fixture
def blockchain():
    """Fixture que cria uma nova blockchain "limpa" para cada teste."""
    return Blockchain()

@pytest.fixture
def mock_transaction():
    """Fixture que cria uma transação básica com taxa de 1.0 para testes."""
    return Transaction(
        "remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_cripto",
        signature="assinatura", fee=1.0
    )


def test_blockchain_initialization(blockchain):
    # A cadeia deve inicializar com exatamente 1 bloco (O Gênese)
    assert len(blockchain.chain) == 1
    assert blockchain.chain[0].index == 0
    assert blockchain.chain[0].previous_hash == '0'

def test_difficulty_property_validation(blockchain):
    # Testa se o setter bloqueia tipos incorretos
    with pytest.raises(ValueError, match="Dificuldade deve ser um inteiro"):
        blockchain.difficulty = "3" # Tipo string ao invés de int

# --- TESTES DE TRANSAÇÃO E ECONOMIA ---

@patch('transaction.Transaction.validate', return_value=True)
@patch.object(Blockchain, 'get_balance', return_value=10.0) # Mocka o saldo para ter fundos
def test_add_transaction_success(mock_balance, mock_validate, blockchain, mock_transaction):
    # Se a transação for válida e houver saldo, deve entrar na mempool
    blockchain.add_transaction(mock_transaction)
    assert len(blockchain.mempool) == 1
    assert mock_transaction in blockchain.mempool

@patch('transaction.Transaction.validate', return_value=True)
@patch.object(Blockchain, 'get_balance', return_value=0.0) # Mocka o saldo para ZERO
def test_add_transaction_insufficient_funds(mock_balance, mock_validate, blockchain, mock_transaction):
    # Se não houver saldo suficiente para pagar a taxa, deve ser rejeitada
    with pytest.raises(Exception, match="Saldo insuficiente"):
        blockchain.add_transaction(mock_transaction)

@patch('transaction.Transaction.validate', return_value=False)
def test_add_transaction_invalid_signature(mock_validate, blockchain, mock_transaction):
    # Se a assinatura for inválida, deve levantar exceção imediatamente
    with pytest.raises(Exception, match="Transação inválida"):
        blockchain.add_transaction(mock_transaction)


# --- TESTES DE SALDO REAIS (INTEGRAÇÃO) ---

@patch('transaction.Transaction.validate', return_value=True)
def test_get_balance_calculation(mock_validate, blockchain):
    """Teste de integração avançado: Simula a economia fluindo entre Alice e Bob"""
    
    # 1. Alice minera um bloco vazio (Ganha 5.0 da recompensa base)
    block1 = Block(1, [], blockchain.get_latest_block().hash)
    block1.mine_block(blockchain.difficulty, miner_address="Alice")
    blockchain.add_block(block1)
    
    assert blockchain.get_balance("Alice") == 5.0
    
    # 2. Alice cria uma transação pagando 1.5 de taxa
    tx_alice = Transaction("Alice", "Bob", "uri", "key", "sig", fee=1.5)
    blockchain.add_transaction(tx_alice)
    
    # 3. Bob minera um bloco contendo a transação da Alice
    block2 = Block(2, [tx_alice], blockchain.get_latest_block().hash)
    block2.mine_block(blockchain.difficulty, miner_address="Bob")
    blockchain.add_block(block2)
    
    # 4. Auditoria dos saldos:
    # Alice tinha 5.0, pagou 1.5 de taxa. Resta 3.5.
    assert blockchain.get_balance("Alice") == 3.5
    # Bob minerou o bloco. Ganha 5.0 (base) + 1.5 (taxa da Alice). Total 6.5.
    assert blockchain.get_balance("Bob") == 6.5


# --- TESTES DE BLOCO E CONSENSO ---

@patch('transaction.Transaction.validate', return_value=True)
@patch.object(Blockchain, 'get_balance', return_value=10.0)
def test_add_block_success(mock_balance, mock_validate, blockchain, mock_transaction):
    blockchain.add_transaction(mock_transaction)
    
    last_block = blockchain.get_latest_block()
    new_block = Block(index=1, transactions=[mock_transaction], previous_hash=last_block.hash)
    new_block.mine_block(blockchain.difficulty, miner_address="MineradorX")
    
    blockchain.add_block(new_block)
    
    assert len(blockchain.chain) == 2
    assert blockchain.get_latest_block() == new_block
    assert len(blockchain.mempool) == 0 # A transação foi empacotada

def test_add_block_invalid_coinbase_reward(blockchain):
    last_block = blockchain.get_latest_block()
    new_block = Block(index=1, transactions=[], previous_hash=last_block.hash)
    
    # Minera o bloco normalmente (Recompensa esperada = 5.0)
    new_block.mine_block(blockchain.difficulty, miner_address="Minerador_Guloso")
    
    # O minerador adultera a própria recompensa para 100 tokens ANTES de mandar pra rede
    new_block.transactions[0].reward = 100.0
    
    # A rede deve pegar a fraude e rejeitar o bloco
    with pytest.raises(Exception, match="Bloco inválido: a primeira transação deve ser a de recompensa"):
        blockchain.add_block(new_block)

@patch('transaction.Transaction.validate', return_value=True)
def test_consensus_longest_chain_and_orphan_recovery(mock_validate):
    node_a = Blockchain() 
    node_b = Blockchain() 
    
    # Criamos transações com taxa zero para pular a necessidade de ter saldo nos nós testes
    tx_orphan = Transaction("A", "B", "uri1", "key1", "sig1", fee=0.0) 
    tx_network_1 = Transaction("C", "D", "uri2", "key2", "sig2", fee=0.0)
    tx_network_2 = Transaction("E", "F", "uri3", "key3", "sig3", fee=0.0)
    
    # Node A minera o Bloco 1 (Cadeia mais curta)
    previous_hash = node_a.get_latest_block().hash or '0'
    block_a1 = Block(1, [tx_orphan], previous_hash)
    block_a1.mine_block(node_a.difficulty, miner_address="node_a")
    node_a.add_block(block_a1)
    
    # Node B minera o Bloco 1 e o Bloco 2 (Cadeia mais longa)
    previous_hash = node_b.get_latest_block().hash or '0'
    block_b1 = Block(1, [tx_network_1], previous_hash)
    block_b1.mine_block(node_b.difficulty, miner_address="node_b")
    node_b.add_block(block_b1)
    
    previous_hash = node_b.get_latest_block().hash or '0'
    block_b2 = Block(2, [tx_network_2], previous_hash)
    block_b2.mine_block(node_b.difficulty, miner_address="node_b")
    node_b.add_block(block_b2)
    
    # Executa o consenso no Node A
    houve_substituicao = node_a.consensus([node_b.chain])
    
    assert houve_substituicao is True
    assert len(node_a.chain) == 3 
    
    # A transação órfã volta para a mempool para não ser perdida
    assert tx_orphan in node_a.mempool
    assert tx_network_1 not in node_a.mempool