# Plano — Middleware Azure Service Bus (demo Keeggo)

> **Documento vivo.** Reflete o estado atual da implementação. Para o dia-a-dia
> de operação das filas, consulte `docs/runbook.md`; para deploy em contêiner,
> `deploy/README.md`.

## Context

O projeto `azure_service_bus` é o **consumer middleware** que fecha o fluxo de
integração da demo Keeggo entre Checkout (site), Salesforce e SAP B1:

```
a) Checkout (site) ──► b) Service Bus ──► c) Salesforce ──► d) Service Bus ──► e) SAP B1
                              │                                     │
                              └─── consumer middleware (este) ──────┘
```

O middleware:
1. Consome `pedidos` (tipos `pedido_criado`, `pagamento_aprovado`) e
   cria/atualiza registros no **Salesforce** (leg b→c).
2. Consome `oportunidades` (tipo `oportunidade_ganha`, publicado pelo trigger
   Apex) e cria pedidos de venda no **SAP B1 Service Layer** (leg d→e).

Restrições (cravadas pelos producers):
- **Formato de mensagem imutável**: `body = {tipo, payload, timestamp}`,
  `application_properties.tipo` (+ `traceparent` W3C),
  `messageId = <tipo>-<epoch_ms>-<rand6>`.
- **Idempotência via `payload.correlation_id`**.
- **At-least-once** com peek-lock (não `receive-and-delete`).
- **Execução em contêiner**: JSON logs em stdout, graceful shutdown em SIGTERM,
  healthcheck HTTP em `/healthz` e `/ready`.

---

## Status das etapas

| # | Etapa | Status |
|---|---|---|
| 1 | Bootstrap (estrutura, deps, Makefile, pyproject) | ✅ feito |
| 2 | Núcleo do consumer (config, logger, dispatcher, consumer, health) | ✅ feito |
| 3 | Integração Salesforce (vendor + handlers + 17 campos custom) | ✅ feito |
| 4 | Fila `oportunidades` provisionada (via `scripts/create_queues.py`) | ✅ feito |
| 5 | Integração SAP (vendor + handler + idempotência via `NumAtCard`) | ✅ feito |
| 6 | Dockerfile multi-stage (build local precisa de Docker instalado) | ✅ feito |
| 7 | Testes pytest (59 testes, cobrem config/dispatcher/3 handlers/service SF/session SAP) | ✅ feito |
| 8 | README.md principal + `docs/architecture.md` + `docs/message-contract.md` | ✅ feito |

---

## Decisões de design (resumo)

### Filas
Duas filas distintas, DLQ independente (escalabilidade e isolamento por
integração):
- **`pedidos`** — tipos `pedido_criado`, `pagamento_aprovado` → Salesforce
- **`oportunidades`** — tipo `oportunidade_ganha` → SAP B1

Parâmetros padrão (em `scripts/create_queues.py`): `lock_duration=5min`,
`max_delivery_count=5`, `ttl=14 dias`, `dlqOnExpire=True`.

### Salesforce
- **Cliente vendored** de `salesforce-admin\client.py` em
  `src/middleware/integrations/salesforce/`. Adaptação: config injetada no
  construtor (não global), logger stdlib. Ver `integrations/salesforce/ORIGIN.md`.
- **Autenticação**: OAuth2 user+password com fallbacks (SOAP, Salesforce CLI
  client_ids).
- **Idempotência nativa via External ID**: `PATCH /sobjects/Opportunity/Correlation_Id__c/<valor>`.
  Cria se não existe, atualiza se existe — um único round-trip.
- **Schema custom** (17 campos em `Opportunity`, criados via
  `scripts/sf_create_opportunity_fields.py` + FLS automática no profile do user):
  - **Chave idempotente**: `Correlation_Id__c` (Unique + External ID)
  - **External IDs**: `Pedido_Id__c`, `Aluno_Id__c`, `Pagamento_Id__c`
  - **Aluno**: `Aluno_Nome__c`, `Aluno_Email__c`
  - **Pedido**: `Parcelas__c`, `Pedido_Created_At__c`, `Status_Checkout__c`, `Itens_Json__c`
  - **Pagamento**: `Pagamento_Protocolo__c`, `Forma_Pagamento__c`, `Status_Pagamento__c`, `Status_Pedido__c`, `Cartao_Final__c`
  - **Reservados (ficam vazios até o checkout passar a enviar)**:
    `Curso_Nome__c`, `Curso_Descricao__c`
- **Account master**: uma Account genérica chamada *"Checkout Keeggo - Alunos"*
  sob a qual todos os Contacts são criados (1 por email). O campo
  `SF_ACCOUNT_MASTER_EXTRA` (JSON no env) injeta campos obrigatórios da org na
  criação — na demo Keeggo é `{"cnpj__c":"00000000000000"}`.

### SAP B1 Service Layer
- **Cliente vendored** de `sap-automation-lab\src\sap_client.py` em
  `src/middleware/integrations/sap/`. Adaptações:
  - Session token **não** armazenado no client — a cada request vem via
    `SapSession` que lê a env var `sessionId` (case-sensitive) do ambiente.
  - **Retry automático em 401**: se o Service Layer recusar a sessão, o client
    chama `session.refresh()` (relê env) e refaz 1x.
- **Endpoint principal**: `POST /b1s/v2/Orders` com payload `DocDate`,
  `DocDueDate`, `CardCode`, `BPL_IDAssignedToInvoice`, `DocumentLines[]`,
  `Comments`, e agora **`NumAtCard = opportunity_id`**.
- **Idempotência**: via `NumAtCard` (customer reference, varchar 100, filtrável
  nativamente com `eq`). Antes de criar, handler consulta
  `/Orders?$filter=NumAtCard eq '<opp_id>'` — se existe, pula.
  - *Por que não `Comments`?* `Comments` é memo field, SAP B1 não suporta
    `contains` sobre ele.
- **Cluster**: no Kubernetes, a env var `sessionId` é atualizada por um job
  externo a cada ~30 min. Em dev, `.env` fornece o valor manualmente (obtido
  via `POST /b1s/v2/Login`).

### Containerização
Dockerfile multi-stage (`python:3.12-slim`), usuário não-root (UID 10001),
`HEALTHCHECK` via `curl` em `/healthz`. Imagem final ~130 MB. Manifests
Kubernetes ficam para a próxima iteração (quando detalhes do cluster demo
estiverem definidos).

---

## Estrutura do projeto

```
azure_service_bus/
├── src/middleware/
│   ├── __init__.py, __main__.py     # entrypoint: python -m middleware
│   ├── config.py                     # env + validação de QUEUE_NAME
│   ├── logging_setup.py              # JSON logger (stdout + logs/app.log)
│   ├── consumer.py                   # peek-lock loop + SIGTERM graceful
│   ├── dispatcher.py                 # (fila, tipo) → handler injetado
│   ├── health.py                     # /healthz + /ready em thread
│   ├── handlers/
│   │   ├── base.py                   # Handler protocol + HandleResult
│   │   ├── pedido_criado.py          # upsert Opp via Correlation_Id__c
│   │   ├── pagamento_aprovado.py     # fecha Opp em Closed Won
│   │   └── oportunidade_ganha.py     # Order SAP com idempotência NumAtCard
│   └── integrations/
│       ├── salesforce/               # client.py, config.py, service.py, ORIGIN.md
│       └── sap/                      # client.py, config.py, session.py, ORIGIN.md
├── scripts/                          # 8 ferramentas de ops (ver abaixo)
├── tests/                            # ⏳ Etapa 7 pendente
├── deploy/
│   ├── Dockerfile                    # multi-stage
│   ├── .dockerignore
│   └── README.md                     # build / run / troubleshooting
├── docs/
│   ├── runbook.md                    # ops de filas, DLQ, troubleshooting
│   ├── architecture.md               # diagrama, decisões, observabilidade
│   └── message-contract.md           # schema canônico dos 3 tipos
├── logs/                             # gitignored
├── .env.example, .gitignore
├── requirements.txt, requirements-dev.txt
├── pyproject.toml, Makefile
├── PLAN.md                           # este arquivo
└── README.md                         # ponto de entrada rápido
```

### Scripts de operação em `scripts/`

| Script | Propósito |
|---|---|
| `create_queues.py`               | Provisiona `pedidos`/`oportunidades` no namespace (idempotente). |
| `list_queues.py`                 | Conta mensagens active/DLQ por fila. |
| `receive.py [queue] [--max N]`   | Peek; sem argumento, lista todas as filas e peeka em cada. |
| `send.py --tipo X ...`           | Publica mensagem de teste nos 3 tipos conhecidos. |
| `purge_queue.py`                 | Drena fila/DLQ com filtro por tipo (ops de limpeza). |
| `redrive_dlq.py --from A --to B` | Reinjeta da DLQ de A para B preservando metadados. |
| `sap_get_order.py`               | Consulta Orders no SAP B1 (por DocEntry ou `--recent N`). |
| `sf_create_opportunity_fields.py`| Cria os 17 custom fields em `Opportunity` (Tooling API) + FLS. |

---

## Verificação (end-to-end — já executada)

### Local
1. `pip install -r requirements.txt -r requirements-dev.txt`
2. `.env` com `AZURE_SERVICE_BUS_CONNECTION_STRING`, credenciais SF, `sessionId` SAP
3. `python scripts/create_queues.py` (idempotente; já provisionadas)
4. `python scripts/sf_create_opportunity_fields.py` (idempotente; já criados)
5. Consumer pedidos → SF:
   ```bash
   QUEUE_NAME=pedidos python -m middleware
   ```
6. Consumer oportunidades → SAP:
   ```bash
   QUEUE_NAME=oportunidades python -m middleware
   ```
7. Smoke test SF (validado):
   ```bash
   python scripts/send.py --queue pedidos --numero-pedido PED-TEST --correlation-id ct
   python scripts/send.py --queue pedidos --tipo pagamento_aprovado \
       --numero-pedido PED-TEST --correlation-id ct
   ```
   → Opp criada em Prospecting, depois Closed Won, com todos os campos custom
   populados.

8. Smoke test SAP (validado):
   ```bash
   python scripts/send.py --tipo oportunidade_ganha --opp-id OPP-1 --amount 999
   ```
   → Order criada no SAP com `NumAtCard=OPP-1`. Republicar mesma `opp-id` não
   cria nova Order (idempotência).

### Contêiner
```bash
docker build -t sb-middleware:dev -f deploy/Dockerfile .
docker run --rm --env-file .env -e QUEUE_NAME=pedidos -p 8080:8080 sb-middleware:dev
curl localhost:8080/healthz  # 200
curl localhost:8080/ready    # 200 após conexão com SB
```

---

## Pendente

- **Manifests Kubernetes**: `Deployment` por fila, `ConfigMap`
  não-sensível, `Secret` com SB connection string, SF creds e `sessionId`,
  probes `/healthz`/`/ready`, `terminationGracePeriodSeconds: 60`.
- **Campos `Curso_Nome__c` e `Curso_Descricao__c`**: aguardando checkout passar
  a enviar (hoje ficam `None` na Opp). Quando chegar no payload, o handler
  `pedido_criado` precisa de 1 linha em `_opp_fields()` pra preencher.
