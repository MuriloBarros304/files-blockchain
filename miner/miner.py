import json
import threading
import time
import traceback
import uuid
from kafka import KafkaConsumer, KafkaProducer

from core.blockchain import Blockchain
from core.block import Block
from core.transaction import Transaction
from miner.mempool import Mempool

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

class Miner:
    def __init__(self, broker='localhost:9092'):
        self.blockchain = Blockchain()
        self.mempool = Mempool()
        self.miner_address = self.__generate_miner_key()
        self.broker = broker
        
        # Gera um ID único para essa instância do minerador
        self.miner_id = str(uuid.uuid4())
        
        self.block_producer = KafkaProducer(
            bootstrap_servers=[self.broker],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        self.stop_mining_event = threading.Event()
        self.mining_lock = threading.Lock()
        self.current_mining_block_index = None

    def __generate_miner_key(self):
        """Gera um par de chaves RSA e retorna a chave pública formatada."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return public_pem.decode('utf-8')
    
    def __announce_block(self, block):
        """Envia o bloco minerado para o Kafka."""
        block_dict = {
            'index': block.index,
            'previous_hash': block.previous_hash,
            'nonce': block.nonce,
            'timestamp': block.timestamp,
            'hash': block.hash,
            'transactions': [
                {
                    'sender': tx.sender, 'receiver': tx.receiver, 'file_uri': tx.file_uri,
                    'encrypted_key': tx.encrypted_key, 'timestamp': tx.timestamp,
                    'reward': tx.reward, 'fee': tx.fee, 'signature': tx.signature
                } for tx in block.transactions
            ]
        }
        self.block_producer.send('blocks', block_dict)
        print(f"📢 Bloco #{block.index} anunciado à rede!")

    def reconstruct_transaction(self, tx_data):
        tx = Transaction(
            sender_public_key=tx_data['sender'],
            receiver_public_key=tx_data['receiver'],
            file_uri=tx_data['file_uri'],
            encrypted_access_key=tx_data['encrypted_key'],
            fee=tx_data.get('fee', 0.0),
            reward=tx_data.get('reward', 0.0)
        )
        tx.timestamp = tx_data['timestamp']
        tx.signature = tx_data.get('signature')
        return tx

    def block_listener(self):
        """Escuta a rede para novos blocos de outros mineradores."""
        block_consumer = KafkaConsumer(
            'blocks',
            bootstrap_servers=[self.broker],
            group_id=f"miner-block-group-{self.miner_id}", 
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest'
        )

        try:
            for message in block_consumer:
                block_data = message.value
                
                with self.mining_lock:
                    latest = self.blockchain.get_latest_block()
                    
                    # Se for o próximo bloco esperado e encaixar na hash
                    if (block_data['index'] == latest.index + 1 and block_data['previous_hash'] == latest.hash):
                        
                        reconstructed_txs = [self.reconstruct_transaction(t) for t in block_data['transactions']]
                        new_block = Block(
                            index=block_data['index'],
                            transactions=reconstructed_txs,
                            previous_hash=block_data['previous_hash'],
                            timestamp=block_data['timestamp'],
                            nonce=block_data['nonce']
                        )
                        new_block._hash = block_data['hash']
                        
                        try:
                            # Tenta adicionar o bloco na blockchain local
                            self.blockchain.add_block(new_block)
                            self.mempool.remove_transactions(reconstructed_txs)
                            
                            # Para a mineração atual (se estiver ocorrendo) pois a rede achou o bloco
                            self.stop_mining_event.set()
                            print(f"✅ Bloco #{new_block.index} recebido da rede e validado.")
                        except Exception as e:
                            print(f"❌ Bloco recebido da rede era inválido: {e}")
                            
        except Exception as e:
            print(f"❌ Erro no block_listener: {e}")

    def mining_worker(self):
        while True:
            try:
                with self.mining_lock:
                    latest_block = self.blockchain.get_latest_block()

                    # Requisito de ter ao menos algumas txs para minerar (ajuste se quiser minerar blocos vazios)
                    if len(self.mempool) < 1:
                        time.sleep(1)
                        continue

                    next_index = latest_block.index + 1
                    self.current_mining_block_index = next_index
                    self.stop_mining_event.clear()

                    txs_to_mine = self.mempool.get_transactions(2)

                    if not txs_to_mine:
                        continue

                    new_block = Block(
                        index=next_index,
                        transactions=txs_to_mine.copy(), # Copia para evitar mutações estranhas
                        previous_hash=latest_block.hash
                    )

                    total_fee = sum(t.fee for t in txs_to_mine)
                    reward = 5.0 + total_fee

                    coinbase = new_block.generate_coinbase_transaction(self.miner_address, reward)
                    new_block.transactions.insert(0, coinbase)

                    # Importante recalcular as hashes de transação dentro do bloco (dependendo da sua implementação de Block)
                    if hasattr(new_block, 'transaction_hashes'):
                         new_block.transaction_hashes = ''.join(tx.generate_hash() for tx in new_block.transactions)

                    target = '0' * self.blockchain.difficulty
                    print(f"🔨 Minerando bloco #{next_index}...")

                # Loop intensivo de mineração (Fora do lock para não travar o recebimento de blocos/txs)
                while not self.stop_mining_event.is_set():
                    
                    current_hash = new_block.generate_hash()

                    # Achou o bloco!
                    if current_hash.startswith(target):
                        new_block._hash = current_hash

                        with self.mining_lock:
                            # Revalida se o bloco ainda é válido (alguém pode ter achado enquanto esperávamos o lock)
                            latest_block = self.blockchain.get_latest_block()
                            if new_block.previous_hash != latest_block.hash:
                                print("⚠️ Bloco ficou obsoleto no último segundo (fork), descartando...")
                                break

                            # Correção: Tratando o add_block que lança Exception ao invés de retornar booleano
                            try:
                                self.blockchain.add_block(new_block)
                                print(f"🏆 BLOCO #{next_index} MINERADO COM SUCESSO!")
                                self.mempool.remove_transactions(txs_to_mine)
                                self.__announce_block(new_block)
                            except Exception as e:
                                print(f"⚠️ Erro ao inserir bloco que acabei de minerar: {e}")

                        break # Sai do loop de nonce e vai buscar o próximo bloco

                    new_block.nonce += 1

                self.current_mining_block_index = None

            except Exception as e:
                print(f"❌ Erro no mining_worker: {e}")
                traceback.print_exc()

            time.sleep(0.1)

    def run(self):
        """Inicia todos os processos do minerador."""
        print("=" * 60)
        print(f"🪙 MINERADOR ONLINE | ID: {self.miner_id[:8]} | Dificuldade: {self.blockchain.difficulty}")
        print("=" * 60)

        # Threads em background
        threading.Thread(target=self.block_listener, daemon=True).start()
        threading.Thread(target=self.mining_worker, daemon=True).start()

        # Consumidor de transações (Group ID único para receber TODAS as transações)
        tx_consumer = KafkaConsumer(
            'transactions',
            bootstrap_servers=[self.broker],
            group_id=f"miner-tx-group-{self.miner_id}", # <--- IMPORTANTE!
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest'
        )

        try:
            for message in tx_consumer:
                tx_data = message.value
                with self.mining_lock:
                    new_tx = self.reconstruct_transaction(tx_data)

                    if self.mempool.add_tx(new_tx):
                        print(f"📥 TX recebida. Mempool: {len(self.mempool)}")
        except KeyboardInterrupt:
            print("\n🛑 Encerrando minerador...")

if __name__ == "__main__":
    miner = Miner()
    miner.run()