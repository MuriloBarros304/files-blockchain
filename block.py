import hashlib
import time

from transaction import Transaction

class Block:
    """
    Classe que representa um bloco na blockchain
    """
    def __init__(
            self, index: int, transactions: list[Transaction], previous_hash: str,
            timestamp: float | None=None, nonce: int=0
        ) -> None:
        self._index: int = index
        self.transactions: list[Transaction] = transactions
        self._previous_hash: str = previous_hash
        self.timestamp: float = timestamp or time.time()
        self.nonce: int = nonce
        self._hash: str | None = None
        self.transaction_hashes = ''.join(tx.generate_hash() for tx in self.transactions)

    @property
    def index(self) -> int:
        """Retorna o índice do bloco na cadeia"""
        return self._index

    @property
    def previous_hash(self) -> str:
        """Retorna o hash do bloco anterior"""
        return self._previous_hash
    
    @property
    def hash(self) -> str | None:
        """Retorna o hash do bloco, se já tiver sido minerado"""
        return self._hash

    def generate_hash(self) -> str:
        """
        Gera o hash do bloco com base em seus dados atuais (index, transações, hash anterior, timestamp e nonce).
        Returns:
            str: O hash SHA-256 do bloco.
        """
        complete_string = f'{self.index}{self.transaction_hashes}{self.previous_hash}{self.timestamp}{self.nonce}'

        hash_obj = hashlib.sha256()
        hash_obj.update(complete_string.encode('utf-8'))

        return hash_obj.hexdigest()
    
    def mine_block(self, difficulty: int) -> None:
        """
        Realiza o processo de mineração do bloco, ajustando o nonce até que o hash do bloco atenda à condição de dificuldade.
        Args:
            difficulty (int): O número de zeros iniciais que o hash do bloco deve conter para ser considerado válido.
        """
        target = '0' * difficulty

        while self.generate_hash()[:difficulty] != target:
            self.nonce += 1

        self._hash = self.generate_hash()
