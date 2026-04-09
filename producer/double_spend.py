import json
import time
import requests
from multiprocessing import Process, Queue
from kafka import KafkaProducer
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
import base64
from core.block import Block
from core.transaction import Transaction

def generate_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_key, public_pem.decode('utf-8')

def sign_transaction(private_key, msg_hash):
    signature = private_key.sign(
        msg_hash.encode('utf-8'),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def get_hash(s, r, uri, e, t, rew, f):
    import hashlib
    h = hashlib.sha256()
    h.update(f"{s}{r}{uri}{e}{t}{rew}{f}".encode('utf-8'))
    return h.hexdigest()

def mine_and_return(block_index, prev_hash, tx_dict, difficulty, miner_address, queue, result_id, nonce_start=0, step=1):
    # Reconstruct tx
    tx = Transaction(
        sender_public_key=tx_dict['sender'],
        receiver_public_key=tx_dict['receiver'],
        file_uri=tx_dict['file_uri'],
        encrypted_access_key=tx_dict['encrypted_key'],
        fee=tx_dict.get('fee', 0.0),
        reward=tx_dict.get('reward', 0.0)
    )
    tx.timestamp = tx_dict['timestamp']
    tx.signature = tx_dict.get('signature')
    
    b = Block(index=block_index, transactions=[tx], previous_hash=prev_hash, timestamp=time.time())
    
    import hashlib
    total_fee = sum(t.fee for t in b.transactions)
    reward_amount = 5.0 + total_fee
    coinbase_tx = b.generate_coinbase_transaction(miner_address=miner_address, reward_amount=reward_amount)
    b.transactions.insert(0, coinbase_tx)
    b.transaction_hashes = ''.join(t.generate_hash() for t in b.transactions)
    
    target = '0' * difficulty
    base_str = f'{b.index}{b.transaction_hashes}{b.previous_hash}{b.timestamp}'
    base_bytes = base_str.encode('utf-8')
    
    nonce = nonce_start
    while True:
        h = hashlib.sha256()
        h.update(base_bytes + str(nonce).encode('utf-8'))
        hex_digest = h.hexdigest()
        if hex_digest.startswith(target):
            b.nonce = nonce
            b._hash = hex_digest
            break
        nonce += step
    
    print(f"[{result_id}] Bloco minerado! Hash: {b.hash}")
    
    block_dict = {
        'index': b.index,
        'previous_hash': b.previous_hash,
        'timestamp': b.timestamp,
        'nonce': b.nonce,
        'hash': b.hash,
        'miner': f'malicious-{result_id}',
        'tx_count': max(0, len(b.transactions) - 1),
        'transactions': [
            {
                'sender': it.sender, 'receiver': it.receiver, 'file_uri': it.file_uri,
                'encrypted_key': it.encrypted_key, 'timestamp': it.timestamp,
                'reward': it.reward, 'fee': it.fee, 'signature': it.signature
            } for it in b.transactions
        ]
    }
    queue.put((result_id, block_dict))

def main():
    print("Aguardando API Gateway em http://localhost:8000/snapshot ...")
    while True:
        try:
            resp = requests.get("http://localhost:8000/snapshot", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if 'blocks' in data and len(data['blocks']) > 0:
                    break
        except Exception:
            pass
        time.sleep(2)
        
    blocks = data['blocks']
    # Filter only main chain blocks to get the actual tip
    main_blocks = [b for b in blocks if b.get('is_main', False)]
    if not main_blocks:
        main_blocks = blocks  # Fallback

    latest_block = max(main_blocks, key=lambda b: b['index'])
    print(f"Último bloco da cadeia principal: #{latest_block['index']} (hash: {latest_block['hash']})")

    priv_sender, pub_sender = generate_keypair()
    _, pub_receiver1 = generate_keypair()
    _, pub_receiver2 = generate_keypair()

    file_uri = "ipfs://storage/double_spend_target_file.pdf"
    enc_key = "encrypted_key_data"
    fee = 0.0
    reward = 0.0
    ts = time.time()

    h1 = get_hash(pub_sender, pub_receiver1, file_uri, enc_key, ts, reward, fee)
    sig1 = sign_transaction(priv_sender, h1)
    
    tx1 = {
        'sender': pub_sender, 'receiver': pub_receiver1,
        'file_uri': file_uri, 'encrypted_key': enc_key,
        'timestamp': ts, 'reward': reward, 'fee': fee,
        'signature': sig1
    }

    h2 = get_hash(pub_sender, pub_receiver2, file_uri, enc_key, ts, reward, fee)
    sig2 = sign_transaction(priv_sender, h2)

    tx2 = {
        'sender': pub_sender, 'receiver': pub_receiver2,
        'file_uri': file_uri, 'encrypted_key': enc_key,
        'timestamp': ts, 'reward': reward, 'fee': fee,
        'signature': sig2
    }

    difficulty = 6
    target_index = latest_block['index'] + 1
    prev_hash = latest_block['hash']

    print(f"\nDisparando vários processos de mineração concorrentes para forçar um fork no bloco #{target_index}")
    
    q = Queue()
    
    processes = []
    
    for i in range(4):
        p = Process(target=mine_and_return, args=(target_index, prev_hash, tx1, difficulty, pub_sender, q, 'A', i, 4))
        processes.append(p)
        
    for i in range(4):
        p = Process(target=mine_and_return, args=(target_index, prev_hash, tx2, difficulty, pub_sender, q, 'B', i, 4))
        processes.append(p)
        
    for p in processes:
        p.start()
    
    results = {}
    while len(results) < 2:
        res_id, block_dict = q.get()
        if res_id not in results:
            results[res_id] = block_dict
            print(f"Bloco {res_id} minerado com sucesso! Aguardando o outro bloco...")
            
    for p in processes:
        p.terminate()
        p.join()

    print("\nAmbos os blocos com transações conflitantes foram minerados!")
    print("Conectando ao Kafka para broadcast simultâneo...")
    
    producer = KafkaProducer(
        bootstrap_servers=['localhost:9092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    print(f"Bloco A (Hash: {results['A']['hash']}) -> Transação A")
    producer.send('blocks', results['A'])
    
    print(f"Bloco B (Hash: {results['B']['hash']}) -> Transação B")
    producer.send('blocks', results['B'])

    producer.flush()
    print("\nAtaque concluído! Os blocos entraram na rede. Gasto duplo injetado.")
    print("O sistema irá aplicar regras de consenso (como ordem de chegada ou desempate de valor) para aceitar apenas um dos processos e rejeitar a fraude.")

if __name__ == '__main__':
    main()
