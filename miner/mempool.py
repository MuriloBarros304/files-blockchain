import heapq
import time

class Mempool:
    def __init__(self, max_size=1000):
        self.pool = []
        self.tx_map = {}   # tx_id -> tx
        self.max_size = max_size
        self.counter = 0   # evita erro no heap (desempate)

    def add_tx(self, tx):
        """
        Adiciona uma transação ao mempool, ordenada por taxa (fee).
        """
        if not tx.validate():
            return False

        tx_id = tx.generate_hash()

        if tx_id in self.tx_map:
            return False

        if len(self.pool) >= self.max_size:
            return False

        heapq.heappush(self.pool, (-tx.fee, self.counter, tx_id))
        self.tx_map[tx_id] = tx
        self.counter += 1

        return True

    def get_transactions(self, max_count=10):
        """
        Retorna as transações mais lucrativas (com maior fee) para mineração.
        """
        txs = []

        while self.pool and len(txs) < max_count:
            _, _, tx_id = heapq.heappop(self.pool)

            tx = self.tx_map.pop(tx_id, None)
            if tx:
                txs.append(tx)

        return txs

    def remove_transactions(self, transactions):
        """
        Remove transações já mineradas (quando recebe um bloco)
        """
        for tx in transactions:
            tx_id = tx.generate_hash()
            self.tx_map.pop(tx_id, None)

        # ⚠️ reconstruir heap (lazy removal)
        self.pool = [
            (fee, count, tx_id)
            for (fee, count, tx_id) in self.pool
            if tx_id in self.tx_map
        ]
        heapq.heapify(self.pool)

    def cleanup_expired(self, ttl=60):
        """
        Remove transações antigas (TTL em segundos)
        """
        now = time.time()

        valid_ids = []
        for tx_id, tx in list(self.tx_map.items()):
            if now - tx.timestamp > ttl:
                del self.tx_map[tx_id]
            else:
                valid_ids.append(tx_id)

        self.pool = [
            (fee, count, tx_id)
            for (fee, count, tx_id) in self.pool
            if tx_id in valid_ids
        ]
        heapq.heapify(self.pool)

    def __len__(self):
        return len(self.tx_map)