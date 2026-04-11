import argparse
import os
import threading
import time
import traceback
import uuid

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        return False

from core.blockchain import Blockchain
from core.block import Block
from miner.mempool import Mempool
from miner.utils import ler_int_env, generate_miner_key
from miner.consensus import ConsensusManager
from miner.network import MinerNetwork

load_dotenv()

class Miner:
    def __init__(
        self,
        broker='localhost:9092',
        difficulty: int | None = None,
        finalization_confirmations: int | None = None,
        tx_topic: str = 'transactions',
        blocks_topic: str = 'blocks',
    ):
        self.blockchain = Blockchain()
        self.mempool = Mempool()
        self.miner_address = generate_miner_key()

        if difficulty is None:
            difficulty = ler_int_env('MINER_DIFFICULTY')

        if finalization_confirmations is None:
            finalization_confirmations = ler_int_env(
                'MINER_FINALIZATION_CONFIRMATIONS',
                min_value=0,
            )

        if finalization_confirmations is None:
            finalization_confirmations = 6

        if difficulty is not None:
            if difficulty < 1:
                raise ValueError(f"difficulty deve ser >= 1, recebido: {difficulty}")
            self.blockchain.difficulty = difficulty

        if finalization_confirmations < 0:
            raise ValueError(
                'finalization_confirmations deve ser >= 0, '
                f'recebido: {finalization_confirmations}'
            )

        self.finalization_confirmations = finalization_confirmations
        self.miner_id = str(uuid.uuid4())
        
        self.stop_mining_event = threading.Event()
        self.mining_lock = threading.Lock()
        self.current_mining_block_index = None

        self.consensus_manager = ConsensusManager(
            blockchain=self.blockchain,
            mempool=self.mempool,
            stop_mining_event=self.stop_mining_event,
            finalization_confirmations=self.finalization_confirmations
        )

        self.network = MinerNetwork(
            broker=broker,
            miner_id=self.miner_id,
            tx_topic=tx_topic,
            blocks_topic=blocks_topic,
            mempool=self.mempool,
            consensus_manager=self.consensus_manager,
            mining_lock=self.mining_lock
        )

    def mining_worker(self):
        while True:
            try:
                should_wait_for_txs = False
                new_block = None
                txs_to_mine = []
                target = ''
                next_index = None

                with self.mining_lock:
                    latest_block = self.blockchain.get_latest_block()

                    if len(self.mempool) < 1:
                        self.current_mining_block_index = None
                        should_wait_for_txs = True
                    else:
                        next_index = latest_block.index + 1
                        self.current_mining_block_index = next_index
                        self.stop_mining_event.clear()

                        txs_to_mine = self.mempool.get_transactions(2)

                        if not txs_to_mine:
                            self.current_mining_block_index = None
                            should_wait_for_txs = True
                        else:
                            try:
                                new_block = Block(
                                    index=next_index,
                                    transactions=txs_to_mine.copy(),
                                    previous_hash=latest_block.hash
                                )
                            except Exception as e:
                                print(f"-> Erro ao criar novo bloco: {e}")
                                traceback.print_exc()
                                self.current_mining_block_index = None
                                should_wait_for_txs = True
                                continue

                            total_fee = sum(t.fee for t in txs_to_mine)
                            reward = 5.0 + total_fee

                            coinbase = new_block.generate_coinbase_transaction(self.miner_address, reward)
                            new_block.transactions.insert(0, coinbase)

                            if hasattr(new_block, 'transaction_hashes'):
                                 new_block.transaction_hashes = ''.join(tx.generate_hash() for tx in new_block.transactions)

                            target = '0' * self.blockchain.difficulty

                if should_wait_for_txs or new_block is None or next_index is None:
                    time.sleep(0.25)
                    continue

                print(f"Minerando bloco #{next_index}...")
                bloco_confirmado = False

                while not self.stop_mining_event.is_set():
                    current_hash = new_block.generate_hash()

                    if current_hash.startswith(target):
                        new_block._hash = current_hash

                        with self.mining_lock:
                            latest_block = self.blockchain.get_latest_block()
                            if new_block.previous_hash != latest_block.hash:
                                print("Bloco minerado em ponta antiga; tentando integrar como fork...")

                            try:
                                if self.consensus_manager.integrate_block(new_block):
                                    bloco_confirmado = True
                                    print(f"BLOCO #{next_index} MINERADO COM SUCESSO!")
                                    self.network.announce_block(new_block, mempool_size=len(self.mempool))
                                else:
                                    print(f"Bloco #{next_index} minerado, mas não integrado (corrida/rede).")
                            except Exception as e:
                                print(f"-> Erro ao integrar bloco minerado: {e}")

                        # Garante que a flag seja checada se confirmou
                        break

                    new_block.nonce += 1
                    
                    # Cede CPU ocasionalmente para que a thread da rede consiga processar blocos de outros nós
                    if new_block.nonce % (1000 * self.blockchain.difficulty) == 0:
                        time.sleep(0)

                if not bloco_confirmado:
                    if self.stop_mining_event.is_set():
                        print("Mineração interrompida: novo bloco recebido na rede. Minerador atualizando seu último bloco...")
                    with self.mining_lock:
                        tx_ids_confirmadas = self.consensus_manager.tx_ids_from_chain(self.consensus_manager.active_chain_hashes)
                        for tx in txs_to_mine:
                            if tx.generate_hash() not in tx_ids_confirmadas:
                                self.mempool.add_tx(tx)

                self.current_mining_block_index = None

            except Exception as e:
                print(f"-> Erro no mining_worker: {e}")
                traceback.print_exc()

            time.sleep(0.1)

    def run(self):
        """Inicia todos os processos do minerador."""
        print("=" * 60)
        print(
            f"MINERADOR ONLINE | ID: {self.miner_id[:8]} | "
            f"Dificuldade: {self.blockchain.difficulty} | "
            f"Finalizacao: {self.finalization_confirmations}"
        )
        print("=" * 60)

        threading.Thread(target=self.network.block_listener, daemon=True).start()
        threading.Thread(target=self.mining_worker, daemon=True).start()

        # Roda o consumidor de transações na thread principal
        print("\nPressione Ctrl+C para encerrar...")
        self.network.transaction_listener()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Executa o minerador da blockchain.')
    parser.add_argument(
        '--broker',
        default=os.getenv('KAFKA_BROKER', 'localhost:9092'),
        help='Broker Kafka no formato host:porta (default: env KAFKA_BROKER ou localhost:9092).',
    )
    parser.add_argument(
        '--difficulty',
        type=int,
        default=ler_int_env('MINER_DIFFICULTY'),
        help='Dificuldade de mineração (default: env MINER_DIFFICULTY ou valor padrão do Blockchain).',
    )
    parser.add_argument(
        '--finalization-confirmations',
        type=int,
        default=ler_int_env('MINER_FINALIZATION_CONFIRMATIONS', min_value=0),
        help=(
            'Numero de confirmacoes para finalizacao da cadeia. '
            'Apos essa janela, ramos perdedores deixam de ser estendidos '
            '(default: env MINER_FINALIZATION_CONFIRMATIONS ou 6).'
        ),
    )
    parser.add_argument(
        '--tx-topic',
        default=os.getenv('KAFKA_TOPIC_TRANSACTIONS', 'transactions'),
        help='Tópico Kafka de transações (default: env KAFKA_TOPIC_TRANSACTIONS ou transactions).',
    )
    parser.add_argument(
        '--blocks-topic',
        default=os.getenv('KAFKA_TOPIC_BLOCKS', 'blocks'),
        help='Tópico Kafka de blocos (default: env KAFKA_TOPIC_BLOCKS ou blocks).',
    )

    args = parser.parse_args()

    if args.difficulty is not None and args.difficulty < 1:
        parser.error('--difficulty deve ser >= 1')

    if args.finalization_confirmations is not None and args.finalization_confirmations < 0:
        parser.error('--finalization-confirmations deve ser >= 0')

    miner = Miner(
        broker=args.broker,
        difficulty=args.difficulty,
        finalization_confirmations=args.finalization_confirmations,
        tx_topic=args.tx_topic,
        blocks_topic=args.blocks_topic,
    )
    miner.run()
