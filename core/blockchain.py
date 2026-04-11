from core.block import Block
from core.transaction import Transaction

class Blockchain:
    """
    Classe que representa a blockchain.
    """
    def __init__(self) -> None:
        self.chain: list[Block] = []
        self.mempool: list[Transaction] = [] # Transações aguardando inclusão em um bloco
        self._difficulty: int = 6
        self.create_genesis_block() # Primeiro bloco que deve ser criado

    @property
    def difficulty(self) -> int:
        """Getter para a dificuldade atual da mineração."""
        return self._difficulty

    @difficulty.setter
    def difficulty(self, value) -> None:
        """Setter para a dificuldade da mineração."""
        if not isinstance(value, int):
            raise ValueError("Dificuldade deve ser um inteiro")
        self._difficulty = value

    def create_genesis_block(self) -> None:
        """
        Cria o bloco gênesis, que é o primeiro bloco da cadeia.
        Ele não tem transações e seu hash anterior é '0'.
        """
        genesis_block = Block(index=0, transactions=[], previous_hash='0', 
                              timestamp=0.0)
        genesis_block.mine_block(self.difficulty, miner_address='SYSTEM')
        self.chain.append(genesis_block)

    def get_latest_block(self) -> Block:
        """
        Retorna o último bloco da cadeia, que é o bloco mais recente.
        Returns:
            Block: O último bloco da cadeia.
        """
        return self.chain[-1]
    
    def add_transaction(self, transaction: Transaction) -> None:
        """
        Adiciona uma transação à mempool, mas somente se ela for válida.
        Args:
            transaction (Transaction): A transação a ser adicionada.
        Raises:
            Exception: Se a transação for inválida.
        """
        tax = transaction.reward + transaction.fee
        try:
            transaction.validate()
            if self.get_balance(transaction.sender) >= tax:
                self.mempool.append(transaction)
            else:
                raise Exception("Saldo insuficiente para cobrir a recompensa \
                e a taxa da transação")
        except Exception as e:
            raise Exception(f"Transação inválida: {e}")
        
    def get_balance(self, public_key: str) -> float:
        """
        Calcula o saldo de um usuário com base nas transações presentes na 
        cadeia.
        Args:
            public_key (str): A chave pública do usuário para o qual o saldo \
            deve ser calculado.
        Returns:
            float: O saldo do usuário.
        """
        balance = 0.0

        for block in self.chain:
            for transaction in block.transactions:
                # Se for coinbase (recompensa para mineradores), o destinatário recebe a recompensa,
                # Se não for coinbase, o destinatário recebe 0.0, mas o remetente perde a taxa da transação
                if transaction.receiver == public_key:
                    balance += transaction.reward # Recebe a recompensa da transação
                if transaction.sender == public_key:
                    balance -= transaction.fee # Perde a taxa da transação
        
        return balance
        
    def proof_of_work(self, block: Block) -> bool:
        """
        Faz a prova de trabalho para um bloco, verificando se o hash 
        do bloco atende à condição de dificuldade.
        Args:
            block (Block): O bloco a ser verificado.
        Returns:
            bool: True se o bloco atende à condição de dificuldade, False caso \
                contrário.
        """
        target = '0' * self.difficulty

        if not block.hash:
            return False

        if block.hash[:self.difficulty] != target:
            return False
        
        if block.hash != block.generate_hash():
            return False
        
        return True

    def add_block(self, block: Block) -> None:
        """
        Adiciona um bloco à cadeia, mas somente se ele for válido 
        (hash correto, prova de trabalho válida e transações válidas).
        Args:
            block (Block): O bloco a ser adicionado.
        Raises:
            Exception: Se o bloco for inválido.
        """
        if self.get_latest_block().hash != block.previous_hash:
            raise Exception("Bloco inválido: hash anterior não corresponde")
        
        if not self.proof_of_work(block):
            raise Exception("Prova de trabalho inválida")

        rewards = [t for t in block.transactions if t.sender == 'SYSTEM']
        
        if len(rewards) != 1:
            raise Exception("Bloco inválido: deve haver exatamente uma " \
            "transação de recompensa.")

        taxes = sum(t.fee for t in block.transactions)
        if block.transactions[0].sender != 'SYSTEM' \
            or block.transactions[0].reward != (5.0 + taxes):
            raise Exception(f"Bloco inválido: a primeira transação deve ser a \
                            de recompensa ({5.0 + taxes}).")

        for transaction in block.transactions:
            if not transaction.validate():
                raise Exception(
                    f"Transação: {transaction.sender} -> {transaction.receiver}"
                    f"({transaction.timestamp}) inválida"
                )

        self.chain.append(block)
        
        self.mempool = [t for t in self.mempool if t not in block.transactions]

    def validate_chain(self, chain: list[Block]) -> bool:
        """
        Valida uma cadeia de blocos, verificando a integridade de cada bloco e 
        a validade das transações.
        Args:
            chain (list[Block]): A cadeia de blocos a ser validada.
        Returns:
            bool: True se a cadeia for válida, False caso contrário.
        """
        if chain[0].hash != self.chain[0].hash:
            return False

        for i in range(1, len(chain)):
            current = chain[i]
            previous = chain[i - 1]

            if current.previous_hash != previous.hash:
                return False
            
            if not self.proof_of_work(current):
                return False
            
            for transaction in current.transactions:
                if not transaction.validate():
                    return False
                
            # Verifica se as transações deste bloco já estão presentes em blocos anteriores, o que não deveria acontecer
            for b in chain[:i]:
                for t in b.transactions:
                    if t in current.transactions:
                        return False
        
        # Verifica se as transações de recompensa para mineradores estão corretas
        for block in chain[1:]: # Começa do bloco 1, pois o bloco 0 é o gênesis e não tem transações
            taxes = sum(t.fee for t in block.transactions)
            if block.transactions[0].sender != 'SYSTEM' \
                or block.transactions[0].reward != (5.0 + taxes):
                return False
        
        return True

    def consensus(self, other_chains: list[list[Block]]) -> bool:
        """
        Caso haja divergências entre cadeias, adota a cadeia mais longa e 
        válida encontrada.
        Args:
            other_chains (list[list[Block]]): Outras cadeias de blocos a serem \
                comparadas.
        Returns:
            bool: True se a cadeia foi substituída por uma mais longa e \
                válida, False caso contrário.
        """
        longest_chain = self.chain

        for other in other_chains:
            if len(other) > len(longest_chain) and self.validate_chain(other):
                longest_chain = other

        # Se a cadeia mais longa encontrada for diferente da cadeia atual, substitui a cadeia atual pela mais longa
        if longest_chain != self.chain:
            orphan_blocks = [b for b in self.chain if b not in longest_chain] # Blocos que estão na cadeia mais curta mas não estão na mais longa
            all_transactions_in_longest = \
                [t for b in longest_chain for t in b.transactions] # Transações que já estão na cadeia mais longa
            orphan_transactions = [ob.transactions for ob in orphan_blocks] # Transações que estavam nos blocos órfãos, que precisam ser recolocadas na mempool
            for ot in orphan_transactions:
                for t in ot:
                    if t not in self.mempool \
                        and t not in all_transactions_in_longest: # Se não já está na mempool ou na cadeia mais longa
                        self.mempool.append(t) # Recoloca as transações dos blocos órfãos de volta na mempool

            self.chain = longest_chain
            return True
        
        return False