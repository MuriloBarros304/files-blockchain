import pytest
from unittest.mock import patch
from blockchain import Blockchain
from block import Block
from transaction import Transaction

@pytest.fixture
def blockchain():
    """Fixture que cria uma nova blockchain "limpa" para cada teste."""
    return Blockchain()

@pytest.fixture
def mock_transaction():
    """Fixture que cria uma transação básica para testes."""
    return Transaction("remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_cripto", signature="assinatura")


def test_blockchain_initialization(blockchain):
    # A cadeia deve inicializar com exatamente 1 bloco (O Gênese)
    assert len(blockchain.chain) == 1
    assert blockchain.chain[0].index == 0
    assert blockchain.chain[0].previous_hash == '0'

def test_difficulty_property_validation(blockchain):
    # Testa se o setter bloqueia tipos incorretos
    with pytest.raises(ValueError, match="Dificuldade deve ser um inteiro"):
        blockchain.difficulty = "3" # Tipo string ao invés de int

@patch('transaction.Transaction.validate', return_value=True)
def test_add_transaction_success(mock_validate, blockchain, mock_transaction):
    # Se a transação for válida, deve entrar na mempool
    blockchain.add_transaction(mock_transaction)
    assert len(blockchain.mempool) == 1
    assert mock_transaction in blockchain.mempool

@patch('transaction.Transaction.validate', return_value=False)
def test_add_transaction_invalid(mock_validate, blockchain, mock_transaction):
    # Se a transação for inválida, deve levantar exceção e não entrar na mempool
    with pytest.raises(Exception, match="Transferência inválida"):
        blockchain.add_transaction(mock_transaction)
    assert len(blockchain.mempool) == 0

@patch('transaction.Transaction.validate', return_value=True)
def test_add_block_success(mock_validate, blockchain, mock_transaction):
    blockchain.add_transaction(mock_transaction)
    
    # Cria e minera um novo bloco apontando para o Gênese
    last_block = blockchain.get_latest_block()
    new_block = Block(index=1, transactions=[mock_transaction], previous_hash=last_block.hash)
    new_block.mine_block(blockchain.difficulty)
    
    blockchain.add_block(new_block)
    
    # Verifica se o bloco entrou na cadeia e se a transação saiu da mempool
    assert len(blockchain.chain) == 2
    assert blockchain.get_latest_block() == new_block
    assert len(blockchain.mempool) == 0

def test_add_block_invalid_previous_hash(blockchain):
    # Cria um bloco com um previous_hash inventado
    new_block = Block(index=1, transactions=[], previous_hash="hash_falso")
    new_block.mine_block(blockchain.difficulty)
    
    with pytest.raises(Exception, match="Bloco inválido"):
        blockchain.add_block(new_block)

def test_add_block_invalid_proof_of_work(blockchain):
    last_block = blockchain.get_latest_block()
    new_block = Block(index=1, transactions=[], previous_hash=last_block.hash)
    
    # Minera o bloco corretamente
    new_block.mine_block(blockchain.difficulty)
    
    # Um nó malicioso altera o hash após a mineração
    new_block._hash = "0000_hash_adulterado" 
    
    with pytest.raises(Exception, match="Prova de trabalho inválida"):
        blockchain.add_block(new_block)

@patch('transaction.Transaction.validate', return_value=True)
def test_consensus_longest_chain_and_orphan_recovery(mock_validate):
    # Simula dois nós da rede
    node_a = Blockchain() # Nosso nó local
    node_b = Blockchain() # Nó da rede (vizinho)
    
    # Cria transações distintas
    tx_orphan = Transaction("A", "B", "uri1", "key1", "sig1") # Ficará no bloco órfão
    tx_network_1 = Transaction("C", "D", "uri2", "key2", "sig2")
    tx_network_2 = Transaction("E", "F", "uri3", "key3", "sig3")
    
    # Node A minera o Bloco 1 (Cadeia mais curta)
    block_a1 = Block(1, [tx_orphan], node_a.get_latest_block().hash) # type: ignore
    block_a1.mine_block(node_a.difficulty)
    node_a.add_block(block_a1)
    
    # Node B minera o Bloco 1 e o Bloco 2 (Cadeia mais longa)
    block_b1 = Block(1, [tx_network_1], node_b.get_latest_block().hash) # type: ignore
    block_b1.mine_block(node_b.difficulty)
    node_b.add_block(block_b1)
    
    block_b2 = Block(2, [tx_network_2], node_b.get_latest_block().hash) # type: ignore
    block_b2.mine_block(node_b.difficulty)
    node_b.add_block(block_b2)
    
    # Executa o consenso no Node A recebendo a cadeia do Node B
    had_substitution = node_a.consensus([node_b.chain])
    
    assert had_substitution is True
    # O Node A deve ter adotado a cadeia inteira do Node B
    assert len(node_a.chain) == 3 
    assert node_a.get_latest_block().hash == block_b2.hash
    
    # TESTE CRÍTICO: A transação tx_orphan, que estava no bloco descartado do Node A,
    # deve ter sido devolvida para a mempool para não ser perdida.
    assert tx_orphan in node_a.mempool
    assert tx_network_1 not in node_a.mempool # Já está na cadeia nova, não deve ir pra mempool