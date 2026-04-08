import time
import random
import argparse
from kafka import KafkaProducer
import json
import base64
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from core.transaction import Transaction
from .wallet import Wallet

def generate_tx(users):
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

def main():
    parser = argparse.ArgumentParser(description='Gerador de transações para a Blockchain.')
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='Semente (seed) fixa para tornar a execução reproduzível.'
    )
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        print(f"Generator] Executando com seed fixa: {args.seed}")

    producer = KafkaProducer(
        bootstrap_servers=['localhost:9092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    users = [Wallet(f"User_{i}") for i in range(5)]

    while True:
        data = generate_tx(users).__dict__
        producer.send('transactions', data)
        print(f"Transação enviada!(URI: {data['file_uri']})")
        time.sleep(random.uniform(1, 3))
if __name__ == "__main__":
    main()

