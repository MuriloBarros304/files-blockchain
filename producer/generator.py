import time
import random
from kafka import KafkaProducer
import json
import base64
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from core.transaction import Transaction
from .wallet import Wallet

producer = KafkaProducer(
    bootstrap_servers=['localhost:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

users = [Wallet(f"User_{i}") for i in range(5)]

def generate_tx():
    # Sorteio de remetente e destinatário
    sender, receiver = random.sample(users, 2)
    
    # Simula a criptografia da chave do arquivo (usando a pública do receiver)
    file_key = b"chave-secreta-do-arquivo-pdf"
    encrypted_key = receiver.public_key.encrypt(
        file_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    
    # Instancia a transação (Ainda sem assinatura)
    tx = Transaction(
        sender_public_key=sender.get_public_key_pem(),
        receiver_public_key=receiver.get_public_key_pem(),
        file_uri=f"ipfs://storage/file_{random.randint(1,100)}.zip",
        encrypted_access_key=base64.b64encode(encrypted_key).decode('utf-8'),
        fee=0.5
    )
    
    # O Remetente assina o hash da transação
    tx.signature = sender.sign_transaction(tx.generate_hash())
    
    return tx

while True:
    data = generate_tx().__dict__
    producer.send('transactions', data)
    print(f"Transação enviada! ✅")
    time.sleep(random.uniform(1, 5)) # Intervalo aleatório

