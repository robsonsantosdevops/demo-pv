# Deploy — container do middleware

Este diretório tem o Dockerfile e artefatos relacionados ao empacotamento do
middleware para Kubernetes. Nesta iteração, só Dockerfile + `.dockerignore` —
os manifests `k8s/*.yaml` ficam para a próxima iteração quando os detalhes do
cluster demo (namespace, registry, política de Secret) forem definidos.

---

## Build

A partir da raiz do repositório:

```bash
docker build -t sb-middleware:dev -f deploy/Dockerfile .
```

O build é multi-stage:

- **Stage `builder`**: cria uma venv `/opt/venv` com `requirements.txt`.
  Camada pesada, mas cacheada — muda só quando `requirements.txt` muda.
- **Stage `test`** (alvo opcional): instala dev deps, copia `src/` + `tests/`,
  e roda `pytest` como CMD. Build ou run que falhem param o pipeline.
- **Stage `runtime`** (default): `python:3.12-slim` + venv + `src/` + usuário
  `mw` (UID 10001, não-root). Tamanho final esperado: ~130 MB.

> `docker build` na raiz é importante: o `COPY src /app/src` precisa do
> contexto a partir da raiz. O `-f deploy/Dockerfile` só indica onde está
> o Dockerfile; o contexto continua sendo `.`.

---

## Run local

```bash
# Consumer da fila pedidos → Salesforce (Opportunity)
docker run --rm \
  --env-file .env \
  -e QUEUE_NAME=pedidos \
  -p 8080:8080 \
  sb-middleware:dev

# Consumer da fila contatos → Salesforce (Contact)
docker run --rm \
  --env-file .env \
  -e QUEUE_NAME=contatos \
  -p 8081:8080 \
  sb-middleware:dev

# Consumer da fila oportunidades → SAP B1 (Order)
docker run --rm \
  --env-file .env \
  -e QUEUE_NAME=oportunidades \
  -p 8082:8080 \
  sb-middleware:dev

# Consumer da fila relatorios → SAP (lê Order) + Salesforce (atualiza Relatorio_SAP__c)
docker run --rm \
  --env-file .env \
  -e QUEUE_NAME=relatorios \
  -p 8083:8080 \
  sb-middleware:dev
```

`QUEUE_NAME` é a única variável que **não** está no `.env` — vem via `-e` no
runtime para deixar explícito qual fila este contêiner consome. É assim que os
quatro deployments Kubernetes vão diferir: mesma imagem, `QUEUE_NAME` diferente.

> **Setup inicial da org Salesforce.** Antes do primeiro deploy em uma org
> nova, rodar uma vez (fora do contêiner) `python scripts/sf_create_opportunity_fields.py`
> pra criar os 17 custom fields em `Opportunity` + conceder FLS. Idempotente.

### Checagens rápidas

```bash
# Liveness — 200 se o processo está vivo
curl localhost:8080/healthz

# Readiness — 200 só depois que o consumer conectou no Service Bus
curl localhost:8080/ready
```

### Rodar os testes no container

```bash
docker build -t sb-middleware:test --target test -f deploy/Dockerfile .
docker run --rm sb-middleware:test
```

O build termina com 59 testes pytest (≤1s). Saída não-zero = alguma regressão.
Equivalente via Makefile: `make docker-test`.

---

## Variáveis de ambiente esperadas

Tudo que está em `.env.example` pode entrar via `--env-file .env` ou `-e`.
Resumo mínimo por deployment:

### Para `QUEUE_NAME=pedidos` (Salesforce — Opportunity)
- `AZURE_SERVICE_BUS_CONNECTION_STRING`
- `SF_USERNAME`, `SF_PASSWORD`, `SF_SECURITY_TOKEN`
- `SF_CONSUMER_KEY`, `SF_CONSUMER_SECRET` (opcionais — fallbacks disponíveis)
- `SF_DOMAIN` (`login` ou `test` — sandbox é `test`)
- `SF_ACCOUNT_MASTER_EXTRA` — JSON com campos obrigatórios específicos da org
  (ex.: `{"cnpj__c":"00000000000000"}` na demo Keeggo)

### Para `QUEUE_NAME=contatos` (Salesforce — Contact)
Mesmas variáveis SF de `pedidos`. Não usa SAP.
- `AZURE_SERVICE_BUS_CONNECTION_STRING`
- `SF_USERNAME`, `SF_PASSWORD`, `SF_SECURITY_TOKEN`
- `SF_CONSUMER_KEY`, `SF_CONSUMER_SECRET`
- `SF_DOMAIN`
- `SF_ACCOUNT_MASTER_EXTRA`

### Para `QUEUE_NAME=oportunidades` (SAP B1 — Order)
- `AZURE_SERVICE_BUS_CONNECTION_STRING`
- `sessionId` (case-sensitive) — session token `B1SESSION`. No cluster vem via job externo que atualiza a env var do namespace.
- `SAP_BASE_URL` (ex.: `https://host:50000/b1s/v2`)
- `SAP_COMPANY_DB`
- `SSL_VERIFY=false` para o SAP de dev com cert auto-assinado
- `SAP_DEFAULT_CARDCODE`, `SAP_DEFAULT_ITEM_CODE`, `SAP_DEFAULT_BPL_ID`
- **SF é opcional aqui** (enrichment fail-soft) — se as vars SF estiverem
  presentes, o handler enriquece a Order com Curso/Aluno antes de postar; se
  ausentes/inválidas, segue sem enrichment.

### Para `QUEUE_NAME=relatorios` (SAP — leitura — + Salesforce — escrita)
Precisa de **ambas** as integrações: lê a Order no SAP e atualiza o
`Relatorio_SAP__c` no SF.
- `AZURE_SERVICE_BUS_CONNECTION_STRING`
- Todas as variáveis de SF (mesmas de `pedidos`)
- Todas as variáveis de SAP (mesmas de `oportunidades`)

---

## Health checks

O Dockerfile declara `HEALTHCHECK` batendo em `/healthz` via `curl`. Isso é
útil em `docker ps` (mostra `healthy`/`unhealthy`) e em orquestradores que
respeitam o healthcheck do OCI (Nomad, Docker Swarm). **Kubernetes ignora o
`HEALTHCHECK` do Docker** — use `livenessProbe` / `readinessProbe` nos
manifests, apontando pras mesmas rotas `/healthz` e `/ready`.

---

## Troubleshooting

### "Variável obrigatória ausente: QUEUE_NAME"
Faltou o `-e QUEUE_NAME=...` no `docker run`. O middleware não assume default
pra evitar que um pod mal configurado consuma a fila errada.

### "falha montando handlers — abortando boot" com 401
Credenciais SF rejeitadas. Confira `SF_USERNAME` / `SF_PASSWORD` +
`SF_SECURITY_TOKEN` (a senha concatena com o token no fluxo user/pwd).

### Readiness nunca vira 200
Consumer ainda não conectou no Service Bus. Ver logs — normalmente rede
(firewall) ou connection string errada.

### Handler SAP retorna `sap_session_unavailable`
`sessionId` vazio ou ausente. No cluster, esperar o job externo atualizar a
env var; em dev, obter novo token via `POST /b1s/v2/Login` e colocar no `.env`.

### Build recria tudo a cada mudança em `src/`
Esperado. As deps só são reinstaladas quando `requirements.txt` muda — o
`COPY src` fica na última camada do runtime. Para acelerar builds de dev,
use `docker build --build-arg BUILDKIT_INLINE_CACHE=1` ou um registry cache.
