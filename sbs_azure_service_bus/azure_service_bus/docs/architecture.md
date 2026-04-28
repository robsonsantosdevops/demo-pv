# Arquitetura — Middleware Azure Service Bus

## Problema que o middleware resolve

A demo Keeggo precisa propagar pedidos do **checkout** (site Node) até o
**SAP B1** (ERP), passando pelo **Salesforce** (CRM) como registro comercial
intermediário. Nenhum dos 3 sistemas fala direto com os outros em tempo real:

- Checkout é um app web — não pode bloquear aguardando sincronismo com SF/SAP
  (latência imprevisível, disponibilidade variável).
- Salesforce exige auth, rate limits e custom fields — integração via REST
  requer um worker dedicado.
- SAP B1 Service Layer tem session-based auth com token que expira e gateway
  instável em dev — precisa de retry e renovação.

**Solução:** um barramento assíncrono (Azure Service Bus) com mensageria
idempotente + um consumer Python (este projeto) que faz as integrações.

---

## Fluxo end-to-end

```
                       ┌──────────────────────┐
                       │   Checkout (site)    │
                       │    producer Node     │
                       └─────────┬────────────┘
                                 │ pedido_criado
                                 │ pagamento_aprovado
                                 ▼
                       ┌──────────────────────┐
                       │   fila: pedidos      │ ◄──┐ DLQ independente
                       │   (Service Bus)      │    │
                       └─────────┬────────────┘    │
                                 │                 │
                         peek-lock, consume         │
                                 │                 │
                       ┌─────────▼────────────┐    │
                       │ middleware (pod #1)  ├────┘ (retries / dead-letter)
                       │ QUEUE_NAME=pedidos   │
                       └─────────┬────────────┘
                                 │ POST /sobjects/Account/...
                                 │ PATCH /sobjects/Opportunity/
                                 │   Correlation_Id__c/<valor>
                                 ▼
                       ┌──────────────────────┐
                       │     Salesforce       │
                       │   (Account, Contact, │
                       │    Opportunity)      │
                       └─────────┬────────────┘
                                 │ trigger Apex: Closed Won
                                 │ publica oportunidade_ganha
                                 ▼
                       ┌──────────────────────┐
                       │ fila: oportunidades  │ ◄──┐
                       │   (Service Bus)      │    │
                       └─────────┬────────────┘    │
                                 │                 │
                         peek-lock, consume         │
                                 │                 │
                       ┌─────────▼────────────┐    │
                       │ middleware (pod #2)  ├────┘
                       │ QUEUE_NAME=          │
                       │   oportunidades      │
                       └─────────┬────────────┘
                                 │ GET /Orders?$filter=NumAtCard eq ...
                                 │ POST /Orders
                                 ▼
                       ┌──────────────────────┐
                       │    SAP B1 Service    │
                       │    Layer (Orders)    │
                       └──────────────────────┘
```

Mesma imagem Docker roda como **2 pods distintos**, só diferenciando pelo env
var `QUEUE_NAME`. Cada pod é isolado: cair um não afeta o outro, escalam
independente, DLQs não se misturam.

---

## Decisões de design

### Uma fila por leg (não fila única com dispatch)

**Decisão:** filas `pedidos` e `oportunidades` separadas, cada uma com sua DLQ.

**Motivo:** cada leg tem integração, SLA e tipo de falha diferentes
(Salesforce lento vs SAP instável). Fila única misturaria DLQs — se SAP
estivesse quebrado, mensagens pra SF iam junto. Fila única também impede
escalar um consumer sem escalar o outro.

### Peek-lock com at-least-once (não receive-and-delete)

**Decisão:** `get_queue_receiver(receive_mode=PEEK_LOCK)`.

**Motivo:** se o pod crashar depois de fazer a chamada SF/SAP mas antes do
`complete`, o lock expira e a mensagem volta pra `active` — nada é perdido.
Trade-off: handlers precisam ser idempotentes (o mesmo `complete` pode ser
tentado duas vezes em reentrega). Isso é resolvido por:

- SF: upsert nativo via `Correlation_Id__c` (External ID + Unique).
- SAP: filter `NumAtCard eq <opp_id>` antes de `POST /Orders`.

### Retry/DLQ explícitos por classe de erro

O handler devolve um `HandleResult` discreto:

| `HandleResult` | Ação do consumer | Quando usar |
|---|---|---|
| `.ok()` | `complete_message` — sai da fila | Sucesso, ou no-op idempotente |
| `.retry(reason)` | `abandon_message` — volta pra `active`, `delivery_count++` | Erro transiente: 5xx, timeout, token expirado, Opp não encontrada (ordem invertida) |
| `.dlq(reason)` | `dead_letter_message` — move pra DLQ com reason | Erro permanente: payload inválido, 4xx de validação, tipo desconhecido |

Após `max_delivery_count=5` retries automáticos, Service Bus move pra DLQ com
`MaxDeliveryCountExceeded`. Operador inspeciona via `redrive_dlq.py --dry-run`
e decide reinjeção.

### Idempotência por chave externa (não "busca antes de criar")

**Antigo** (descartado):
```
SOQL SELECT Id FROM Opportunity WHERE Name = 'PED-X'
IF found: PATCH   ELSE: POST
```
Problema: duas mensagens concorrentes podem ler vazio e criar duas Opps.

**Atual**:
```
PATCH /sobjects/Opportunity/Correlation_Id__c/<valor>
```
SF resolve atomicidade via índice Unique do External ID. Um único round-trip.

No SAP, `NumAtCard` é varchar(100) filtrável com `eq` — usado como chave por
ser o único campo prático para isso (tentamos `Comments` antes; memo field,
`contains` não funciona).

### Session SAP não é cacheada no client

**Decisão:** `SapSession` relê a env var `sessionId` a cada request.

**Motivo:** no cluster Kubernetes demo, um job externo (fora do escopo deste
projeto) atualiza a env var `sessionId` do namespace a cada ~30min com um
`B1SESSION` fresco. Se o client cacheasse o token na inicialização, usaria
um valor antigo. `refresh()` força re-leitura após 401.

Em dev, o `.env` fornece o token manualmente.

### Config injetada por construtor (vendoring)

Ambos clients (`SalesforceClient`, `SapClient`) vieram de projetos irmãos
(`salesforce-admin`, `sap-automation-lab`). Os originais liam `.env` no
import (efeito colateral). Aqui cada client recebe um `Config` dataclass no
construtor, facilitando:
- Testes unitários com mocks
- Rodar 2 clients do mesmo tipo com configs diferentes (se um dia precisar)
- Evitar ressuscitar vars obsoletas por ordem de import

Ver `src/middleware/integrations/{salesforce,sap}/ORIGIN.md` para diferenças
exatas.

### Graceful shutdown por `threading.Event`

`__main__` instala handlers de SIGINT/SIGTERM que setam `shutdown.set()`. O
loop do consumer verifica `shutdown.is_set()` a cada iteração e abandona
mensagens em voo antes de sair. `max_wait_time=5s` mantém o loop responsivo.

---

## Componentes internos

```
src/middleware/
├── __main__.py              # orquestra: config → logger → health → handlers → consumer
├── config.py                # Config dataclass, load_config (valida env)
├── logging_setup.py         # JSON formatter, rotating file em logs/app.log
├── consumer.py              # peek-lock loop + graceful shutdown + DLQ calls
├── dispatcher.py            # Dispatcher(handlers_dict), resolve((queue, tipo))
├── health.py                # HealthState + ThreadingHTTPServer em /healthz /ready
├── handlers/
│   ├── base.py              # Handler protocol, HandleResult, HandlerContext
│   ├── pedido_criado.py     # upsert Opp via Correlation_Id__c
│   ├── pagamento_aprovado.py# busca + update Opp para Closed Won
│   └── oportunidade_ganha.py# idempotência NumAtCard + create Order SAP
└── integrations/
    ├── salesforce/
    │   ├── client.py        # SalesforceClient (REST + OAuth2/SOAP)
    │   ├── service.py       # alto nível: ensure_account, upsert_contact, upsert_opp
    │   └── config.py        # SalesforceConfig (do env)
    └── sap/
        ├── client.py        # SapClient (REST + retry-on-401)
        ├── session.py       # SapSession (relê sessionId do env)
        └── config.py        # SapConfig (do env)
```

**Princípio:** `consumer.py` e `dispatcher.py` não conhecem nem SF nem SAP.
Handlers são injetados no `__main__` conforme `QUEUE_NAME`. Adicionar uma
terceira fila (ex.: notificações) seria questão de criar um handler novo e
acrescentar no `_build_handlers`.

---

## Observabilidade

### Logs estruturados (JSON)

Todo log sai como 1 linha JSON no stdout (e opcionalmente em `logs/app.log`).
Campos sempre presentes: `ts`, `level`, `logger`, `msg`. Campos opcionais
(preenchidos quando relevante): `correlation_id`, `message_id`, `tipo`,
`queue`, `delivery_count`, `handler`, `duration_ms`, `status`, `reason`.

Exemplo:
```json
{"ts":"2026-04-23T01:23:09Z","level":"INFO","logger":"middleware.handler.pedido_criado",
 "msg":"opportunity criada","correlation_id":"refac-corr-001","handler":"pedido_criado",
 "status":"ok","reason":"006g5000003ODgjAAG numero_pedido=PED-REFAC-001"}
```

Isso encaixa direto em stacks tipo Loki/ELK com parser JSON — sem regex.

### Distributed tracing (parcial)

Todas as mensagens trazem `application_properties.traceparent` (W3C Trace
Context) propagado pelo checkout. O middleware lê e coloca em
`HandlerContext.traceparent`, disponível pros handlers. Hoje não é
instrumentado em spans OpenTelemetry (TBD); mas o trace ID já segue no log
se precisar correlacionar com o site.

### Healthchecks HTTP

- `GET /healthz` — 200 se o processo está vivo (liveness).
- `GET /ready` — 200 só se o consumer conectou no Service Bus (readiness).

Threading daemon, porta `HEALTH_PORT` (default 8080).

---

## Deploy

### Local
```bash
QUEUE_NAME=pedidos       python -m middleware
QUEUE_NAME=oportunidades python -m middleware   # em outro terminal
```

### Docker (validado no WSL)
```bash
docker build -t sb-middleware:dev -f deploy/Dockerfile .
docker run --rm --env-file .env -e QUEUE_NAME=pedidos -p 8080:8080 sb-middleware:dev
```

### Kubernetes (planejado, não implementado)

Previsto para próxima iteração:

- `Deployment` por fila (réplicas=1 inicialmente; escalar por backlog se
  necessário via KEDA com `ServiceBusQueue` scaler).
- `ConfigMap` com non-secrets (`SAP_BASE_URL`, `SF_DOMAIN`, `LOG_LEVEL`).
- `Secret` com `AZURE_SERVICE_BUS_CONNECTION_STRING`, credenciais SF e
  `sessionId`.
- `livenessProbe` em `/healthz` (period=30s).
- `readinessProbe` em `/ready` (period=10s, failureThreshold=3).
- `terminationGracePeriodSeconds: 60` para não cortar no meio de um
  `complete_message`.
- `resources.requests.memory=128Mi`, `.limits.memory=256Mi`.

---

## Limites conhecidos

| Limite | Descrição | Mitigação |
|---|---|---|
| Sem tracing distribuído ativo | `traceparent` só é logado, não propagado em spans OTel | Adicionar `opentelemetry-sdk` + exporter Azure Monitor quando necessário |
| Sem rate limiting explícito | Se SF devolver 429, o handler só retenta | Futuro: backoff exponencial no `RETRY` |
| Sem métricas Prometheus | Só logs JSON | Adicionar `/metrics` com contagem de ACK/RETRY/DLQ por fila |
| `Itens_Json__c` truncado em 32K | LongTextArea do SF é 32K max | Produtos super longos ficam truncados — aceitável para a demo |
| `SF_ACCOUNT_MASTER_EXTRA` é hardcoded por deploy | Campo obrigatório custom da org injetado por env | Ok para demo, futuramente virar sync automático de schema |
| Handlers `Curso_Nome__c`, `Curso_Descricao__c` vazios | Checkout ainda não envia | Preenchimento é trivial quando producer passar a enviar |
