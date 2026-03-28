from unittest.mock import patch
from core.transaction import Transaction

def test_transaction_initialization_with_economy():
    # Verifica se as taxas e recompensas estão sendo atribuídas corretamente
    tx = Transaction(
        "remetente_pub", "destinatario_pub", "ipfs://arquivo",
        "chave_aes", signature="assinatura", reward=5.0, fee=1.5
    )
    assert tx.reward == 5.0
    assert tx.fee == 1.5
    assert tx.sender == "remetente_pub"

def test_transaction_hash_determinism():
    tx = Transaction("remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes_criptografada")
    
    hash1 = tx.generate_hash()
    hash2 = tx.generate_hash()
    
    # O hash deve ser exatamente o mesmo se os dados não mudaram
    assert hash1 == hash2
    assert isinstance(hash1, str)

def test_transaction_hash_economy_sensitivity():
    # Se alguém tentar adulterar a taxa ou a recompensa, o hash DEVE mudar
    tx_original = Transaction("remetente", "destinatario", "uri", "chave", fee=1.0)
    
    tx_adulterada = Transaction("remetente", "destinatario", "uri", "chave", fee=50.0)
    # Igualamos o timestamp para garantir que a única diferença seja a taxa
    tx_adulterada.timestamp = tx_original.timestamp 
    
    assert tx_original.generate_hash() != tx_adulterada.generate_hash()

# --- TESTES DE VALIDAÇÃO DE ASSINATURA ---

@patch('core.transaction.cryptography') # Intercepta a chamada da biblioteca cryptography
def test_transaction_validation_success(mock_crypto):
    # Força a biblioteca de mentira a retornar True (simulando uma assinatura válida)
    mock_crypto.verify_signature.return_value = True
    
    tx = Transaction("remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes", signature="assinatura_valida")
    
    assert tx.validate() is True

@patch('core.transaction.cryptography')
def test_transaction_validation_invalid_signature(mock_crypto):
    # Simula um hacker tentando usar uma assinatura que não bate com a chave pública
    mock_crypto.verify_signature.return_value = False
    
    tx = Transaction("hacker_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes", signature="assinatura_falsa")
    
    assert tx.validate() is False

def test_transaction_validation_missing_sender():
    tx = Transaction(None, "destinatario_pub", "ipfs://arquivo", "chave_aes", signature="assinatura") # type: ignore
    assert tx.validate() is False

def test_transaction_validation_missing_signature():
    tx = Transaction("remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes", signature=None)
    assert tx.validate() is False

# --- TESTE DO MINERADOR (COINBASE) ---

def test_transaction_system_validation_success():
    # Transações de recompensa do sistema não têm assinatura, mas devem ser válidas
    tx_coinbase = Transaction(
        sender_public_key="SYSTEM",
        receiver_public_key="minerador_pub",
        file_uri="",
        encrypted_access_key="",
        signature=None,
        reward=5.0
    )
    
    # A validação DEVE retornar True mesmo sem assinatura
    assert tx_coinbase.validate() is True