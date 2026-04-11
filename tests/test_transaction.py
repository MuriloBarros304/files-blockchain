from unittest.mock import MagicMock, patch
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

@patch('core.transaction.serialization.load_pem_public_key')
def test_transaction_validation_invalid_signature(mock_load_key):
    # Setup the mock public key
    mock_public_key = MagicMock()
    # verify() raising an exception means the signature is invalid
    mock_public_key.verify.side_effect = Exception("Assinatura Inválida")
    mock_load_key.return_value = mock_public_key
    
    tx = Transaction("hacker_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes", signature="assinatura_falsa")
    
    assert tx.validate() is False

def test_transaction_validation_missing_sender():
    tx = Transaction(None, "destinatario_pub", "ipfs://arquivo", "chave_aes", signature="assinatura") # type: ignore
    assert tx.validate() is False

def test_transaction_validation_missing_signature():
    tx = Transaction("remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes", signature=None)
    assert tx.validate() is False

# --- TESTE DO MINERADOR (COINBASE) ---

@patch('core.transaction.serialization.load_pem_public_key')
def test_transaction_validation_success(mock_load_key):
    # Setup the mock public key
    mock_public_key = MagicMock()
    # verify() returning None means the signature is valid in the cryptography library
    mock_public_key.verify.return_value = None 
    mock_load_key.return_value = mock_public_key
    
    tx = Transaction("remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes", signature="assinatura_valida")
    
    assert tx.validate() is True