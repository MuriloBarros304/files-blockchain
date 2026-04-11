import json
from kafka import KafkaConsumer, KafkaProducer
from core.block import Block
from core.transaction import Transaction
from miner.mempool import Mempool
from miner.consensus import ConsensusManager
import threading

class MinerNetwork:
    def __init__(
        self,
        broker: str,
        miner_id: str,
        tx_topic: str,
        blocks_topic: str,
        mempool: Mempool,
        consensus_manager: ConsensusManager,
        mining_lock: threading.Lock
    ):
        self.broker = broker
        self.miner_id = miner_id
        self.tx_topic = tx_topic
        self.blocks_topic = blocks_topic
        self.mempool = mempool
        self.consensus_manager = consensus_manager
        self.mining_lock = mining_lock
        
        self.block_producer = KafkaProducer(
            bootstrap_servers=[self.broker],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )

    def announce_block(self, block: Block, mempool_size: int | None = None):
        """Envia o bloco minerado para o Kafka."""
        block_dict = {
            'index': block.index,
            'previous_hash': block.previous_hash,
            'nonce': block.nonce,
            'timestamp': block.timestamp,
            'hash': block.hash,
            'miner': self.miner_id,
            'tx_count': max(0, len(block.transactions) - 1),
            'transactions': [
                {
                    'sender': tx.sender, 'receiver': tx.receiver, 'file_uri': tx.file_uri,
                    'encrypted_key': tx.encrypted_key, 'timestamp': tx.timestamp,
                    'reward': tx.reward, 'fee': tx.fee, 'signature': tx.signature
                } for tx in block.transactions
            ]
        }

        if mempool_size is not None:
            block_dict['mempool_size'] = mempool_size

        self.block_producer.send(self.blocks_topic, block_dict)
        print(f"Bloco #{block.index} anunciado à rede!")

    def reconstruct_transaction(self, tx_data: dict) -> Transaction:
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
            self.blocks_topic,
            bootstrap_servers=[self.broker],
            group_id=f"miner-block-group-{self.miner_id}", 
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest'
        )

        try:
            for message in block_consumer:
                block_data = message.value
                try:
                    raw_txs = block_data.get('transactions')
                    if not isinstance(raw_txs, list):
                        continue

                    reconstructed_txs = [self.reconstruct_transaction(t) for t in raw_txs]
                    new_block = Block(
                        index=block_data['index'],
                        transactions=reconstructed_txs,
                        previous_hash=block_data['previous_hash'],
                        timestamp=block_data['timestamp'],
                        nonce=block_data['nonce']
                    )
                    new_block._hash = block_data['hash']
                except (KeyError, TypeError, ValueError):
                    continue

                with self.mining_lock:
                    if self.consensus_manager.integrate_block(new_block):
                        print(f"Bloco #{new_block.index} recebido da rede e integrado.")
                            
        except Exception as e:
            print(f"-> Erro no block_listener: {e}")

    def transaction_listener(self):
        """Consome transações da rede."""
        tx_consumer = KafkaConsumer(
            self.tx_topic,
            bootstrap_servers=[self.broker],
            group_id=f"miner-tx-group-{self.miner_id}",
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest'
        )

        try:
            for message in tx_consumer:
                tx_data = message.value
                with self.mining_lock:
                    new_tx = self.reconstruct_transaction(tx_data)
                    if self.mempool.add_tx(new_tx):
                        print(f"Transação recebida. \
                            Mempool: {len(self.mempool)}")
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"-> Erro no transaction_listener: {e}")
