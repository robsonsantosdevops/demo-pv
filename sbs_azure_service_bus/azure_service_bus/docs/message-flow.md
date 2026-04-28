# Fluxo de mensagens — detalhado

Como as 3 mensagens (`pedido_criado`, `pagamento_aprovado`,
`oportunidade_ganha`) fluem pelas 2 filas (`pedidos`, `oportunidades`) e
quais interações cada consumer executa. Complementa `docs/demo-overview.md`
(topologia) com o "quem fala com quem" passo-a-passo.

Para referência dos schemas de cada mensagem, ver
`docs/message-contract.md`.

---

## 1. Jornada completa (happy path)

```mermaid
sequenceDiagram
    autonumber
    actor Aluno
    participant Site as Checkout<br/>(Yasmin)
    participant PQ as fila<br/>pedidos
    participant MW1 as Middleware<br/>(QUEUE_NAME=pedidos)
    participant SF as Salesforce
    participant Apex as Apex Trigger<br/>OpportunityGanha
    participant OQ as fila<br/>oportunidades
    participant MW2 as Middleware<br/>(QUEUE_NAME=oportunidades)
    participant SAP as SAP B1<br/>Service Layer

    %% ── leg 1: pedido → SF ───────────────────────────────────
    Aluno->>Site: finaliza carrinho
    Site->>PQ: publish pedido_criado<br/>(correlation_id, pedido_id, aluno, itens)
    PQ-->>MW1: peek-lock (at-least-once)
    MW1->>SF: ensure Account "Checkout Keeggo - Alunos"
    MW1->>SF: upsert Contact by Email
    MW1->>SF: PATCH /Opportunity/Correlation_Id__c/{corr}
    Note over MW1,SF: upsert nativo via External ID<br/>cria ou atualiza, atomicamente
    SF-->>MW1: 201/204 + id
    MW1-->>PQ: complete_message

    %% ── leg 2: pagamento → SF Closed Won ─────────────────────
    Aluno->>Site: conclui pagamento (pix)
    Site->>PQ: publish pagamento_aprovado<br/>(mesmo correlation_id, valor, forma)
    PQ-->>MW1: peek-lock
    MW1->>SF: SOQL find Opportunity<br/>WHERE Correlation_Id__c = ?
    SF-->>MW1: Opp existente (Prospecting)
    MW1->>SF: PATCH /Opportunity/{id}<br/>StageName=Closed Won + dados pagto
    SF-->>MW1: 204
    MW1-->>PQ: complete_message

    %% ── leg 3: Apex → SAP ────────────────────────────────────
    SF->>Apex: trigger (StageName → Closed Won)
    Apex->>OQ: publish oportunidade_ganha<br/>(opportunity_id, name, amount, ...)
    OQ-->>MW2: peek-lock
    MW2->>SAP: GET /Orders?$filter=NumAtCard eq {opp_id}
    SAP-->>MW2: [ ] (vazio — primeira vez)
    MW2->>SF: GET /Opportunity/{id}?fields=Curso_Nome__c,<br/>Aluno_Nome__c,Aluno_Email__c,Pedido_Id__c,...
    Note over MW2,SF: enrichment — puxa dados<br/>que o Apex não mandou
    SF-->>MW2: { Curso_Nome__c: "Medicina Online", ... }
    MW2->>SAP: POST /Orders<br/>NumAtCard + Comments resumido<br/>+ 8 UDFs (U_SF_OppId, U_Curso_Nome, ...)
    SAP-->>MW2: 201 { DocEntry, DocNum }
    MW2-->>OQ: complete_message
```

**Observações sobre a numeração:**
- Passos 1-9: leg de `pedido_criado` (cria Opp em Prospecting).
- Passos 10-16: leg de `pagamento_aprovado` (fecha a mesma Opp).
- Passos 17-24: leg de `oportunidade_ganha` (cria Order no SAP).

Total: entre 15 e 20 chamadas HTTP entre sistemas, todas com retry e
idempotência nativas.

---

## 2. O que acontece em cada fila

### Fila `pedidos`
- **Producer**: Checkout (Node).
- **Consumer**: Middleware rodando com `QUEUE_NAME=pedidos` (pod #1).
- **Tipos aceitos**: `pedido_criado`, `pagamento_aprovado`.
- **Destino de sucesso**: Salesforce (Account/Contact/Opportunity).
- **Chave idempotente**: `payload.correlation_id` → `Opportunity.Correlation_Id__c`.

### Fila `oportunidades`
- **Producer**: Apex Trigger `OpportunityGanhaTrigger` no Salesforce.
- **Consumer**: Middleware rodando com `QUEUE_NAME=oportunidades` (pod #2).
- **Tipo aceito**: `oportunidade_ganha`.
- **Destino de sucesso**: SAP B1 Service Layer (Sales Order).
- **Chave idempotente**: `payload.opportunity_id` → `Order.NumAtCard`.

---

## 3. Caminhos alternativos

### 3.1 Ordem invertida — `pagamento_aprovado` chega antes de `pedido_criado`

```mermaid
sequenceDiagram
    participant Site as Checkout
    participant PQ as fila pedidos
    participant MW1 as Middleware pedidos
    participant SF as Salesforce

    Site->>PQ: pagamento_aprovado (chega antes)
    PQ-->>MW1: peek-lock
    MW1->>SF: SOQL find Opp by Correlation_Id__c
    SF-->>MW1: (vazia — pedido_criado ainda não veio)
    MW1-->>PQ: abandon_message<br/>(HandleResult.retry "opp_not_found")
    Note over PQ: delivery_count++<br/>mensagem volta para active

    Site->>PQ: pedido_criado (chega agora)
    PQ-->>MW1: peek-lock
    MW1->>SF: upsert Opportunity
    SF-->>MW1: ok
    MW1-->>PQ: complete_message

    PQ-->>MW1: redelivery pagamento_aprovado
    MW1->>SF: SOQL find Opp
    SF-->>MW1: Opp encontrada
    MW1->>SF: PATCH Closed Won
    MW1-->>PQ: complete_message
```

Depois de `max_delivery_count=5` sem sucesso, a mensagem vai automaticamente
para a DLQ com `reason=MaxDeliveryCountExceeded`.

### 3.2 Idempotência SAP — `oportunidade_ganha` duplicada

```mermaid
sequenceDiagram
    participant Apex as Apex Trigger
    participant OQ as fila oportunidades
    participant MW2 as Middleware oportunidades
    participant SAP as SAP B1

    Apex->>OQ: oportunidade_ganha (1ª vez)
    OQ-->>MW2: peek-lock
    MW2->>SAP: GET /Orders?$filter=NumAtCard eq {opp_id}
    SAP-->>MW2: [ ] vazio
    MW2->>SAP: POST /Orders (NumAtCard + UDFs)
    SAP-->>MW2: 201 DocEntry=A
    MW2-->>OQ: complete_message

    Apex->>OQ: oportunidade_ganha (mesma Opp, 2ª vez)
    OQ-->>MW2: peek-lock
    MW2->>SAP: GET /Orders?$filter=NumAtCard eq {opp_id}
    SAP-->>MW2: [ { DocEntry: A } ]
    Note over MW2,SAP: skip — Order já existe
    MW2-->>OQ: complete_message (sem POST extra)
```

### 3.3 Enrichment com fallback — Salesforce fora do ar

```mermaid
sequenceDiagram
    participant OQ as fila oportunidades
    participant MW2 as Middleware oportunidades
    participant SF as Salesforce
    participant SAP as SAP B1

    OQ-->>MW2: oportunidade_ganha
    MW2->>SAP: GET /Orders?$filter=NumAtCard eq...
    SAP-->>MW2: [ ] vazio
    MW2->>SF: GET /Opportunity/{id}?fields=...
    SF--xMW2: timeout / 5xx
    Note over MW2: fail-soft: segue<br/>sem enrichment
    MW2->>SAP: POST /Orders<br/>(só campos básicos do payload)
    SAP-->>MW2: 201 DocEntry=X
    MW2-->>OQ: complete_message
```

A Order é criada com os campos mínimos (vindos do payload) e `Comments`
básico. Sem `Curso_Nome__c`, `Aluno_Email__c`, etc. — mas a demo continua
fluindo.

---

## 4. Caminhos de erro (DLQ)

```mermaid
flowchart TD
    Msg[Mensagem chega] --> Parse{body é JSON válido?}
    Parse -- não --> DLQ1[DLQ reason=invalid_json]
    Parse -- sim --> HasPayload{tem 'payload' dict?}
    HasPayload -- não --> DLQ2[DLQ reason=missing_payload]
    HasPayload -- sim --> KnownType{tipo registrado<br/>para esta fila?}
    KnownType -- não --> DLQ3[DLQ reason=unknown_type]
    KnownType -- sim --> Handler[executa handler]
    Handler --> Res{HandleResult}
    Res -- ok --> ACK[complete_message]
    Res -- retry --> Abandon[abandon_message<br/>delivery_count++]
    Res -- dlq --> DLQ4[DLQ reason=&lt;handler&gt;]
    Abandon --> MaxCheck{delivery_count<br/>> max_delivery_count?}
    MaxCheck -- sim --> DLQ5[DLQ reason=MaxDeliveryCountExceeded]
    MaxCheck -- não --> Reenqueue[volta para active]

    classDef ok fill:#e6f4ea,stroke:#34a853
    classDef dlq fill:#fce8e6,stroke:#ea4335
    classDef flow fill:#fef7e0,stroke:#fbbc04
    class ACK ok
    class DLQ1,DLQ2,DLQ3,DLQ4,DLQ5 dlq
    class Handler,Parse,HasPayload,KnownType,Res,MaxCheck,Abandon,Reenqueue flow
```

**Tipos de falha por handler (pra contexto):**

| Handler | Condição | Ação |
|---|---|---|
| `pedido_criado` | payload sem `numero_pedido`/`pedido_id`/`aluno_nome`/... | DLQ `missing_required` |
| `pedido_criado` | `total` não-parseável | DLQ `invalid_total` |
| `pagamento_aprovado` | Opp não encontrada | RETRY `opp_not_found` (ordem invertida) |
| `oportunidade_ganha` | `sessionId` SAP vazio | RETRY `sap_session_unavailable` |
| `oportunidade_ganha` | SAP retorna 4xx (≠401/408/429) | DLQ `sap_http_4xx` |
| `oportunidade_ganha` | SAP retorna -2014 (schema stale) | RETRY `sap_schema_stale` |
| `oportunidade_ganha` | SAP 5xx / network | RETRY `sap_http_5xx` / `sap_network` |

Ver `docs/runbook.md` seção 5 e 10 para procedimentos de DLQ e
troubleshooting.

---

## 5. Rastreabilidade de ponta a ponta

Três identificadores são propagados pela jornada inteira:

| ID | Nascimento | Onde vai parar |
|---|---|---|
| `correlation_id` | Checkout (`jornada-<aluno_id>-<uuid>`) | `Opportunity.Correlation_Id__c` (SF) + `NumAtCard` (SAP via Apex) + todo log JSON |
| `pedido_id` | Checkout (numérico) | `Opportunity.Pedido_Id__c` (SF) + `U_Pedido_Id` (SAP UDF) |
| `opportunity_id` | Salesforce (autogerado) | `payload.opportunity_id` (msg Apex) + `Order.NumAtCard` (SAP) + `U_SF_OppId` (SAP UDF) |

Para debugar uma jornada específica, use `correlation_id`:

```bash
wsl.exe docker logs sb-consumer-pedidos 2>&1 | grep 'correlation_id":"jornada-1-831294cb'
wsl.exe docker logs sb-consumer-oportunidades 2>&1 | grep 'correlation_id":"sf-006g5000003'
```

Ou busque no SAP por `NumAtCard` (= opportunity_id SF) ou no SF por
`Correlation_Id__c`.
