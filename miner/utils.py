import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


def ler_int_env(nome: str, min_value: int = 1) -> int | None:
    valor_raw = os.getenv(nome)
    if valor_raw is None or not valor_raw.strip():
        return None

    try:
        valor = int(valor_raw)
    except ValueError as exc:
        raise ValueError(f"{nome} deve ser um inteiro, recebido: \
                        {valor_raw!r}") from exc

    if valor < min_value:
        raise ValueError(f"{nome} deve ser >= {min_value}, recebido: {valor}")

    return valor


def generate_miner_key() -> str:
    """Gera um par de chaves RSA e retorna a chave pública formatada em PEM."""
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
