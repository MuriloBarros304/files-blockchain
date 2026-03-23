import hashlib
import time
import cryptography

class Transaction:
    """
    Classe que representa uma transação de transferência de acesso a um arquivo na blockchain
    """
    def __init__(
            self, sender_public_key: str, receiver_public_key: str, file_uri: str,
            encrypted_access_key: str, signature: str | None=None
        ) -> None:
        self.sender: str = sender_public_key
        self.receiver: str = receiver_public_key
        self.file_uri: str = file_uri
        self.encrypted_key: str = encrypted_access_key
        self.timestamp: float = time.time()
        self.signature: str | None= signature # Será preenchido por quem cria a transação

    def generate_hash(self) -> str:
        """
        Gera o hash da transação com base em seus dados atuais (remetente, destinatário, URI do arquivo, chave criptografada e timestamp).
        Returns:
            str: O hash SHA-256 da transação.
        """
        metadata = f"{self.sender}{self.receiver}{self.file_uri}{self.encrypted_key}{self.timestamp}"
        encoded_metadata = metadata.encode('utf-8')

        hash_obj = hashlib.sha256()
        hash_obj.update(encoded_metadata)

        return hash_obj.hexdigest()
    
    def validate(self) -> bool:
        """
        Valida a transação verificando se o remetente e a assinatura estão presentes e se a assinatura é válida para os dados atuais da transação.
        Returns:
            bool: True se a transação for válida, False caso contrário.
        """
        if self.sender is None:
            return False
            
        if self.signature is None:
            return False
            
        current_hash = self.generate_hash()
        
        return cryptography.verify_signature(  # type: ignore
            public_key=self.sender, signature=self.signature,
            message=current_hash
        )