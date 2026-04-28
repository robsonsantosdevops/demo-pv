# Middleware Azure Service Bus — demo Keeggo

Consumer em Python que integra **Azure Service Bus** com **Salesforce** e **SAP Business One** (Service Layer), fechando o fluxo de checkout, oportunidades e relatórios.

## Índice

- [Visão geral](#visão-geral)
- [Arquitetura em uma imagem](#arquitetura-em-uma-imagem)
- [Filas e tipos de mensagem](#filas-e-tipos-de-mensagem)
- [Requisitos](#requisitos)
- [Configuração](#configuração)
- [Execução local](#execução-local)
- [Docker](#docker)
- [Scripts operacionais](#scripts-operacionais)
- [Testes](#testes)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Documentação relacionada](#documentação-relacionada)

---

## Visão geral

Este pacote (`src/middleware`) é um **worker** que:

1. Conecta ao Azure Service Bus e consome **uma fila por processo** (`QUEUE_NAME`).
2. Encaminha cada mensagem ao **dispatcher**, que escolhe o handler pelo par `(fila, tipo_da_mensagem)`.
3. Executa integrações com **Salesforce** (pedidos, contatos, relatórios) e/ou **SAP B1** (oportunidades ganhas, leitura de pedidos para relatório), conforme a fila.

Cada deployment (local ou Kubernetes) sobe **um contêiner por fila** — mesma imagem, variável `QUEUE_NAME` diferente.

---

## Arquitetura em uma imagem

```
Checkout / API ──► fila pedidos      ──► middleware ──► Salesforce
                         │                              │
                         │ (pedido_report / relay)      │
                         ▼                              ▼
                    fila relatorios ◄── reencaminhamento + handler SAP+SF

Salesforce (Apex) ──► fila oportunidades ──► middleware ──► SAP B1

Checkout ──► fila contatos ──► middleware ──► Salesforce (Contact)
```

Relacionamento com a API Node (`api-pv`): a API publica eventos (`pedido_criado`, `pagamento_aprovado`, etc.) na mesma namespace do Service Bus; **este** repositório contém o consumidor Python que processa essas mensagens.

---

## Filas e tipos de mensagem

| `QUEUE_NAME`   | Tipos tratados (exemplos) | Integração principal |
|----------------|---------------------------|----------------------|
| `pedidos`      | `pedido_criado`, `pagamento_aprovado` | Salesforce |
| `pedidos`      | `pedido_report`, `relatorio_sap_request` | Reencaminha para `relatorios` |
| `contatos`     | `aluno_cadastrado` | Salesforce (Contact) |
| `oportunidades`| `oportunidade_ganha` | SAP B1 (Sales Order); Salesforce opcional (enrichment) |
| `relatorios`   | `pedido_report`, `relatorio_sap_request` | SAP + Salesforce |

Valores aceitos de `QUEUE_NAME` estão definidos em `src/middleware/config.py` (`VALID_QUEUES`).

---

## Requisitos

- **Python** 3.11 ou superior (`requires-python` no `pyproject.toml`).
- **Credenciais e endpoints** no `.env` (modelo em `.env.example`):
  - `AZURE_SERVICE_BUS_CONNECTION_STRING`
  - Salesforce: `SF_USERNAME`, `SF_PASSWORD`, `SF_SECURITY_TOKEN`, etc.
  - SAP: `sessionId` (token `B1SESSION`, case-sensitive), `SAP_BASE_URL`, `SAP_COMPANY_DB`, defaults de item/card quando aplicável.

Provisionamento inicial em ambiente novo (idempotente quando possível):

```bash
python scripts/create_queues.py
python scripts/sf_create_opportunity_fields.py   # org Salesforce nova: campos custom + FLS
```

---

## Configuração

1. Copie `.env.example` para `.env` e preencha os segredos (não commitar `.env`).
2. Defina `QUEUE_NAME` no ambiente de execução (não há default no código — evita consumir a fila errada).
3. Opcionais úteis: `LOG_LEVEL`, `HEALTH_PORT` (default `8080`), `SB_MAX_WAIT_TIME`, `SB_MAX_MESSAGE_COUNT`.

Variáveis detalhadas por tipo de deployment (pedidos vs oportunidades) estão em `deploy/README.md`.

---

## Execução local

```bash
pip install -r requirements.txt

# Um terminal por fila — cada processo consome apenas a fila indicada:
set QUEUE_NAME=pedidos && python -m middleware
# Linux/macOS: QUEUE_NAME=pedidos python -m middleware
```

Filas possíveis: `contatos`, `pedidos`, `oportunidades`, `relatorios`.

**Health checks** (após subir o processo):

- `GET http://localhost:8080/healthz` — processo vivo (liveness).
- `GET http://localhost:8080/ready` — consumer conectado ao Service Bus (readiness).

### Mensagens de teste

```bash
python scripts/send.py
python scripts/send.py --numero-pedido PED-DEMO-1 --correlation-id demo-1
python scripts/send.py --tipo pagamento_aprovado --numero-pedido PED-DEMO-1 --correlation-id demo-1
python scripts/send.py --tipo oportunidade_ganha --opp-id OPP-1 --amount 1500
```

Inspecionar filas sem consumir de forma agressiva:

```bash
python scripts/list_queues.py
python scripts/receive.py
python scripts/receive.py pedidos
```

---

## Docker

Na raiz deste diretório (`azure_service_bus/`):

```bash
docker build -t sb-middleware:dev -f deploy/Dockerfile .
docker run --rm --env-file .env -e QUEUE_NAME=pedidos -p 8080:8080 sb-middleware:dev
```

Build multi-stage, usuário não-root e testes opcionais — ver **`deploy/README.md`** (variáveis, probes, troubleshooting).

### Kubernetes

Manifestos (Deployments por fila, ConfigMap, Services, Kustomize) estão em **`k8s/`** — ver **`k8s/README.md`**.

---

## Scripts operacionais

| Script | Função |
|--------|--------|
| `create_queues.py` | Cria filas no namespace do Service Bus |
| `list_queues.py` | Contagens active/DLQ |
| `send.py` | Publica mensagens de teste |
| `receive.py` | Peek/recebimento para diagnóstico |
| `purge_queue.py` | Esvaziar fila (cuidado em produção) |
| `redrive_dlq.py` | Reprocessar DLQ |
| `sap_get_order.py` / `sap_create_order_udfs.py` | Utilitários SAP |
| `sf_create_contact_fields.py` / `sf_create_opportunity_fields.py` | Setup Salesforce |

---

## Testes

```bash
pip install -r requirements-dev.txt
pytest -v
```

Ou via imagem de teste do Dockerfile (`deploy/README.md`, alvo `test` / `make docker-test` se existir Makefile).

---

## Estrutura do repositório

```
src/middleware/           # Consumer, dispatcher, handlers, integrações SF/SAP
scripts/                  # Operação de filas e testes manuais
tests/                    # Testes pytest (config, dispatcher, handlers, integrações)
deploy/                   # Dockerfile, .dockerignore, README de deploy
k8s/                      # Manifests Kubernetes (Deployments, ConfigMap, Services)
docs/                     # Arquitetura, contrato de mensagens, runbook, fluxos
logs/                     # Logs em desenvolvimento (tipicamente ignorados pelo Git)
.env.example              # Template de variáveis de ambiente
pyproject.toml            # Metadados do pacote e ferramentas (ruff, pytest)
PLAN.md                   # Plano / status do projeto (se mantido)
```

---

## Documentação relacionada

| Assunto | Arquivo |
|---------|---------|
| Visão da demo e topologia | `docs/demo-overview.md` |
| Fluxo ponta a ponta / sequências | `docs/message-flow.md` |
| Arquitetura e decisões | `docs/architecture.md` |
| Contrato das mensagens (schema) | `docs/message-contract.md` |
| Operação: DLQ, reprocessamento, SF/SAP | `docs/runbook.md` |
| Deploy em contêiner / env por fila | `deploy/README.md` |
| Deploy no cluster (K8s / Kustomize) | `k8s/README.md` |
| Kubernetes no Azure (guia) | `docs/implementations/k8s-deploy-azure.md` |
| Origem dos clients SF/SAP | `src/middleware/integrations/*/ORIGIN.md` |

---

## Status

Core do middleware, integrações Salesforce e SAP, imagem Docker e suíte de testes documentados em `PLAN.md` e nos docs acima. Ajuste manifests Kubernetes e secrets conforme o cluster alvo.
