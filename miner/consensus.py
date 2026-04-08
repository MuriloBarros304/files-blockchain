from collections import defaultdict
from core.block import Block
from core.blockchain import Blockchain
from miner.mempool import Mempool
import threading

class ConsensusManager:
    def __init__(
        self,
        blockchain: Blockchain,
        mempool: Mempool,
        stop_mining_event: threading.Event,
        finalization_confirmations: int
    ):
        self.blockchain = blockchain
        self.mempool = mempool
        self.stop_mining_event = stop_mining_event
        self.finalization_confirmations = finalization_confirmations

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

    def tx_ids_da_cadeia(self, chain_hashes: list[str]) -> set[str]:
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

        tx_ids_nova_cadeia = self.tx_ids_da_cadeia(nova_cadeia_hashes)

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

    def integrar_bloco(self, block: Block) -> bool:
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
            self.integrar_bloco(child)

        self.resolver_conflitos()
        return True
