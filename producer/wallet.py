import base64
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

class Wallet:
    """
    Classe que representa a carteira de um usuário.
    """
    def __init__(self, name):
        self.name = name
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.private_key.public_key()
        
    def get_public_key_pem(self) -> str:
        """Retorna a chave pública em formato string (PEM) para a Blockchain"""
        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode('utf-8')

    def sign_transaction(self, tx_hash_str: str) -> str:
        """Assina o hash de uma transação com a chave privada"""
        signature = self.private_key.sign(
            tx_hash_str.encode('utf-8'),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode('utf-8')