from block import Block
from transaction import Transaction

class Blockchain:
    def __init__(self) -> None:
        self.chain: list[Block] = []
        self.mempool: list[Transaction] = [] # Transações aguardando inclusão em um bloco
        self._difficulty: int = 2
        self.create_genesis_block() # Primeiro bloco que deve ser criado

    @property
    def difficulty(self) -> int:
        return self._difficulty

    @difficulty.setter
    def difficulty(self, value) -> None:
        if not isinstance(value, int):
            raise ValueError("Dificuldade deve ser um inteiro")
        self._difficulty = value

    def create_genesis_block(self) -> None:
        genesis_block = Block(index=0, transactions=[], previous_hash='0')
        genesis_block.mine_block(self.difficulty)
        self.chain.append(genesis_block)

    def get_latest_block(self) -> Block:
        return self.chain[-1]
    
    def add_transaction(self, transaction: Transaction) -> None:
        if transaction.validate():
            self.mempool.append(transaction)
        else:
            raise Exception("Transferência inválida")
        
    def add_block(self, block: Block) -> None:
        pass