import pytest
from block import Block
from transaction import Transaction

@pytest.fixture
def sample_transactions():
    # Cria uma lista de transações fake para usar nos testes
    tx = Transaction("remetente", "destinatario", "uri", "chave", "assinatura")
    return [tx]

def test_block_hash_changes_with_nonce(sample_transactions):
    bloco = Block(index=1, transactions=sample_transactions, previous_hash="hash_anterior")
    
    hash_inicial = bloco.generate_hash()
    
    # Simula o trabalho do minerador
    bloco.nonce += 1
    hash_modificado = bloco.generate_hash()
    
    # Prova que alterar o nonce muda completamente a identidade do bloco
    assert hash_inicial != hash_modificado

def test_block_mining_proof_of_work(sample_transactions):
    dificuldade = 2
    bloco = Block(index=1, transactions=sample_transactions, previous_hash="hash_anterior")
    
    bloco.mine_block(dificuldade)
    
    # Verifica se o bloco salvou um hash
    assert bloco.hash is not None
    # Verifica se o hash cumpre a regra de dificuldade (começa com '00')
    assert bloco.hash.startswith('0' * dificuldade)
    # Garante que o hash salvo é matematicamente autêntico em relação aos dados atuais do bloco
    assert bloco.hash == bloco.generate_hash()