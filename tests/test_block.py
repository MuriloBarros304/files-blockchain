import pytest
from core.block import Block
from core.transaction import Transaction

@pytest.fixture
def sample_transactions():
    # Criamos transações com taxas (fees) para testar a matemática do bloco
    tx1 = Transaction("remetente1", "destinatario1", "uri1", "chave1", "sig1", fee=1.5)
    tx2 = Transaction("remetente2", "destinatario2", "uri2", "chave2", "sig2", fee=2.5)
    return [tx1, tx2]

def test_block_hash_changes_with_nonce(sample_transactions):
    bloco = Block(index=1, transactions=sample_transactions, previous_hash="hash_anterior")
    
    hash_inicial = bloco.generate_hash()
    
    # Simula o trabalho do minerador
    bloco.nonce += 1
    hash_modificado = bloco.generate_hash()
    
    # Prova que alterar o nonce muda completamente a identidade do bloco
    assert hash_inicial != hash_modificado

def test_block_mining_proof_of_work(sample_transactions):
    dificuldade = 1
    bloco = Block(index=1, transactions=sample_transactions, previous_hash="hash_anterior")
    
    # Agora a mineração exige saber para quem vai o dinheiro!
    bloco.mine_block(dificuldade, miner_address="Carteira_do_Minerador")
    
    # Verifica se o bloco salvou um hash
    assert bloco.hash is not None
    # Verifica se o hash cumpre a regra de dificuldade (começa com '00')
    assert bloco.hash.startswith('0' * dificuldade)
    # Garante que o hash salvo é matematicamente autêntico em relação aos dados atuais do bloco
    assert bloco.hash == bloco.generate_hash()

# --- TESTES NOVOS: ECONOMIA E SEGURANÇA ---

def test_block_coinbase_generation_and_fee_calculation(sample_transactions):
    # Passamos uma cópia da lista para não alterar a fixture original
    bloco = Block(index=1, transactions=sample_transactions.copy(), previous_hash="hash_anterior")
    
    bloco.mine_block(difficulty=1, miner_address="Minerador_Bob")
    
    # Regra 1: A transação Coinbase DEVE ter sido injetada na posição 0
    coinbase_tx = bloco.transactions[0]
    
    assert coinbase_tx.sender == 'SYSTEM'
    assert coinbase_tx.receiver == 'Minerador_Bob'
    
    # Regra 2: A matemática da recompensa
    # Recompensa base (5.0) + tx1 fee (1.5) + tx2 fee (2.5) = 9.0
    assert coinbase_tx.reward == 9.0
    assert coinbase_tx.fee == 0.0 # Coinbase não paga taxa de rede
    
    # Regra 3: O bloco agora tem 3 transações (As 2 originais + a Coinbase)
    assert len(bloco.transactions) == 3

def test_block_read_only_properties(sample_transactions):
    # Garante que as propriedades de segurança não podem ser adulteradas após a criação
    bloco = Block(index=1, transactions=sample_transactions, previous_hash="hash_anterior")
    
    with pytest.raises(AttributeError):
        bloco.index = 2 # Tentativa de mudar a posição do bloco
        
    with pytest.raises(AttributeError):
        bloco.previous_hash = "novo_hash_falso" # Tentativa de quebrar o encadeamento
        
    with pytest.raises(AttributeError):
        bloco.hash = "0000_hash_forjado" # Tentativa de forjar o Proof of Work