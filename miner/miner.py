import argparse
from collections import defaultdict
import json
import os
import threading
import time
import traceback
import uuid
from kafka import KafkaConsumer, KafkaProducer

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        return False

from core.blockchain import Blockchain
from core.block import Block
from core.transaction import Transaction
from miner.mempool import Mempool

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

load_dotenv()


def _ler_int_env(nome: str, min_value: int = 1) -> int | None:
    valor_raw = os.getenv(nome)
    if valor_raw is None or not valor_raw.strip():
        return None

    try:
        valor = int(valor_raw)
    except ValueError as exc:
        raise ValueError(f"{nome} deve ser um inteiro, recebido: {valor_raw!r}") from exc

    if valor < min_value:
        raise ValueError(f"{nome} deve ser >= {min_value}, recebido: {valor}")

    return valor


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
        self.miner_address = self.__generate_miner_key()
        self.broker = broker
        self.tx_topic = tx_topic
        self.blocks_topic = blocks_topic

        if difficulty is None:
            difficulty = _ler_int_env('MINER_DIFFICULTY')

        if finalization_confirmations is None:
            finalization_confirmations = _ler_int_env(
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
        
        # Gera um ID único para essa instância do minerador
        self.miner_id = str(uuid.uuid4())
        
        self.block_producer = KafkaProducer(
            bootstrap_servers=[self.broker],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        self.stop_mining_event = threading.Event()
        self.mining_lock = threading.Lock()
        self.current_mining_block_index = None

        # Estruturas para rastrear ramos concorrentes e aplicar consenso local
        self.known_blocks: dict[str, Block] = {}
        self.children_by_parent: dict[str, set[str]] = defaultdict(set)
        self.pending_blocks_by_parent: dict[str, list[Block]] = defaultdict(list)
        self.cumulative_work_by_hash: dict[str, int] = {}
        self.active_chain_hashes: list[str] = []
        self.active_tip_hash = ''
        self._registrar_genesis_local()

    def _registrar_genesis_local(self) -> None:
        genesis = self.blockchain.chain[0]
        genesis_hash = genesis.hash
        if not isinstance(genesis_hash, str):
            raise ValueError('Hash do genesis inválido no minerador')

        self.known_blocks[genesis_hash] = genesis
        self.children_by_parent[genesis.previous_hash].add(genesis_hash)
        self.cumulative_work_by_hash[genesis_hash] = self._trabalho_do_bloco(genesis)
        self.active_chain_hashes = [genesis_hash]
        self.active_tip_hash = genesis_hash

    def _trabalho_do_bloco(self, block: Block) -> int:
        block_hash = block.hash
        if not isinstance(block_hash, str):
            return 0

        zeros = 0
        for char in block_hash:
            if char != '0':
                break
            zeros += 1

        # Aproxima o trabalho acumulado: mais zeros iniciais => maior trabalho.
        return 16 ** zeros

    def _obter_caminho_hashes(self, tip_hash: str) -> list[str]:
        caminho_reverso: list[str] = []
        visitados: set[str] = set()
        atual_hash = tip_hash

        while atual_hash and atual_hash not in visitados:
            visitados.add(atual_hash)
            bloco = self.known_blocks.get(atual_hash)
            if bloco is None:
                break

            caminho_reverso.append(atual_hash)
            if bloco.previous_hash == '0':
                break

            atual_hash = bloco.previous_hash

        caminho_reverso.reverse()
        return caminho_reverso

    def _obter_melhor_ponta_hash(self) -> str:
        hashes_com_filho: set[str] = set()
        for bloco in self.known_blocks.values():
            if bloco.previous_hash in self.known_blocks:
                hashes_com_filho.add(bloco.previous_hash)

        pontas = [block_hash for block_hash in self.known_blocks if block_hash not in hashes_com_filho]
        if not pontas:
            return self.active_tip_hash

        pontas_validas = [block_hash for block_hash in pontas if self._ramo_respeita_finalizacao(block_hash)]
        if pontas_validas:
            pontas = pontas_validas
        elif self.active_tip_hash:
            return self.active_tip_hash

        return max(
            pontas,
            key=lambda block_hash: (
                self.cumulative_work_by_hash.get(block_hash, 0),
                self.known_blocks[block_hash].index,
                block_hash,
            ),
        )

    def _obter_ancora_finalizacao(self) -> tuple[int, str] | None:
        if self.finalization_confirmations <= 0:
            return None

        if len(self.active_chain_hashes) <= self.finalization_confirmations:
            return None

        anchor_pos = len(self.active_chain_hashes) - self.finalization_confirmations - 1
        anchor_hash = self.active_chain_hashes[anchor_pos]
        anchor_block = self.known_blocks.get(anchor_hash)
        if anchor_block is None:
            return None

        return anchor_block.index, anchor_hash

    def _cadeia_respeita_finalizacao(self, chain_hashes: list[str]) -> bool:
        anchor = self._obter_ancora_finalizacao()
        if anchor is None:
            return True

        anchor_index, anchor_hash = anchor
        if len(chain_hashes) <= anchor_index:
            return False

        return chain_hashes[anchor_index] == anchor_hash

    def _ramo_respeita_finalizacao(self, tip_hash: str) -> bool:
        branch_hashes = self._obter_caminho_hashes(tip_hash)
        return self._cadeia_respeita_finalizacao(branch_hashes)

    def _validar_bloco_para_rede(self, block: Block, parent: Block | None) -> bool:
        block_hash = block.hash
        if not isinstance(block_hash, str):
            return False

        if parent is None:
            # Genesis de referência: aceitamos apenas o mesmo genesis local.
            if block.previous_hash != '0' or block.index != 0:
                return False

            genesis_hash = self.blockchain.chain[0].hash
            return isinstance(genesis_hash, str) and block_hash == genesis_hash

        if block.previous_hash != parent.hash:
            return False

        if block.index != parent.index + 1:
            return False

        if not self.blockchain.proof_of_work(block):
            return False

        rewards = [t for t in block.transactions if t.sender == 'SYSTEM']
        if len(rewards) != 1:
            return False

        taxes = sum(t.fee for t in block.transactions)
        if block.transactions[0].sender != 'SYSTEM' or abs(block.transactions[0].reward - (5.0 + taxes)) > 1e-9:
            return False

        for transaction in block.transactions:
            if not transaction.validate():
                return False

        return True

    def _tx_ids_da_cadeia(self, chain_hashes: list[str]) -> set[str]:
        tx_ids: set[str] = set()
        for block_hash in chain_hashes:
            bloco = self.known_blocks.get(block_hash)
            if not bloco:
                continue
            for tx in bloco.transactions:
                if tx.sender != 'SYSTEM':
                    tx_ids.add(tx.generate_hash())
        return tx_ids

    def resolver_conflitos(self) -> bool:
        """
        Consenso local por trabalho acumulado: escolhe a melhor ponta entre os
        ramos conhecidos e reorganiza para a cadeia vencedora quando necessário.
        """
        melhor_ponta_hash = self._obter_melhor_ponta_hash()
        if not melhor_ponta_hash:
            return False

        nova_cadeia_hashes = self._obter_caminho_hashes(melhor_ponta_hash)
        if not nova_cadeia_hashes:
            return False

        if not self._cadeia_respeita_finalizacao(nova_cadeia_hashes):
            return False

        nova_cadeia = [self.known_blocks[block_hash] for block_hash in nova_cadeia_hashes if block_hash in self.known_blocks]
        if not nova_cadeia:
            return False

        if not self.blockchain.validate_chain(nova_cadeia):
            return False

        cadeia_antiga_hashes = list(self.active_chain_hashes)
        if cadeia_antiga_hashes == nova_cadeia_hashes:
            self.blockchain.chain = nova_cadeia
            return False

        foi_reorg_real = not (
            len(nova_cadeia_hashes) >= len(cadeia_antiga_hashes)
            and nova_cadeia_hashes[: len(cadeia_antiga_hashes)] == cadeia_antiga_hashes
        )

        tx_ids_nova_cadeia = self._tx_ids_da_cadeia(nova_cadeia_hashes)

        # Transações de blocos órfãos retornam para mempool se não estiverem na nova cadeia.
        for orphan_hash in set(cadeia_antiga_hashes) - set(nova_cadeia_hashes):
            orphan_block = self.known_blocks.get(orphan_hash)
            if not orphan_block:
                continue

            for tx in orphan_block.transactions:
                if tx.sender == 'SYSTEM':
                    continue
                if tx.generate_hash() not in tx_ids_nova_cadeia:
                    self.mempool.add_tx(tx)

        # Remove da mempool o que já está confirmado na nova cadeia principal.
        txs_confirmadas = []
        for block_hash in nova_cadeia_hashes:
            block = self.known_blocks.get(block_hash)
            if not block:
                continue
            txs_confirmadas.extend(tx for tx in block.transactions if tx.sender != 'SYSTEM')
        if txs_confirmadas:
            self.mempool.remove_transactions(txs_confirmadas)

        self.blockchain.chain = nova_cadeia
        self.active_chain_hashes = nova_cadeia_hashes
        self.active_tip_hash = melhor_ponta_hash

        # Interrompe mineração em andamento para retomar sobre a nova ponta.
        self.stop_mining_event.set()

        if foi_reorg_real:
            print(
                f"🔁 Reorganizacao local: nova ponta #{nova_cadeia[-1].index} "
                f"({melhor_ponta_hash[:10]})"
            )
        return True

    def _integrar_bloco(self, block: Block) -> bool:
        block_hash = block.hash
        if not isinstance(block_hash, str):
            return False

        if block_hash in self.known_blocks:
            return False

        parent = None
        if block.previous_hash != '0':
            parent = self.known_blocks.get(block.previous_hash)
            if parent is None:
                self.pending_blocks_by_parent[block.previous_hash].append(block)
                return False

            if not self._ramo_respeita_finalizacao(block.previous_hash):
                print(
                    f"⛔ Bloco #{block.index} ignorado: ramo fora da janela "
                    f"de finalizacao ({self.finalization_confirmations} confirmacoes)."
                )
                return False

        if not self._validar_bloco_para_rede(block, parent):
            return False

        parent_work = self.cumulative_work_by_hash.get(block.previous_hash, 0)
        self.known_blocks[block_hash] = block
        self.children_by_parent[block.previous_hash].add(block_hash)
        self.cumulative_work_by_hash[block_hash] = parent_work + self._trabalho_do_bloco(block)

        # Tenta encaixar blocos pendentes cujo pai acabou de chegar.
        pending_children = self.pending_blocks_by_parent.pop(block_hash, [])
        for child in pending_children:
            self._integrar_bloco(child)

        self.resolver_conflitos()
        return True

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
    
    def __announce_block(self, block, mempool_size: int | None = None):
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
                    if self._integrar_bloco(new_block):
                        print(f"✅ Bloco #{new_block.index} recebido da rede e integrado.")
                            
        except Exception as e:
            print(f"❌ Erro no block_listener: {e}")

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

                    # Requisito de ter ao menos algumas txs para minerar (ajuste se quiser minerar blocos vazios)
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

                if should_wait_for_txs or new_block is None or next_index is None:
                    time.sleep(0.25)
                    continue

                print(f"🔨 Minerando bloco #{next_index}...")
                bloco_confirmado = False

                # Loop intensivo de mineração (Fora do lock para não travar o recebimento de blocos/txs)
                while not self.stop_mining_event.is_set():
                    
                    current_hash = new_block.generate_hash()

                    # Achou o bloco!
                    if current_hash.startswith(target):
                        new_block._hash = current_hash

                        with self.mining_lock:
                            # Se a ponta mudou durante a mineração, ainda tentamos integrar
                            # o bloco como ramo concorrente (fork válido) ao invés de descartá-lo.
                            latest_block = self.blockchain.get_latest_block()
                            if new_block.previous_hash != latest_block.hash:
                                print("⚠️ Bloco minerado em ponta antiga; tentando integrar como fork...")

                            try:
                                if self._integrar_bloco(new_block):
                                    bloco_confirmado = True
                                    print(f"🏆 BLOCO #{next_index} MINERADO COM SUCESSO!")
                                    self.__announce_block(new_block, mempool_size=len(self.mempool))
                                else:
                                    print(f"⚠️ Bloco #{next_index} minerado, mas não integrado (corrida/rede).")
                            except Exception as e:
                                print(f"⚠️ Erro ao integrar bloco minerado: {e}")

                        break # Sai do loop de nonce e vai buscar o próximo bloco

                    new_block.nonce += 1

                if not bloco_confirmado:
                    # Reenfileira transações não confirmadas para evitar perda em corridas de fork.
                    with self.mining_lock:
                        tx_ids_confirmadas = self._tx_ids_da_cadeia(self.active_chain_hashes)
                        for tx in txs_to_mine:
                            if tx.generate_hash() not in tx_ids_confirmadas:
                                self.mempool.add_tx(tx)

                self.current_mining_block_index = None

            except Exception as e:
                print(f"❌ Erro no mining_worker: {e}")
                traceback.print_exc()

            time.sleep(0.1)

    def run(self):
        """Inicia todos os processos do minerador."""
        print("=" * 60)
        print(
            f"🪙 MINERADOR ONLINE | ID: {self.miner_id[:8]} | "
            f"Dificuldade: {self.blockchain.difficulty} | "
            f"Finalizacao: {self.finalization_confirmations}"
        )
        print("=" * 60)

        # Threads em background
        threading.Thread(target=self.block_listener, daemon=True).start()
        threading.Thread(target=self.mining_worker, daemon=True).start()

        # Consumidor de transações (Group ID único para receber TODAS as transações)
        tx_consumer = KafkaConsumer(
            self.tx_topic,
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
    parser = argparse.ArgumentParser(description='Executa o minerador da blockchain.')
    parser.add_argument(
        '--broker',
        default=os.getenv('KAFKA_BROKER', 'localhost:9092'),
        help='Broker Kafka no formato host:porta (default: env KAFKA_BROKER ou localhost:9092).',
    )
    parser.add_argument(
        '--difficulty',
        type=int,
        default=_ler_int_env('MINER_DIFFICULTY'),
        help='Dificuldade de mineração (default: env MINER_DIFFICULTY ou valor padrão do Blockchain).',
    )
    parser.add_argument(
        '--finalization-confirmations',
        type=int,
        default=_ler_int_env('MINER_FINALIZATION_CONFIRMATIONS', min_value=0),
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