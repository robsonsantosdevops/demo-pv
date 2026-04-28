# Implementação — Fila `contatos` + Contact enriquecido no SF

> **Status:** ✅ implementado e validado end-to-end.
> 94 testes pytest passam. Contrato de mensagem alinhado com o que o
> checkout publica em produção (ver nota abaixo sobre nomes de campos).
>
> **Nota sobre contrato:** o tipo canônico é `aluno_cadastrado` (não
> `contato_criado`, como planejado inicialmente). Os nomes dos campos
> seguem a convenção do checkout: `nome_completo`, `email`,
> `correlation_id` opcional. POC — sem reversão planejada.

## Contexto e motivação

O middleware hoje consome duas filas:
- `pedidos` → Salesforce (Opportunity, Contact criado junto)
- `oportunidades` → SAP (Sales Order enriquecida)

O Contact no SF é criado/atualizado **dentro** do handler de `pedido_criado`,
com os dados mínimos que vêm no payload do pedido (nome e email). Isso tem
limitações:

- Alunos que se cadastram mas **ainda não compraram** não existem no SF.
- Dados mais ricos (CPF, telefone) **não chegam ao SF** porque o payload de
  pedido não carrega.
- O Contact tem ciclo de vida próprio (atualizações de dados pessoais,
  re-cadastros) que hoje não é refletido.

A demo está evoluindo para suportar **cadastro de usuário** como evento
independente da compra. O checkout passará a publicar `aluno_cadastrado` numa
fila nova `contatos` assim que o aluno finalizar o cadastro no site.

**Resultados esperados:**
- Contact no SF sempre existe e está atualizado, independente de compras.
- Vínculo explícito Contact↔Opportunity via `OpportunityContactRole` —
  aparece na related list nativa do layout de Opp.
- Padrão consistente com o resto do middleware (1 pod por fila, 1 handler
  por tipo, idempotência por chave externa).

---

## Arquitetura com a nova fila

```
   Checkout (site)                              Apex Trigger (SF)
         │                                              │
  ┌──────┴──────┐                                       │
  ▼             ▼                                       ▼
contatos    pedidos                               oportunidades
  │             │                                       │
  ▼             ▼                                       ▼
[pod 1]       [pod 2]                               [pod 3]
  │             │                                       │
  └─────────────┴──► Salesforce                         └──► SAP B1
                        Contact  ◄──── OpportunityContactRole ─┐
                        Opportunity ─────────────────────────────┘
```

**Filas:**

| Fila | Producer | Tipos | Pod | Destino |
|---|---|---|---|---|
| `contatos` *(nova)* | Checkout | `aluno_cadastrado` | `sb-consumer-contatos` :8092 | SF Contact |
| `pedidos` | Checkout | `pedido_criado`, `pagamento_aprovado` | `sb-consumer-pedidos` :8090 | SF Opportunity |
| `oportunidades` | Apex Trigger | `oportunidade_ganha` | `sb-consumer-oportunidades` :8091 | SAP B1 Order |

Os 3 pods compartilham a mesma imagem Docker e o mesmo `.env`. A variável
`QUEUE_NAME` decide qual handler stack é carregado.

---

## Decisões de design

### Design escolhido (respostas do usuário)

- **Payload `aluno_cadastrado`**: `aluno_id`, `nome_completo`, `email`, `cpf`, `telefone`.
- **Vínculo Contact↔Opp**: `OpportunityContactRole` com `Role="Aluno"` (padrão
  nativo do SF — aparece na related list, suporta vários papéis por Opp).

### Decisões da implementação

- **Pod dedicado** `sb-consumer-contatos` (porta 8092). Mantém o padrão
  "1 pod por fila" já consolidado: DLQ isolada, escalar independente, falha
  isolada.
- **Match de Contact pelo `Aluno_Id__c`** (novo External ID), não pelo email.
  Razão: email pode mudar ao longo do tempo; `aluno_id` é estável e vem em
  todos os payloads. Email fica como fallback pra Contacts legados sem
  `Aluno_Id__c` preenchido.
- **Ordem invertida tolerada** — se `pedido_criado` chegar antes de
  `aluno_cadastrado`, o handler de pedido cria Contact mínimo via
  `upsert_contact_by_email` (comportamento atual). O `aluno_cadastrado`
  posterior enriquece o mesmo Contact. Sem retry, sem DLQ.

---

## Schema Salesforce — novos custom fields

Criar no sObject `Contact`:

| API Name | Tipo | Tamanho | Flags | Origem |
|---|---|---|---|---|
| `Aluno_Id__c` | Number | 10, 0 | **Unique + External ID** | `payload.aluno_id` |
| `CPF__c` | Text | 14 | (sem Unique na demo) | `payload.cpf` |

Campos standard utilizados (não precisam ser criados):
- `FirstName` / `LastName` — `split(aluno_nome)` (mesmo padrão do handler atual)
- `Email` — `email`
- `Phone` — `telefone`
- `AccountId` — Account master *"Checkout Keeggo - Alunos"* (já existe)

### Criação via Tooling API

Novo script `scripts/sf_create_contact_fields.py` — espelho do existente
`scripts/sf_create_opportunity_fields.py`. Padrão igual:
- `POST /tooling/sobjects/CustomField` com `FullName=Contact.<Name>`
- Concede FLS (Read+Edit) no PermissionSet shadow do profile autenticado
- Idempotente (skip se já existir)
- Flags `--dry-run`, `--only`, `--fls-only`

---

## Schema do payload `aluno_cadastrado`

```json
{
  "correlation_id": "jornada-5-<uuid>",
  "aluno_id": 5,
  "aluno_nome": "Arya Stark",
  "aluno_email": "arya@winterfell.com",
  "cpf": "12345678900",
  "telefone": "+5511988887777",
  "created_at": "2026-04-23T15:00:00.000Z"
}
```

**Obrigatórios**: `correlation_id`, `aluno_id`, `nome_completo`, `email`.
Falta de qualquer um → **DLQ** `missing_required`.

**Opcionais**: `cpf`, `telefone`, `created_at`. Quando ausentes, o handler
omite os campos do payload SF (mantém a política "drop None" já existente
no resto do código).

---

## Arquivos afetados

### Novos

| Arquivo | Propósito |
|---|---|
| `src/middleware/handlers/aluno_cadastrado.py` | Handler: upsert Contact por `Aluno_Id__c` |
| `scripts/sf_create_contact_fields.py` | Cria `Aluno_Id__c` + `CPF__c` no Contact + FLS |
| `tests/test_handler_aluno_cadastrado.py` | Happy path, missing_required, match por aluno_id vs fallback por email |

### Modificados

| Arquivo | Mudança |
|---|---|
| `src/middleware/config.py` | Adicionar `"contatos"` em `VALID_QUEUES` |
| `src/middleware/dispatcher.py` | Adicionar `"contatos": {"aluno_cadastrado"}` em `KNOWN_TYPES` |
| `src/middleware/__main__.py` | Novo branch `config.queue_name == "contatos"` instancia `AlunoCadastradoHandler` com `SalesforceService` |
| `src/middleware/integrations/salesforce/service.py` | Novos métodos: `find_contact_by_aluno_id`, `upsert_contact_by_aluno_id`, `ensure_opportunity_contact_role` |
| `src/middleware/handlers/pedido_criado.py` | Match de Contact passa a tentar `Aluno_Id__c` primeiro; após upsert da Opp, chama `ensure_opportunity_contact_role(opp_id, contact_id, "Aluno")` |
| `scripts/create_queues.py` | Adicionar `"contatos"` em `QUEUE_NAMES` |
| `scripts/send.py` | Novo choice `aluno_cadastrado` em `--tipo` + flags `--aluno-id`, `--cpf`, `--telefone` |
| `tests/conftest.py` | Novas fixtures `ctx_contato`, `contato_payload` |
| `tests/test_handler_pedido_criado.py` | +1 teste: cria OpportunityContactRole quando Contact existe |
| `tests/test_salesforce_service.py` | +3 testes: find_contact_by_aluno_id, upsert_contact_by_aluno_id, ensure_opportunity_contact_role (com idempotência) |
| `docs/message-contract.md` | Seção 2.4 `aluno_cadastrado` com schema + exemplo + validações |
| `docs/message-flow.md` | Sequence diagram novo (contato → SF) + atualizar happy path incluindo OpportunityContactRole |
| `docs/demo-overview.md` | Diagrama com 3 filas e 3 pods |
| `docs/runbook.md` | Mencionar a fila nos comandos e troubleshooting |
| `README.md` | Árvore atualizada + comando do 3º pod |

### Código existente reutilizado

- `SalesforceService.ensure_account_master` — reusar tal qual.
- `SalesforceService.upsert_contact_by_email` — **mantém** como fallback pro
  cenário de ordem invertida.
- `_soql_escape` do service — reutilizado em `find_contact_by_aluno_id`.
- Padrão `scripts/sf_create_opportunity_fields.py` — copiar o boilerplate e
  apontar pra `Contact`.

---

## Fluxo do handler `aluno_cadastrado`

```
1. Valida payload: correlation_id, aluno_id, aluno_nome, aluno_email
   (DLQ se faltar qualquer um → reason=missing_required:<campos>)
2. ensure_account_master() → account_id
3. find_contact_by_aluno_id(aluno_id):
     - achou → PATCH /sobjects/Contact/{id} com campos do payload (merge)
     - não achou → POST /sobjects/Contact/ com Aluno_Id__c = aluno_id
4. ACK
```

**Idempotência**: chave canônica é `Aluno_Id__c`. Reentregas da mesma
mensagem casam pelo mesmo Contact e apenas re-aplicam o PATCH (no-op
efetivo). Múltiplos `aluno_cadastrado` com mesmo `aluno_id` funcionam como
atualizações sucessivas — comportamento desejado.

---

## Ajuste no handler `pedido_criado`

### Hoje
```
1. ensure_account_master
2. upsert_contact_by_email(account_id, nome, email)  → contact_id
3. upsert_opportunity_by_correlation(...)            → opp_id
4. ACK
```

### Depois
```
1. ensure_account_master
2. Match Contact:
     a. find_contact_by_aluno_id(payload.aluno_id)   ← NOVO (primário)
     b. fallback: upsert_contact_by_email(...)        ← MANTÉM (fallback)
   → contact_id (de um dos dois caminhos)
3. upsert_opportunity_by_correlation(...)            → opp_id
4. ensure_opportunity_contact_role(opp_id, contact_id, "Aluno")   ← NOVO
5. ACK
```

`ensure_opportunity_contact_role` é idempotente: faz
`SELECT Id FROM OpportunityContactRole WHERE OpportunityId=X AND ContactId=Y`
e só cria se não existir.

### Ordem invertida (pedido antes de contato)

O fallback (b) garante que a Opp sempre tem Contact vinculado, mesmo com
dados mínimos. Quando `aluno_cadastrado` chegar depois, enriquece o mesmo
Contact — match por `Aluno_Id__c` (que ainda está vazio no Contact mínimo
→ não acha) OU por email (fallback do próprio `aluno_cadastrado` handler pode
ser adicionado se quiser cobrir esse caso; ou o handler só atualiza os
campos em cima).

Na prática o handler `aluno_cadastrado` faz:
- `find_contact_by_aluno_id(aluno_id)` — não acha.
- **Mas se encontrou já um Contact com o mesmo email** que foi criado pelo
  fallback do pedido, é esse que queremos atualizar. Então o handler deve
  tentar: (1) por aluno_id; (2) se não achar, fallback busca por email; se
  achar, atualiza + **grava o Aluno_Id__c** ali (upgrade do Contact mínimo).

Essa lógica de "promote Contact mínimo a Contact completo" é o cuidado
extra na implementação do `upsert_contact_by_aluno_id`.

---

## Infra, Docker, Fila

### Provisionar a fila
`scripts/create_queues.py` — rodar para criar `contatos` com os mesmos
parâmetros das demais (lock 5min, maxDelivery 5, TTL 14d, DLQ on expire).

### Novo pod
```bash
wsl.exe bash -c 'docker run -d --name sb-consumer-contatos \
    --restart unless-stopped \
    --env-file ~/.sb-middleware.env \
    -e QUEUE_NAME=contatos \
    -p 8092:8080 \
    sb-middleware:latest'
```

Imagem: mesma `sb-middleware:latest`, rebuild normal pega os handlers novos.

---

## Verificação end-to-end

```bash
# 1. Infra: provisionar fila + schema SF
python scripts/create_queues.py                    # cria contatos
python scripts/sf_create_contact_fields.py         # cria Aluno_Id__c + CPF__c + FLS

# 2. Rebuild e subir o pod novo
wsl.exe bash -c 'cd /mnt/c/Users/LucianoSilverioMarti/Documents/Python\ Projects/azure_service_bus && \
    docker build -t sb-middleware:latest -f deploy/Dockerfile . && \
    docker run -d --name sb-consumer-contatos --restart unless-stopped \
    --env-file ~/.sb-middleware.env -e QUEUE_NAME=contatos -p 8092:8080 sb-middleware:latest'

# 3. Smoke test 1: publicar aluno_cadastrado
python scripts/send.py --tipo aluno_cadastrado \
    --aluno-id 99 --aluno-email teste99@keeggo.com \
    --correlation-id jornada-99-test

# Validar no SF:
#   SELECT Id, Aluno_Id__c, FirstName, LastName, Email, Phone, CPF__c
#   FROM Contact WHERE Aluno_Id__c = 99

# 4. Smoke test 2: publicar pedido para o mesmo aluno
python scripts/send.py --tipo pedido_criado \
    --numero-pedido PED-99 --correlation-id jornada-99-test

# Validar no SF:
#   - Opportunity PED-99 existe
#   - SELECT Id FROM OpportunityContactRole WHERE OpportunityId = '<OppId>'
#     retorna 1 linha ligando ao Contact do aluno 99

# 5. Suíte de testes
pytest -q                 # esperado: ~83 testes (75 + ~8 novos)
make docker-test          # pytest dentro do container

# 6. Monitorar
python scripts/list_queues.py                     # 3 filas visíveis
wsl.exe docker ps --filter name=sb-consumer       # 3 containers healthy
wsl.exe docker logs -f sb-consumer-contatos       # logs do pod novo
```

---

## Observações

- `cpf` e `telefone` **dependem do checkout** passar a enviá-los. Enquanto
  não enviarem, o handler omite os campos (política `drop None` herdada).
- `CPF__c` na demo vai como Text sem Unique. Em produção é fortemente
  recomendado Unique + External ID (ajuda deduplicação de cadastros).
- Se no futuro vier `data_nascimento`, `genero`, ou endereço completo, basta
  estender `sf_create_contact_fields.py` com os campos novos e popular no
  handler — o padrão já está estabelecido e replicável.

---

## Referências

- `docs/architecture.md` — decisões gerais do middleware (peek-lock,
  idempotência, retry/DLQ).
- `docs/message-flow.md` — sequence diagrams do fluxo atual (a ser
  atualizado quando esta implementação for concluída).
- `docs/message-contract.md` — schemas canônicos dos tipos existentes
  (seção 2.4 a ser adicionada quando `aluno_cadastrado` entrar em produção).
- `src/middleware/integrations/salesforce/service.py` — padrão de todos os
  métodos já existentes (ensure_account, upsert_contact, find/upsert Opp).
- `scripts/sf_create_opportunity_fields.py` — referência estrutural para
  criar `sf_create_contact_fields.py`.
