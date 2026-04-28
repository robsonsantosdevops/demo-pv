# Runbook — Operação das filas, DLQ e integrações

Manual de operação do middleware. Cobre:

- Arquitetura resumida das filas
- Como consultar o estado (ativas + DLQ)
- Como inspecionar mensagens sem consumi-las
- Como funciona a dead-letter queue (DLQ)
- Como reinjetar mensagens da DLQ
- Como drenar filas (limpeza)
- Operações com Salesforce (setup de schema)
- Operações com SAP B1 (consulta de Orders)
- Troubleshooting rápido

Todos os scripts aqui mencionados vivem em `scripts/` e leem o `.env` da raiz
do projeto.

---

## 1. Arquitetura das filas

```
Checkout ───► pedidos        ───► middleware ───► Salesforce
                                                       │
                                                       ▼ (Apex trigger Closed Won)
              oportunidades  ◄─── Salesforce
                      │
                      ▼
              middleware ───► SAP B1
```

Duas filas, DLQ independente:

| Fila            | Producer         | Tipos esperados                         | Consumer destino |
|-----------------|------------------|-----------------------------------------|------------------|
| `contatos`      | Checkout (Node)  | `aluno_cadastrado`                      | Salesforce (Contact) |
| `pedidos`       | Checkout (Node) + Apex (transiente) | `pedido_criado`, `pagamento_aprovado`, `pedido_report`, `relatorio_sap_request` | Salesforce (Opp + OCR); os 2 últimos são forwarded pra `relatorios` |
| `oportunidades` | Apex (SF trigger)| `oportunidade_ganha`                    | SAP B1 Order     |
| `relatorios`    | Forwarder (middleware) | `pedido_report`, `relatorio_sap_request` | SAP B1 → Salesforce (Relatorio_SAP__c + Linhas) |

Qualquer mensagem com `application_properties.tipo` fora dessa lista para a
fila correspondente é enviada para a DLQ com `reason=unknown_type` — isso é
uma salvaguarda: o middleware nunca processa uma mensagem que não sabe rotear.

### Parâmetros das filas

Definidos em `scripts/create_queues.py`:

| Parâmetro                              | Valor       | Motivo |
|----------------------------------------|-------------|--------|
| `lock_duration`                        | 5 min       | Dá folga para handlers lentos (SAP) sem perder o lock. |
| `max_delivery_count`                   | 5           | Depois de 5 retries sem `complete`, mensagem vai pra DLQ. |
| `default_message_time_to_live`         | 14 dias     | Protege contra backlog antigo. |
| `dead_lettering_on_message_expiration` | `True`      | Mensagens que estouram TTL vão pra DLQ (não somem). |

> **Nota:** a fila `pedidos` pode ter sido criada com parâmetros antigos
> (lock=1min, maxDelivery=3, ttl=1h, dlqOnExpire=false). O Azure não permite
> alterar vários desses campos depois da criação; para padronizar, seria
> preciso drenar e recriar. Por ora fica como está.

---

## 2. Garantir as filas no Azure

```bash
python scripts/create_queues.py
```

Idempotente — se já existir, mostra os parâmetros atuais e segue. Útil para
provisionar um namespace novo (dev, staging, produção) de uma vez.

Saída esperada:

```
[skip] ja existe: pedidos
   lock=0:01:00 maxDelivery=3 ttl=1:00:00 dlqOnExpire=False
[ok]   criada: oportunidades
   lock=0:05:00 maxDelivery=5 ttl=14 days, 0:00:00 dlqOnExpire=True
```

---

## 3. Consultar o estado das filas

```bash
python scripts/list_queues.py
```

Saída:

```
- oportunidades | active=1 | dlq=0
- pedidos       | active=0 | dlq=0
```

Campos:

- `active` — mensagens aguardando consumo (ainda não em processamento).
- `dlq` — mensagens na sub-fila `$DeadLetterQueue` da própria fila.

Há também, sem aparecer no list, mensagens "em voo": aquelas que um consumer
pegou em peek-lock e ainda não fez `complete` nem abandonou. Elas **não**
contam em `active` enquanto o lock estiver ativo. Quando o lock expira, voltam
para `active` (e incrementam `delivery_count`).

---

## 4. Inspecionar mensagens sem consumi-las (peek)

`scripts/receive.py` faz **peek**: lê as primeiras N mensagens sem remover da
fila e sem adquirir lock. Útil para debug rápido.

```bash
# Todas as filas do namespace (descobre via admin API)
python scripts/receive.py

# Só uma fila
python scripts/receive.py pedidos
python scripts/receive.py oportunidades

# Aumentar o limite por fila (default 20)
python scripts/receive.py --max 50
python scripts/receive.py oportunidades --max 100
```

Saída por mensagem:

```
=== fila: oportunidades | visíveis: 4
---
  messageId: oportunidade_ganha-1776889562855-061298
  props:     {'tipo': 'oportunidade_ganha', 'traceparent': '00-...-...-01'}
  body:      {"tipo":"oportunidade_ganha","payload":{...},"timestamp":"..."}
```

> Peek **não** reserva a mensagem: o consumer real pode pegar a mesma msg
> logo depois. Peek é seguro para inspeção.

### Inspecionar a DLQ de uma fila

Peek da DLQ exige `sub_queue=ServiceBusSubQueue.DEAD_LETTER`. Duas formas:

```bash
# Usando purge_queue em dry-run (recomendado)
python scripts/purge_queue.py --queue pedidos --dlq --dry-run

# Ou redrive_dlq em dry-run (além de listar, mostra o reason da DLQ)
python scripts/redrive_dlq.py --from pedidos --to oportunidades --dry-run
```

Saída:

```
DLQ tem ao menos 1 mensagem(ns) (peek):
  messageId=oportunidade_ganha-1776889562855-061298 tipo='oportunidade_ganha'
  dlq_reason='unknown_type' delivery_count=0
```

Campos importantes do peek de DLQ:

- `dlq_reason` (`DeadLetterReason` no SDK) — vem de quem mandou a mensagem
  pra DLQ. Valores vistos:
  - `unknown_type` — dispatcher do middleware recusou (tipo fora do mapa).
  - `missing_payload` — body sem `payload` ou com `payload` não-dict.
  - `invalid_json` — body não é JSON válido.
  - `MaxDeliveryCountExceeded` — mensagem foi abandonada ≥`max_delivery_count`
    vezes. Infra do Service Bus empurra pra DLQ.
  - `TTLExpiredException` — mensagem expirou antes de ser consumida.
- `delivery_count` — quantas vezes a mensagem foi entregue a algum consumer.

---

## 5. Como funciona a DLQ

Cada fila tem uma sub-fila `<nome>/$DeadLetterQueue`. Mensagens chegam lá por
dois caminhos:

### 5.1 DLQ "de infra" (automática)
Quando o consumer recebe em peek-lock mas não faz `complete`:

- Se `abandon` for chamado → `delivery_count++` e volta pra `active`.
- Se `delivery_count > max_delivery_count` → Service Bus move sozinho pra DLQ
  com `DeadLetterReason=MaxDeliveryCountExceeded`.
- Se o lock expira sem `complete` nem `abandon` (ex.: pod crashou) → volta
  pra `active` com `delivery_count` incrementado. Após N voltas, vai pra DLQ.
- Se TTL expirar e `dead_lettering_on_message_expiration=True` → DLQ com
  `DeadLetterReason=TTLExpiredException`.

### 5.2 DLQ "de negócio" (explícita)
O middleware chama `receiver.dead_letter_message(msg, reason=..., error_description=...)`
quando detecta que a mensagem nunca deveria ter chegado — retry não vai
resolver. Hoje o `consumer.py` faz isso em três casos:

| Caso | `reason`         | Quando |
|------|------------------|--------|
| Body não-JSON | `invalid_json`    | `json.loads` falha. |
| Sem `payload` | `missing_payload` | `body.payload` ausente ou não-dict. |
| Tipo errado   | `unknown_type`    | `(queue, tipo)` fora do mapa do dispatcher. |

Handlers de SF/SAP (Etapas 3 e 5) poderão adicionar mais — ex.: "Opportunity
não existe no Salesforce e não tem como criar" → DLQ com
`reason=opp_not_found`.

### Por que o middleware prefere DLQ a retry silencioso
- Mensagens com payload quebrado ou tipo errado nunca seriam aceitas, mesmo
  em 50 retries. Melhor falhar rápido e visível.
- Retries silenciosos escondem problemas — DLQ força observabilidade.
- DLQ é reversível: `redrive_dlq.py` reinjeta quando a causa for resolvida.

---

## 6. Reinjeção do DLQ (redrive)

`scripts/redrive_dlq.py` move mensagens da DLQ de uma fila para outra fila
ativa, preservando `body`, `content_type`, `message_id`, `correlation_id` e
`application_properties`. Adiciona `application_properties.redriven_from`
para rastreabilidade.

### Casos de uso

1. **Mensagem foi parar na fila errada.** O Apex estava publicando
   `oportunidade_ganha` em `pedidos` antes da fila `oportunidades` existir.
   Solução: mover da DLQ de `pedidos` para `oportunidades`.

2. **Bug no handler foi corrigido.** Mensagens ficaram na DLQ por
   `MaxDeliveryCountExceeded`. Após deploy da correção, reinjetar na própria
   fila de origem resolve — basta `--from X --to X`.

3. **Recuperar mensagens filtradas por tipo.** Só reinjetar as do tipo
   `oportunidade_ganha` e deixar as demais na DLQ para investigação manual.

### Comandos

```bash
# 1. Ver o que tem na DLQ (não move nada)
python scripts/redrive_dlq.py --from pedidos --to oportunidades --dry-run

# 2. Mover tudo (até 50 mensagens por execução; aumentar com --max)
python scripts/redrive_dlq.py --from pedidos --to oportunidades

# 3. Mover só um tipo específico
python scripts/redrive_dlq.py --from pedidos --to oportunidades \
    --filter-tipo oportunidade_ganha

# 4. Reinjetar na mesma fila após corrigir bug do handler
python scripts/redrive_dlq.py --from oportunidades --to oportunidades --max 500
```

### Fluxo interno do script

1. Abre receiver na DLQ (`sub_queue=DEAD_LETTER`) em peek-lock.
2. Abre sender na fila destino.
3. Para cada mensagem recebida:
   - Se `--filter-tipo` for definido e não casar → `abandon` (volta pra DLQ).
   - Constrói nova `ServiceBusMessage` com os mesmos campos + `redriven_from`.
   - `sender.send_messages(new)` → se falhar, `abandon` e log.
   - Em caso de sucesso, `complete_message` na DLQ (remove definitivamente).
4. Reporta `movidas: X | puladas: Y`.

### Flags

| Flag            | Descrição                                                     | Default |
|-----------------|---------------------------------------------------------------|---------|
| `--from`        | Fila de origem (a DLQ dela será lida).                        | *obrig* |
| `--to`          | Fila de destino para reenvio.                                 | *obrig* |
| `--filter-tipo` | Reenvia só se `application_properties.tipo` == valor.         | —       |
| `--max`         | Máximo de mensagens por execução (lock de 5min).              | 50      |
| `--dry-run`     | Peek only — não move, não trava, não incrementa delivery count. | off     |

---

## 7. Drenar mensagens (`purge_queue.py`)

Remove mensagens da fila principal **ou** da DLQ. Útil para limpar lixo de
testes ou drenar uma DLQ inteira sem reinjetar.

```bash
# Inspecionar antes (não move)
python scripts/purge_queue.py --queue oportunidades --dry-run
python scripts/purge_queue.py --queue pedidos --dlq --dry-run

# Drenar DLQ inteira
python scripts/purge_queue.py --queue pedidos --dlq

# Drenar só um tipo
python scripts/purge_queue.py --queue oportunidades --filter-tipo pedido_criado

# Drenar tudo EXCETO um tipo (mantém o legítimo, remove lixo)
python scripts/purge_queue.py --queue oportunidades --exclude-tipo oportunidade_ganha
```

> `complete_message` na fila principal **remove a mensagem definitivamente**.
> Sempre rodar `--dry-run` antes em dados de produção.

---

## 8. Operações com Salesforce

### Setup do schema (uma vez por org)

```bash
python scripts/sf_create_opportunity_fields.py
```

Cria os 17 campos custom em `Opportunity` via Tooling API e concede **FLS**
(Read + Edit) no PermissionSet shadow do profile do usuário autenticado —
sem isso, a Data API devolve `INVALID_FIELD` mesmo com o campo criado.

Idempotente: se um campo já existe, pula. Flags:

- `--only Campo1 Campo2` — cria apenas esses (útil quando surgir novo campo)
- `--dry-run` — só imprime os payloads Metadata
- `--fls-only` — apenas concede FLS (campos já criados)
- `--skip-fls` — só cria, sem FLS

### Campos custom usados pelo middleware

| API Name | Tipo | Quem preenche |
|---|---|---|
| `Correlation_Id__c` | Text(80) Unique+ExtId | `pedido_criado` — chave idempotente |
| `Pedido_Id__c` | Number(10,0) Unique+ExtId | `pedido_criado` |
| `Aluno_Id__c` | Number(10,0) ExtId | `pedido_criado` |
| `Aluno_Nome__c` | Text(100) | `pedido_criado` |
| `Aluno_Email__c` | Email | `pedido_criado` |
| `Parcelas__c` | Number(3,0) | `pedido_criado` |
| `Pedido_Created_At__c` | DateTime | `pedido_criado` |
| `Status_Checkout__c` | Picklist | `pedido_criado` |
| `Itens_Json__c` | LongTextArea(32K) | `pedido_criado` (array serializado) |
| `Pagamento_Id__c` | Number(10,0) ExtId | `pagamento_aprovado` |
| `Pagamento_Protocolo__c` | Text(60) | `pagamento_aprovado` |
| `Forma_Pagamento__c` | Picklist | `pagamento_aprovado` |
| `Status_Pagamento__c` | Picklist | `pagamento_aprovado` |
| `Status_Pedido__c` | Picklist | `pagamento_aprovado` |
| `Cartao_Final__c` | Text(4) | `pagamento_aprovado` (null em PIX/boleto) |
| `Curso_Nome__c` | Text(200) | **reservado** — aguardando checkout |
| `Curso_Descricao__c` | LongTextArea(32K) | **reservado** — aguardando checkout |

### Idempotência da Opp

- `pedido_criado` faz **upsert nativo** via
  `PATCH /sobjects/Opportunity/Correlation_Id__c/<valor>`. Cria se não existe,
  atualiza se existe. Sem condição de corrida.
- `pagamento_aprovado` busca por `Correlation_Id__c` (com fallback por `Name`
  para Opps legadas). Se não achar, retorna RETRY (assume ordem invertida —
  `pedido_criado` ainda não foi processado).

---

## 9. Operações com SAP B1

### Consultar Orders criadas

```bash
# Por DocEntry (um ou mais)
python scripts/sap_get_order.py 41336
python scripts/sap_get_order.py 41330 41332 41334 41336

# Últimas N
python scripts/sap_get_order.py --recent 10
python scripts/sap_get_order.py --by-cardcode C40000 --recent 5

# JSON cru pra inspeção completa
python scripts/sap_get_order.py 41336 --raw
```

### Idempotência do SAP

O handler `oportunidade_ganha` grava **`NumAtCard = opportunity_id`** em toda
Order criada. Antes de POSTar, filtra `/Orders?$filter=NumAtCard eq '<opp_id>'` —
se já existir, pula e retorna ACK sem novo POST.

> **Por que não `Comments`?** `Comments` é memo field no SAP B1 e o Service
> Layer não aceita `contains` sobre memo. `NumAtCard` é varchar(100) filtrável
> com `eq`.

### Renovação do session token

No cluster, a env var **`sessionId`** (case-sensitive) é atualizada por um job
externo a cada ~30 min. O middleware relê a cada request e faz retry-once em 401.

Em dev local, quando expirar, obter novo token com `POST /b1s/v2/Login` e
colar o valor em `sessionId=` no `.env`.

---

## 10. Troubleshooting rápido

### "Vejo mensagens em `active` mas o consumer não processa"
- Confirmar que o pod está com `QUEUE_NAME` certo (`pedidos` vs `oportunidades`).
- `curl :8080/ready` — se 503, consumer ainda não conectou no Service Bus.
- `kubectl logs` — procurar `"status":"error"` no JSON.

### "DLQ está crescendo"
- `redrive_dlq.py --dry-run` para ver `dlq_reason` e `tipo`.
- `MaxDeliveryCountExceeded` → bug no handler, ver logs de quando subia
  `"status":"retry"` com `reason` da exceção.
- `unknown_type` → producer publicando tipo errado (fila errada ou contrato
  alterado). Corrigir o producer, depois redrive.
- `invalid_json` / `missing_payload` → producer enviando body fora do
  contrato `{tipo, payload, timestamp}`. Ver `docs/message-contract.md`
  (Etapa 8 pendente — exemplos de payload estão no `PLAN.md`).

### "Mensagem ficou travada em `in-flight`"
Aconteceu quando o pod crashou sem soltar o lock. O lock expira em
`lock_duration` (5min) e a mensagem volta pra `active` com `delivery_count++`.
Nada a fazer — é automático.

### "Handler SF diz `INVALID_FIELD: No such column 'Correlation_Id__c'`"
Schema não foi setado na org. Rodar:
```bash
python scripts/sf_create_opportunity_fields.py
```

### "Handler SF diz `REQUIRED_FIELD_MISSING` em algum campo custom na Account"
A org tem campos obrigatórios específicos (ex.: `cnpj__c` na demo Keeggo).
Preencher via env var `SF_ACCOUNT_MASTER_EXTRA` (JSON), ex.:
```
SF_ACCOUNT_MASTER_EXTRA={"cnpj__c":"00000000000000"}
```

### "Handler SAP retorna `sap_session_unavailable`"
`sessionId` vazio ou ausente no env. Em dev, obter novo token via
`POST /b1s/v2/Login` e atualizar `.env`. No cluster, esperar o job externo.

### "Handler SAP retorna `sap_http_401`"
Sessão expirou durante o request. O client já tenta 1x com refresh automático.
Se ainda falhar (env não atualizado), a mensagem fica em RETRY até a env var
ser atualizada. Não perde dado.

### "Quero zerar tudo"
Para um ambiente **limpo** de dev:

```bash
python - <<'PY'
import os
from dotenv import load_dotenv
from azure.servicebus.management import ServiceBusAdministrationClient
load_dotenv()
with ServiceBusAdministrationClient.from_connection_string(
    os.environ["AZURE_SERVICE_BUS_CONNECTION_STRING"]
) as a:
    for q in ("pedidos", "oportunidades"):
        try:
            a.delete_queue(q)
            print("deletada:", q)
        except Exception as e:
            print(q, "->", e)
PY

python scripts/create_queues.py
```

> Não faça isso em ambientes com dados importantes. Apaga tudo, inclusive DLQ.
