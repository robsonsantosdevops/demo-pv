# Message Contract

Contrato das mensagens trocadas via Azure Service Bus entre Checkout,
Middleware, Salesforce (via Apex) e SAP B1. Este documento é **canônico** —
qualquer producer ou consumer novo deve respeitar este formato.

---

## 1. Envelope comum

Toda mensagem tem 3 camadas:

### 1.1 Body (JSON)
```json
{
  "tipo":      "<string>",
  "payload":   { ... objeto específico do tipo ... },
  "timestamp": "2026-04-23T01:23:04.000Z"
}
```
`timestamp` = momento em que o body foi serializado, ISO-8601 com sufixo `Z`.

### 1.2 Application Properties (headers custom do Service Bus)

| Chave | Obrigatório | Observação |
|---|---|---|
| `tipo` | **sim** | Replica `body.tipo`. Usado pelo dispatcher — é a chave de roteamento. |
| `traceparent` | não | W3C Trace Context propagado do producer. |
| `DeadLetterReason` | automático | Presente só na DLQ. Set pelo SB ou pelo handler. |
| `redriven_from` | automático | Set pelo `scripts/redrive_dlq.py` quando uma mensagem é reinjetada. |

### 1.3 Propriedades nativas

| Propriedade | Formato | Observação |
|---|---|---|
| `messageId` | `<tipo>-<epoch_ms>-<rand6>` ex: `pedido_criado-1776893956829-hbtbxb` | Padrão estabelecido pelo checkout e replicado pelo Apex. |
| `content_type` | `application/json` | Sempre. |
| `correlation_id` (na message) | opcional | Pode ser usado em vez do `payload.correlation_id`; hoje preferimos o do payload. |

### 1.4 Convenção de `correlation_id` (no payload)

Rastreia uma jornada inteira end-to-end, do checkout ao SAP:

| Origem | Formato típico | Exemplo |
|---|---|---|
| Checkout | `jornada-<aluno_id>-<uuid>` | `jornada-15-eb95389c-ba59-...` |
| Apex (SF trigger) | `sf-<OppId>` | `sf-006g5000003O0d3AAC` |
| Scripts de teste | `jornada-teste-<uuid>` / custom via `--correlation-id` | livre |

**Não se deriva** — é criado no início da jornada e propagado tal-qual por
todos os producers e handlers.

---

## 2. Tipos

### 2.1 `pedido_criado`

- **Fila**: `pedidos`
- **Producer**: Checkout (Node) quando o pedido é submetido, antes do pagamento.
- **Handler**: `middleware.handlers.pedido_criado.PedidoCriadoHandler`
- **Destino**: Salesforce — cria/atualiza Account master + Contact (por email)
  + Opportunity (upsert por `Correlation_Id__c`). StageName inicial:
  `Prospecting`.

#### Schema do payload

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `correlation_id` | string | **sim** | Chave idempotente na Opp. |
| `pedido_id` | int | sim (nice-to-have) | Armazenado em `Pedido_Id__c`. |
| `numero_pedido` | string | **sim** | Vira `Opportunity.Name`. |
| `aluno_id` | int | — | `Aluno_Id__c`. |
| `aluno_nome` | string | **sim** | `Aluno_Nome__c` + Contact.FirstName/LastName. |
| `aluno_email` | string (email) | **sim** | `Aluno_Email__c` + Contact.Email (chave de upsert do Contact). |
| `total` | string ou number | **sim** | Convertido a float → `Amount`. |
| `parcelas` | int | — | `Parcelas__c`. |
| `status` | string | — | `Status_Checkout__c` (ex.: `aguardando_pagamento`). |
| `itens` | array de objetos | — | Serializado em `Itens_Json__c` (LongTextArea, truncado em 32K). |
| `itens[].curso_id` | string | — | Identificador do curso. |
| `itens[].curso_titulo` | string | — | Nome legível. |
| `itens[].quantidade` | int | — | — |
| `itens[].preco_unitario` | number | — | — |
| `created_at` | ISO-8601 string | — | `Pedido_Created_At__c`. |
| `curso_nome` (futuro) | string | — | **Reservado** — ainda não enviado pelo checkout. |
| `curso_descricao` (futuro) | string | — | **Reservado**. |

#### Exemplo real
```json
{
  "correlation_id": "jornada-15-eb95389c-ba59-4612-a036-7a8ad927b0b0",
  "pedido_id": 27,
  "numero_pedido": "PED-MOADP4R3-3AQ",
  "aluno_id": 15,
  "aluno_nome": "Vinte tres",
  "aluno_email": "vintetres@email.com",
  "total": "12990.00",
  "parcelas": 10,
  "status": "aguardando_pagamento",
  "itens": [
    {"curso_id": "enem-online", "curso_titulo": "Enem Online", "quantidade": 1, "preco_unitario": 12990}
  ],
  "created_at": "2026-04-22T18:20:55.504Z"
}
```

#### Validações e decisões do handler

| Condição | Resultado |
|---|---|
| Falta `correlation_id`/`numero_pedido`/`aluno_nome`/`aluno_email`/`total` | **DLQ** `missing_required` |
| `total` não parseável como float | **DLQ** `invalid_total:<valor>` |
| Payload OK, Opp não existe pra esse `correlation_id` | **ACK**, Opp criada em `Prospecting` |
| Payload OK, Opp já existe | **ACK**, update (não rebaixa stage se já for Closed Won) |

#### Idempotência
`PATCH /sobjects/Opportunity/Correlation_Id__c/<correlation_id>` é atômico.
Mensagens duplicadas com mesmo `correlation_id` acabam como uma só Opp.

---

### 2.2 `pagamento_aprovado`

- **Fila**: `pedidos`
- **Producer**: Checkout (Node) quando o gateway de pagamento aprova.
- **Handler**: `middleware.handlers.pagamento_aprovado.PagamentoAprovadoHandler`
- **Destino**: Salesforce — busca Opp por `Correlation_Id__c` (fallback por
  `Name`) e atualiza para Closed Won com dados de pagamento.

#### Schema do payload

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `correlation_id` | string | **sim** | Deve bater com o do `pedido_criado` correspondente. |
| `pagamento_id` | int | — | `Pagamento_Id__c`. |
| `protocolo` | string | — | `Pagamento_Protocolo__c` (ex.: `PAG-1776-811`). |
| `pedido_id` | int | — | — |
| `numero_pedido` | string | **sim** | Usado no fallback de busca da Opp. |
| `aluno_id`, `aluno_nome`, `aluno_email` | — | — | Não re-populam na Opp (já foram no `pedido_criado`). |
| `forma_pagamento` | string | — | `Forma_Pagamento__c`. Valores válidos no picklist: `pix`, `cartao_credito`, `cartao_debito`, `boleto`. |
| `valor` | string ou number | **sim** | Float → `Amount` (sobrescreve o de `pedido_criado`). |
| `parcelas` | int | — | — |
| `status_pagamento` | string | — | `Status_Pagamento__c` (`aprovado`/`recusado`/`pendente`/`estornado`). |
| `status_pedido` | string | — | `Status_Pedido__c`. |
| `cartao_final` | string(4) \| null | — | Só preenchido em cartão; `null` em pix/boleto — nesse caso **o handler omite a chave** (não escreve `null` no SF). |
| `created_at` | ISO-8601 string | — | Merged no `Description`. |

#### Exemplo real
```json
{
  "correlation_id": "jornada-15-eb95389c-ba59-4612-a036-7a8ad927b0b0",
  "pagamento_id": 10,
  "protocolo": "PAG-1776882057066-811",
  "pedido_id": 27,
  "numero_pedido": "PED-MOADP4R3-3AQ",
  "aluno_id": 15,
  "aluno_nome": "Vinte tres",
  "aluno_email": "vintetres@email.com",
  "forma_pagamento": "pix",
  "valor": "12990.00",
  "parcelas": 10,
  "status_pagamento": "aprovado",
  "status_pedido": "pago",
  "cartao_final": null,
  "created_at": "2026-04-22T18:20:57.067Z"
}
```

#### Validações e decisões do handler

| Condição | Resultado |
|---|---|
| Falta `correlation_id`/`numero_pedido`/`valor` | **DLQ** `missing_required` |
| `valor` não parseável | **DLQ** `invalid_valor:<valor>` |
| Opp não encontrada (nem por correlation nem por name) | **RETRY** `opp_not_found:<corr>/<num>` — assume ordem invertida, `pedido_criado` ainda não foi processado |
| Opp já em `Closed Won` | **ACK** sem update (idempotente) |
| Opp encontrada → update `StageName=Closed Won`, campos de pagamento | **ACK** |

#### Ordem invertida
Se `pagamento_aprovado` chegar antes de `pedido_criado` (raro, mas
possível em entrega paralela), o handler retorna RETRY. O consumer faz
`abandon_message` → a mensagem volta pra `active`, `delivery_count++`. Em
~segundos o `pedido_criado` é processado (cria a Opp), e na redelivery
seguinte o `pagamento_aprovado` encontra e fecha. Após `max_delivery_count=5`
sem sucesso, vai pra DLQ.

---

### 2.3 `oportunidade_ganha`

- **Fila**: `oportunidades`
- **Producer**: trigger Apex no Salesforce quando uma `Opportunity` passa
  a `StageName=Closed Won`.
- **Handler**: `middleware.handlers.oportunidade_ganha.OportunidadeGanhaHandler`
- **Destino**: SAP B1 — cria `POST /Orders` com defaults (CardCode,
  ItemCode, BPL_ID vindo do env). Idempotente por `NumAtCard = opportunity_id`.

#### Schema do payload

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `correlation_id` | string | **sim** | Ex.: `sf-<OppId>`. |
| `opportunity_id` | string (SF ID) | **sim** | Vira `Order.NumAtCard` — chave idempotente. |
| `name` | string | **sim** | Entra em `Order.Comments` e no log. |
| `amount` | number | **sim** | Vira `DocumentLines[0].UnitPrice`. |
| `close_date` | ISO date `YYYY-MM-DD` | — | Registrado nos `Comments`. |
| `account_id` | string | — | SF AccountId (não é mapeado pra SAP — a demo usa `SAP_DEFAULT_CARDCODE` fixo). |
| `owner_id` | string | — | SF UserId. |

#### Exemplo real
```json
{
  "correlation_id": "sf-006g5000003O0d3AAC",
  "opportunity_id": "006g5000003O0d3AAC",
  "name": "PED-DEMO-SF-03",
  "amount": 12990.0,
  "close_date": "2026-04-22",
  "account_id": "001g500000JHYNJAA5",
  "owner_id": "005g5000005FrKTAA0"
}
```

#### Validações e decisões do handler

| Condição | Resultado |
|---|---|
| Falta `opportunity_id`/`name`/`amount` | **DLQ** `missing_required` |
| `amount` não parseável | **DLQ** `invalid_amount:<valor>` |
| `sessionId` vazio no env | **RETRY** `sap_session_unavailable` (próximo retry pode pegar env atualizado) |
| SAP devolve 4xx (≠ 401/408/429) | **DLQ** `sap_http_<code>:<body>` (erro de validação, retry não vai resolver) |
| SAP devolve 401, 408, 429, 5xx, network error | **RETRY** |
| Filter pré-create encontra Order com `NumAtCard == opportunity_id` | **ACK** sem POST (idempotente) |
| Filter falha (erro de rede/permissão) | Fail-open: segue pro POST (melhor duplicata que parar fila) |
| Happy path | **ACK**, `Order.DocEntry` retornado no log |

#### Payload do POST /Orders (montado pelo handler)
```json
{
  "DocDate": "2026-04-23T00:00:00Z",
  "DocDueDate": "2026-05-23T00:00:00Z",
  "CardCode": "C40000",
  "BPL_IDAssignedToInvoice": 1,
  "NumAtCard": "006g5000003O0d3AAC",
  "Comments": "Opp SF: PED-DEMO-SF-03 (006g5000003O0d3AAC) | correlation_id: sf-006g5000003O0d3AAC | close_date: 2026-04-22 | account_id: 001g500000JHYNJAA5 | owner_id: 005g5000005FrKTAA0",
  "DocumentLines": [
    {"ItemCode": "S10000", "Quantity": 1.0, "UnitPrice": 12990.0}
  ]
}
```
- `CardCode`, `ItemCode`, `BPL_IDAssignedToInvoice` vêm de env vars
  (`SAP_DEFAULT_CARDCODE`, `SAP_DEFAULT_ITEM_CODE`, `SAP_DEFAULT_BPL_ID`).
- `NumAtCard` **sempre** é o `opportunity_id` — essa convenção é o que
  permite a idempotência. Qualquer outro producer que publique em `oportunidades`
  deve manter a convenção.

---

### 2.4 `aluno_cadastrado`

- **Fila**: `contatos`
- **Producer**: Checkout (Node) quando o aluno finaliza cadastro no site.
- **Handler**: `middleware.handlers.aluno_cadastrado.AlunoCadastradoHandler`
- **Destino**: Salesforce — upsert Contact por External ID `Aluno_Id__c`.

#### Schema do payload

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `aluno_id` | int | **sim** | External ID no SF (`Aluno_Id__c`). Chave idempotente. |
| `nome_completo` | string | **sim** | Split em `FirstName` / `LastName`. |
| `email` | string (email) | **sim** | `Email` do Contact. Fallback de match para Contacts mínimos. |
| `correlation_id` | string | — | ID da jornada. Se omitido, o handler deriva `cadastro-<aluno_id>-<messageId>`. |
| `cpf` | string | — | `CPF__c` Text(14). String vazia `""` tratada como ausente. |
| `telefone` | string | — | `Phone` (campo standard). String vazia `""` tratada como ausente. |
| `created_at` | ISO-8601 string | — | Apenas referência; não é gravado. |

#### Exemplo real (publicado pelo checkout)
```json
{
  "aluno_id": 27,
  "nome_completo": "Yasmin Araujo Santos Lope",
  "email": "yaslopesyweba@gmail.com",
  "telefone": "",
  "created_at": "2026-04-24T03:45:44.567Z"
}
```

> Na POC atual, o checkout omite `correlation_id`; o handler deriva
> `cadastro-<aluno_id>-<messageId>` pra preservar rastreio nos logs.

#### Validações e decisões do handler

| Condição | Resultado |
|---|---|
| Falta `aluno_id` / `nome_completo` / `email` | **DLQ** `missing_required:<campos>` |
| `aluno_id` não é inteiro | **DLQ** `invalid_aluno_id` |
| Contact com `Aluno_Id__c == aluno_id` existe | **ACK**, PATCH merge |
| Contact não existe por id mas existe por email (mínimo criado pelo fallback de `pedido_criado`) | **ACK**, PATCH "promove" preenchendo `Aluno_Id__c` + campos |
| Nenhum Contact existente | **ACK**, POST Contact novo |

#### Idempotência
`Aluno_Id__c` é Unique + External ID. Reentregas da mesma mensagem casam pelo
mesmo Contact e só re-aplicam o PATCH.

---

## 3. Como adicionar um novo tipo

1. **Producer**: publicar com `application_properties.tipo=<novo>` na fila
   apropriada, `messageId` no padrão, payload com `correlation_id`.
2. **Consumer** (este projeto):
   - Criar `src/middleware/handlers/<novo>.py` implementando `Handler`.
   - Registrar no dispatcher dentro de `src/middleware/__main__.py:_build_handlers`.
   - Adicionar em `src/middleware/dispatcher.py:KNOWN_TYPES` (trava pra que
     tipo desconhecido vá pra DLQ explícita).
   - Teste em `tests/test_handler_<novo>.py`.
3. Documentar aqui (seção 2.x) antes de mergear.

---

## 4. Erros comuns e como identificar

| Sintoma | Causa provável |
|---|---|
| `DeadLetterReason=unknown_type` | Producer publicando tipo errado ou na fila errada. Ver `application_properties.tipo` vs fila. |
| `DeadLetterReason=invalid_json` | Body não é JSON válido. Producer serializou mal. |
| `DeadLetterReason=missing_payload` | Body não tem `payload` ou não é objeto. |
| `DeadLetterReason=missing_required:*` | Producer não mandou campo obrigatório do schema. |
| `DeadLetterReason=sap_http_4xx:...` | Order rejeitada pelo SAP (CardCode inexistente, ItemCode inválido, etc.). Corrigir defaults. |
| Várias Orders pra mesma Opp | Mensagem publicada com `NumAtCard` diferente (ou antes do fix de idempotência). Cancelar manualmente no SAP. |

Ver também `docs/runbook.md` seção 10 (Troubleshooting).
