import time
import json
import base64
from kafka import KafkaProducer
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from core.transaction import Transaction
from producer.wallet import Wallet

def criar_tx(sender, receiver, file_uri, fee):
    file_key = b"chave-secreta-do-arquivo-pdf"
    encrypted_key = receiver.public_key.encrypt(
        file_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    
    tx = Transaction(
        sender_public_key=sender.get_public_key_pem(),
        receiver_public_key=receiver.get_public_key_pem(),
        file_uri=file_uri,
        encrypted_access_key=base64.b64encode(encrypted_key).decode('utf-8'),
        fee=fee
    )
    tx.signature = sender.sign_transaction(tx.generate_hash())
    return tx.__dict__

def main():
    producer = KafkaProducer(
        bootstrap_servers=['localhost:9092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    print("Gerando carteiras...")
    hacker = Wallet("Hacker")
    alice = Wallet("Alice")
    bob = Wallet("Bob")
    
    print("\n--- GASTO DUPLO ---")
    print("O hacker envia DUAS transações idênticas gastando todo o seu saldo (100.0), mas para pessoas diferentes na mesma hora.")
    tx_alice = criar_tx(hacker, alice, "ipfs://arquivo_fraude.pdf", fee=100.0)
    tx_bob = criar_tx(hacker, bob, "ipfs://arquivo_fraude.pdf", fee=100.0)
    
    print("Transmitindo Tx1 (Para Alice)...")
    producer.send('transactions', tx_alice)
    
    print("Transmitindo Tx2 (Para Bob)...")
    producer.send('transactions', tx_bob)
    
    producer.flush()
    print("Enviadas!\n")
    time.sleep(5)

if __name__ == '__main__':
    main()
