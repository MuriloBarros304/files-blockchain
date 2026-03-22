from unittest.mock import patch
from transaction import Transaction

def test_transaction_hash_determinism():
    # Cria uma transação com dados fixos
    tx = Transaction("remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes_criptografada")
    
    hash1 = tx.generate_hash()
    hash2 = tx.generate_hash()
    
    # O hash deve ser exatamente o mesmo se os dados não mudaram
    assert hash1 == hash2
    assert isinstance(hash1, str)

@patch('transaction.cryptography') # Intercepta a chamada da biblioteca cryptography
def test_transaction_validation_success(mock_crypto):
    # Força a biblioteca de mentira a retornar True (simulando uma assinatura válida)
    mock_crypto.verify_signature.return_value = True
    
    tx = Transaction("remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes", signature="assinatura_valida")
    
    assert tx.validate() is True

def test_transaction_validation_missing_sender():
    tx = Transaction(None, "destinatario_pub", "ipfs://arquivo", "chave_aes", signature="assinatura") # type: ignore
    assert tx.validate() is False

def test_transaction_validation_missing_signature():
    tx = Transaction("remetente_pub", "destinatario_pub", "ipfs://arquivo", "chave_aes", signature=None)
    assert tx.validate() is False