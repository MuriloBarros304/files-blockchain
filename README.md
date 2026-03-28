# Files Blockchain

Um motor de blockchain em Python construído do zero para gerenciar, auditar e registrar o compartilhamento seguro de arquivos em uma rede distribuída. 

Este projeto não armazena os arquivos pesados na cadeia (on-chain), mas atua como um **livro-razão imutável e descentralizado** de permissões de acesso, utilizando criptografia híbrida e um sistema econômico nativo para incentivar a manutenção da rede.

## Estrutura do Projeto

Atualmente, o projeto está focado no módulo de domínio (`core`), que contém as regras de negócio implacáveis da blockchain:

```text
├── core/
│   ├── transaction.py   # Modelagem de transações, taxas e assinaturas digitais
│   ├── block.py         # Estrutura do bloco, Árvore de Hashes e Proof of Work
│   ├── blockchain.py    # Orquestrador: Mempool, Consenso, Saldos e Validação
├── tests/               # Suíte de testes unitários e de integração (pytest)
└── README.md
```

## Regras de Negócio e Arquitetura

O sistema foi desenhado com regras rígidas para garantir segurança, disponibilidade e alinhamento econômico entre os nós.

### 1. Compartilhamento de Arquivos (Criptografia Híbrida)
A blockchain atua como um cartório de acessos. O fluxo de compartilhamento segue a regra:
* **Off-chain:** O arquivo real é criptografado pelo remetente com uma chave simétrica (ex: AES) e hospedado externamente (ex: IPFS, AWS S3).
* **On-chain:** A transação registra o URI do arquivo e a chave simétrica **criptografada com a Chave Pública do destinatário**. Apenas o dono da Chave Privada correspondente consegue resgatar a chave e abrir o arquivo.

### 2. O Sistema Econômico
Para evitar ataques de *Spam/DDoS* e incentivar o processamento da rede, o sistema possui uma economia nativa baseada em "Tokens de Registro":
* **Taxas (Gas Fees):** Todo usuário que deseja registrar o compartilhamento de um arquivo deve pagar uma taxa (`fee`) estipulada na transação.
* **Recompensa do Minerador:** O nó que resolver o *Proof of Work* primeiro tem o direito de criar uma transação especial (Coinbase) injetada obrigatoriamente no índice `0` do bloco.
* **Matemática do Bloco:** A recompensa do minerador é estritamente fixada em: `Recompensa Base (5.0) + Soma das Taxas das transações do bloco`. Se um minerador cobrar um valor diferente, o bloco é sumariamente rejeitado pela rede.

### 3. Validação e Estado (Saldos)
O sistema não possui um banco de dados central com o saldo dos usuários.
* O saldo é calculado em tempo real varrendo o histórico imutável da cadeia (`get_balance`).
* Transações são rejeitadas e barradas da *Mempool* caso a assinatura digital (`cryptography`) seja inválida ou o remetente não possua saldo suficiente para cobrir a taxa (`fee`).

### 4. Consenso e Resolução de Conflitos (Forks)
Em um ambiente distribuído, divergências ocorrem. O Core implementa a regra da cadeia mais longa (*Longest Chain Rule*):
* Se um nó recebe uma cadeia válida e maior que a sua, ele substitui a cadeia local.
* **Recuperação de Órfãos:** Blocos descartados durante a resolução de um *fork* são auditados. Transações legítimas de usuários que estavam nesses blocos são devolvidas à *Mempool* para não haver perda de dados (acessos pendentes).

### 5. Imutabilidade e Encadeamento
* As propriedades críticas do bloco (`index`, `previous_hash`, `hash`) são atributos de leitura (*Read-Only*).
* Qualquer alteração em um dado histórico (como alterar a taxa de uma transação passada) altera o hash da transação, que por sua vez invalida o hash do bloco, quebrando a corrente criptográfica instantaneamente.

---

## Rodando os Testes

O Core é coberto por uma suíte rigorosa de testes orientada ao comportamento (TDD), garantindo que a matemática financeira e criptográfica funcione perfeitamente.

Para rodar as validações:
```bash
# Na raiz do projeto
python -m pytest -v tests/
```

---

## Camada de Rede e Integração
**[ Status: Em Desenvolvimento ]**

A próxima fase do projeto acoplará o `core` a uma camada de comunicação distribuída. 
A arquitetura de rede (Nodes) será responsável por:
* Disponibilizar uma API (HTTP/REST) para clientes enviarem transações e consultarem arquivos.
* Conectar os nós através de um *Message Broker* (ex: Apache Kafka) ou Sockets (P2P) para realizar o *broadcast* de novos blocos e transações pendentes, garantindo o estado global do livro-razão.
