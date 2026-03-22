import hashlib
import time

from transaction import Transaction

class Block:
    def __init__(
            self, index: int, transactions: list[Transaction], previous_hash: str,
            timestamp: float | None=None, nonce: int=0
        ) -> None:
        self.index: int = index
        self.transactions: list[Transaction] = transactions
        self.previous_hash: str = previous_hash
        self.timestamp: float = timestamp or time.time()
        self.nonce: int = nonce
        self.hash: str | None = None
        self.transaction_hashes = ''.join(tx.generate_hash() for tx in self.transactions)

    def generate_hash(self) -> str:
        complete_string = f'{self.index}{self.transaction_hashes}{self.previous_hash}{self.timestamp}{self.nonce}'

        hash_obj = hashlib.sha256()
        hash_obj.update(complete_string.encode('utf-8'))

        return hash_obj.hexdigest()
    
    def mine_block(self, difficulty: int) -> None:
        target = '0' * difficulty

        while self.generate_hash()[:difficulty] != target:
            self.nonce += 1

        self.hash = self.generate_hash()
