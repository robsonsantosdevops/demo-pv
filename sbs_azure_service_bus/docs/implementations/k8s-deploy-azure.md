# Deploy dos 4 consumers em Kubernetes (AKS)

> **Status:** procedimento — manifests baseados na seção "Kubernetes (planejado)"
> de `docs/architecture.md` e nas vars de `.env.example` / `deploy/README.md`.
> Validar primeiro num namespace de teste (`sb-middleware-stg`) antes de promover.

## Contexto

Hoje os 4 consumers rodam como containers Docker no WSL (`sb-consumer-*`).
Para o deploy demo precisamos rodá-los num cluster **AKS (Azure Kubernetes
Service)** com: imagem hospedada em **ACR (Azure Container Registry)**, secrets
isolados, autoescalonamento por backlog (KEDA) e atualização periódica do
`sessionId` SAP via CronJob.

A imagem é única (`sb-middleware`), publicada uma vez, e sobe como **4
Deployments distintos** parametrizados pela env var `QUEUE_NAME`. Cada
Deployment tem seu próprio `livenessProbe` / `readinessProbe`, recursos e
backlog independente.

---

## Mapeamento queue → integrações → secrets

| Deployment | QUEUE_NAME | Handlers | Integrações | Secrets necessários |
|---|---|---|---|---|
| `sb-consumer-pedidos`       | `pedidos`       | pedido_criado, pagamento_aprovado, forwarder | SF                | `sb-secret`, `sf-secret` |
| `sb-consumer-contatos`      | `contatos`      | aluno_cadastrado                              | SF                | `sb-secret`, `sf-secret` |
| `sb-consumer-oportunidades` | `oportunidades` | oportunidade_ganha                            | SAP (+SF opcional) | `sb-secret`, `sap-secret`, `sf-secret` |
| `sb-consumer-relatorios`    | `relatorios`    | pedido_report                                 | SAP + SF           | `sb-secret`, `sap-secret`, `sf-secret` |

> `oportunidades` carrega `sf-secret` por causa do *enrichment fail-soft* em
> `__main__.py:94` — se SF estiver indisponível, o handler segue sem enriquecer.
> Em produção, manter o secret pra ter o caminho feliz funcionando.

---

## Pré-requisitos

| Recurso | Como criar | Observação |
|---|---|---|
| Subscription Azure | (já existe) | `az login` + `az account set` |
| Resource Group     | `az group create -n rg-sb-middleware -l brazilsouth` | região demo |
| ACR                | `az acr create -n keeggosbacr -g rg-sb-middleware --sku Basic` | nome global, sem hifens |
| AKS                | `az aks create -g rg-sb-middleware -n aks-sb-middleware --node-count 2 --enable-managed-identity --attach-acr keeggosbacr` | `--attach-acr` evita imagePullSecrets |
| `kubectl` ctx      | `az aks get-credentials -g rg-sb-middleware -n aks-sb-middleware` | |
| Service Bus        | (já existe — `demo-poli.servicebus.windows.net`) | usar a mesma connection string do `.env` |

Ferramentas locais: `az` ≥2.60, `kubectl` ≥1.29, `docker` (para build), opcionalmente `helm` ≥3.14 (não usado aqui — manifests YAML diretos).

---

## Etapa 1 — Build e push da imagem para ACR

A partir da raiz do repo:

```bash
# Login no ACR (cria token efêmero docker)
az acr login -n keeggosbacr

# Tag = hash do commit + 'latest'
TAG=$(git rev-parse --short HEAD)

docker build -t keeggosbacr.azurecr.io/sb-middleware:$TAG \
             -t keeggosbacr.azurecr.io/sb-middleware:latest \
             -f deploy/Dockerfile .

docker push keeggosbacr.azurecr.io/sb-middleware:$TAG
docker push keeggosbacr.azurecr.io/sb-middleware:latest
```

Confirmar no ACR:
```bash
az acr repository show-tags -n keeggosbacr --repository sb-middleware -o table
```

---

## Etapa 2 — Namespace e Secrets

### 2.1 Namespace

```yaml
# k8s/00-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sb-middleware
  labels:
    app.kubernetes.io/part-of: sb-middleware
```

### 2.2 Secret — Service Bus (`sb-secret`)

```bash
kubectl -n sb-middleware create secret generic sb-secret \
  --from-literal=AZURE_SERVICE_BUS_CONNECTION_STRING='Endpoint=sb://demo-poli.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=<KEY>'
```

### 2.3 Secret — Salesforce (`sf-secret`)

```bash
kubectl -n sb-middleware create secret generic sf-secret \
  --from-literal=SF_USERNAME='<...>' \
  --from-literal=SF_PASSWORD='<...>' \
  --from-literal=SF_SECURITY_TOKEN='<...>' \
  --from-literal=SF_CONSUMER_KEY='<...>' \
  --from-literal=SF_CONSUMER_SECRET='<...>' \
  --from-literal=SF_ACCOUNT_MASTER_EXTRA='{"cnpj__c":"00000000000000"}'
```

### 2.4 Secret — SAP (`sap-secret`)

`sessionId` será reescrito por CronJob (Etapa 4). Aqui só inicializamos com um token válido:

```bash
kubectl -n sb-middleware create secret generic sap-secret \
  --from-literal=sessionId='<token-B1SESSION-inicial>' \
  --from-literal=SAP_COMPANY_DB='<db>'
```

> **Por que só `sessionId` e `SAP_COMPANY_DB` em secret?** `SAP_BASE_URL`,
> `SSL_VERIFY` e os `SAP_DEFAULT_*` não são sensíveis — vão pro ConfigMap.

### 2.5 ConfigMap — não-secrets (`sb-config`)

```yaml
# k8s/10-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sb-config
  namespace: sb-middleware
data:
  LOG_LEVEL: "INFO"
  HEALTH_PORT: "8080"
  SB_MAX_WAIT_TIME: "5"
  SB_MAX_MESSAGE_COUNT: "10"
  # Salesforce
  SF_LOGIN_URL: "https://login.salesforce.com"
  # SAP
  SAP_BASE_URL: "https://desenvolvimento.ananim.com.br:50000/b1s/v2"
  SSL_VERIFY: "false"
  SAP_DEFAULT_CARDCODE: "C40000"
  SAP_DEFAULT_ITEM_CODE: "S10000"
  SAP_DEFAULT_BPL_ID: "1"
```

```bash
kubectl apply -f k8s/00-namespace.yaml -f k8s/10-configmap.yaml
```

---

## Etapa 3 — Deployments (4×)

Os 4 Deployments compartilham uma estrutura comum. O template abaixo
(`sb-consumer-pedidos`) cobre o caso SF; os demais variam apenas em
`QUEUE_NAME`, no nome do Deployment, e em quais Secrets injetam.

### 3.1 Template para `pedidos` e `contatos` (SF)

```yaml
# k8s/20-deploy-pedidos.yaml  (idem 21-deploy-contatos.yaml trocando QUEUE_NAME e nome)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sb-consumer-pedidos
  namespace: sb-middleware
spec:
  replicas: 1
  selector:
    matchLabels: { app: sb-consumer-pedidos }
  template:
    metadata:
      labels: { app: sb-consumer-pedidos, queue: pedidos }
    spec:
      terminationGracePeriodSeconds: 60   # graceful shutdown via SIGTERM
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
      containers:
        - name: middleware
          image: keeggosbacr.azurecr.io/sb-middleware:latest
          imagePullPolicy: IfNotPresent
          env:
            - name: QUEUE_NAME
              value: "pedidos"
          envFrom:
            - configMapRef: { name: sb-config }
            - secretRef:    { name: sb-secret }
            - secretRef:    { name: sf-secret }
          ports:
            - containerPort: 8080
              name: health
          livenessProbe:
            httpGet: { path: /healthz, port: health }
            periodSeconds: 30
            failureThreshold: 3
          readinessProbe:
            httpGet: { path: /ready, port: health }
            periodSeconds: 10
            failureThreshold: 3
          resources:
            requests: { cpu: "50m",  memory: "128Mi" }
            limits:   { cpu: "500m", memory: "256Mi" }
```

Para `sb-consumer-contatos`: copiar o YAML, trocar `pedidos` → `contatos` em
`metadata.name`, `labels.app`, `labels.queue` e `env.QUEUE_NAME`.

### 3.2 Template para `oportunidades` e `relatorios` (SAP + SF)

Diferenças em relação ao 3.1:
- `envFrom` adiciona `sap-secret`.
- `QUEUE_NAME` = `oportunidades` (ou `relatorios`).

```yaml
# k8s/22-deploy-oportunidades.yaml
spec:
  template:
    spec:
      containers:
        - name: middleware
          image: keeggosbacr.azurecr.io/sb-middleware:latest
          env:
            - name: QUEUE_NAME
              value: "oportunidades"
          envFrom:
            - configMapRef: { name: sb-config }
            - secretRef:    { name: sb-secret }
            - secretRef:    { name: sf-secret }
            - secretRef:    { name: sap-secret }
          # (probes, resources, securityContext idênticos ao 3.1)
```

`sb-consumer-relatorios` é cópia trocando `oportunidades` → `relatorios`.

### 3.3 Aplicar

```bash
kubectl apply -f k8s/20-deploy-pedidos.yaml \
              -f k8s/21-deploy-contatos.yaml \
              -f k8s/22-deploy-oportunidades.yaml \
              -f k8s/23-deploy-relatorios.yaml
```

> **Não há Service.** Os 4 pods não recebem tráfego externo — só consomem do
> Service Bus e fazem chamadas HTTP de saída. As probes batem em `localhost`
> dentro do próprio pod.

---

## Etapa 4 — Atualização periódica do `sessionId` SAP

O `SapSession` relê `sessionId` a cada request (`architecture.md:138-146`),
mas a env var só atualiza quando o pod reinicia. A estratégia é:

1. **CronJob** chama `POST /b1s/v2/Login` no SAP, recebe novo `B1SESSION`.
2. Patch no Secret `sap-secret` com o novo valor.
3. **Rollout restart** dos pods que dependem de SAP (`oportunidades`, `relatorios`).

### 4.1 ServiceAccount + RBAC

```yaml
# k8s/30-sap-refresh-rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata: { name: sap-refresher, namespace: sb-middleware }
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: { name: sap-refresher, namespace: sb-middleware }
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["sap-secret"]
    verbs: ["get", "patch"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    resourceNames: ["sb-consumer-oportunidades", "sb-consumer-relatorios"]
    verbs: ["get", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: sap-refresher, namespace: sb-middleware }
subjects: [{ kind: ServiceAccount, name: sap-refresher, namespace: sb-middleware }]
roleRef: { kind: Role, name: sap-refresher, apiGroup: rbac.authorization.k8s.io }
```

### 4.2 Secret com credenciais SAP de Login

```bash
kubectl -n sb-middleware create secret generic sap-login \
  --from-literal=SAP_USER='<usuario>' \
  --from-literal=SAP_PASSWORD='<senha>' \
  --from-literal=SAP_COMPANY_DB='<db>'
```

### 4.3 CronJob

Roda a cada 25 min (B1SESSION expira em 30 min por default — margem de segurança).

```yaml
# k8s/31-sap-refresh-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata: { name: sap-session-refresh, namespace: sb-middleware }
spec:
  schedule: "*/25 * * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 1
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          serviceAccountName: sap-refresher
          restartPolicy: OnFailure
          containers:
            - name: refresh
              image: bitnami/kubectl:1.29
              envFrom:
                - configMapRef: { name: sb-config }   # SAP_BASE_URL, SSL_VERIFY
                - secretRef:    { name: sap-login }
              command: ["/bin/sh","-c"]
              args:
                - |
                  set -eu
                  CURL_FLAGS=""
                  [ "$SSL_VERIFY" = "false" ] && CURL_FLAGS="-k"
                  TOKEN=$(curl -fsS $CURL_FLAGS -X POST "$SAP_BASE_URL/Login" \
                    -H 'Content-Type: application/json' \
                    -d "{\"UserName\":\"$SAP_USER\",\"Password\":\"$SAP_PASSWORD\",\"CompanyDB\":\"$SAP_COMPANY_DB\"}" \
                    | sed -n 's/.*"SessionId":"\([^"]*\)".*/\1/p')
                  [ -n "$TOKEN" ] || { echo "login falhou"; exit 1; }

                  # base64 do novo token
                  B64=$(printf %s "$TOKEN" | base64 -w0)

                  # patch no secret + rollout
                  kubectl -n sb-middleware patch secret sap-secret \
                    --type='json' -p="[{\"op\":\"replace\",\"path\":\"/data/sessionId\",\"value\":\"$B64\"}]"
                  kubectl -n sb-middleware rollout restart deployment sb-consumer-oportunidades sb-consumer-relatorios
```

> **Trade-off:** `rollout restart` faz os pods SAP reciclarem a cada 25 min.
> Como `terminationGracePeriodSeconds=60` + peek-lock garantem zero perda,
> isso é aceitável na demo. Em produção, considerar
> [Reloader](https://github.com/stakater/Reloader) (anotação no Deployment
> dispara restart automático quando o Secret muda) para evitar lógica de
> rollout no CronJob.

---

## Etapa 5 — Autoscaling com KEDA (opcional, recomendado)

KEDA escala por backlog do Service Bus — pods param em 0 quando não há
mensagem.

### 5.1 Instalar KEDA no AKS

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda --namespace keda --create-namespace
```

### 5.2 ScaledObject por fila

Exemplo para `pedidos`:

```yaml
# k8s/40-keda-pedidos.yaml
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata: { name: sb-auth, namespace: sb-middleware }
spec:
  secretTargetRef:
    - parameter: connection
      name: sb-secret
      key: AZURE_SERVICE_BUS_CONNECTION_STRING
---
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata: { name: sb-consumer-pedidos, namespace: sb-middleware }
spec:
  scaleTargetRef: { name: sb-consumer-pedidos }
  minReplicaCount: 1     # nunca cai a 0 — peek-lock precisa de pod ativo
  maxReplicaCount: 5
  pollingInterval: 30
  cooldownPeriod: 300
  triggers:
    - type: azure-servicebus
      metadata:
        queueName: pedidos
        messageCount: "10"   # 1 réplica adicional a cada 10 mensagens em backlog
      authenticationRef: { name: sb-auth }
```

Replicar trocando `pedidos` → `contatos|oportunidades|relatorios`.

> **Por que `minReplicaCount: 1` em vez de 0?** Tempo de cold start (build de
> SF/SAP client + auth) é ~3-5s. Para a demo com volume baixo mas constante,
> manter 1 pod sempre ativo é mais previsível que escalar do zero.

---

## Etapa 6 — Verificação end-to-end

```bash
# 6.1 Pods running e healthy
kubectl -n sb-middleware get pods -o wide
# Esperado: 4 pods Running, READY 1/1

kubectl -n sb-middleware get deploy
# Esperado: 4 Deployments com READY 1/1

# 6.2 Logs estruturados (JSON) — boot bem-sucedido
kubectl -n sb-middleware logs deploy/sb-consumer-pedidos --tail=20
# Procurar: "middleware iniciando", "salesforce conectado"
kubectl -n sb-middleware logs deploy/sb-consumer-relatorios --tail=20
# Procurar: "relatorios handler pronto (SAP+SF)"

# 6.3 Probes batendo
kubectl -n sb-middleware exec deploy/sb-consumer-pedidos -- \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/ready').read())"
# Esperado: b'OK'

# 6.4 Smoke test — publicar mensagem de teste
# Do laptop (com .env apontando pra mesma SB):
python scripts/send.py --tipo pedido_criado --numero-pedido PED-K8S-SMOKE \
                       --correlation-id smoke-aks-001

# 6.5 Verificar processamento
kubectl -n sb-middleware logs deploy/sb-consumer-pedidos --tail=50 | grep PED-K8S-SMOKE
# Esperado: "opportunity criada" + "mensagem processada status=ack"

# 6.6 SF: confirmar Opp criada
# SOQL: SELECT Id, Name FROM Opportunity WHERE Name = 'PED-K8S-SMOKE'

# 6.7 CronJob SAP rodando
kubectl -n sb-middleware get cronjob sap-session-refresh
kubectl -n sb-middleware get jobs --sort-by=.metadata.creationTimestamp | tail -3
kubectl -n sb-middleware logs job/<nome-do-job-mais-recente>

# 6.8 KEDA escalando (se instalado)
kubectl -n sb-middleware get scaledobject
kubectl -n sb-middleware get hpa     # KEDA cria HPA por baixo
```

---

## Operação corrente

| Tarefa | Comando |
|---|---|
| Redeploy após nova imagem | `docker push ...:$TAG && kubectl -n sb-middleware set image deploy/sb-consumer-pedidos middleware=keeggosbacr.azurecr.io/sb-middleware:$TAG` (repetir pros 4) |
| Rollback                  | `kubectl -n sb-middleware rollout undo deploy/sb-consumer-pedidos` |
| Restart manual            | `kubectl -n sb-middleware rollout restart deploy/sb-consumer-pedidos` |
| Forçar refresh do `sessionId` | `kubectl -n sb-middleware create job --from=cronjob/sap-session-refresh manual-$(date +%s)` |
| Inspecionar DLQ (do laptop) | `python scripts/redrive_dlq.py --from pedidos --to pedidos --dry-run` |
| Escalar manualmente       | `kubectl -n sb-middleware scale deploy/sb-consumer-pedidos --replicas=3` (se KEDA não estiver gerenciando) |
| Ver eventos do namespace  | `kubectl -n sb-middleware get events --sort-by=.lastTimestamp` |

---

## Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| Pod em `CrashLoopBackOff` | Var obrigatória ausente — `__main__.py:131` retorna 2 | `kubectl logs <pod>` — procurar `[config] Variável obrigatória ausente` |
| Pod em `Error` no boot com `salesforce indisponível` | SF auth falhou | Conferir `sf-secret` (especialmente `SF_SECURITY_TOKEN` — concatena com password) |
| Handler SAP retorna `sap_session_unavailable` | `sessionId` vazio ou expirado | Forçar refresh (linha acima); se persistir, validar `sap-login` |
| Mensagens em retry crescente | Erro transiente externo (SF 5xx, SAP 429) | Inspecionar `delivery_count` — se crescer linearmente, o sistema externo está degradado; se chegar a 5, vai pra DLQ |
| Mensagem na DLQ com `DUPLICATE_VALUE` | Constraint Unique no SF (ver `docs/implementations/...`) | Validar schema; redrive após corrigir |
| `imagePullBackOff` | ACR não atachado ou imagem não existe | `az aks update -n aks-sb-middleware -g rg-sb-middleware --attach-acr keeggosbacr` |
| Pods não escalam com KEDA | `TriggerAuthentication` não acessa o secret | `kubectl describe scaledobject sb-consumer-pedidos -n sb-middleware` |

---

## Estrutura final dos arquivos no repo

Sugestão (não obrigatória — pode ficar fora do repo se preferir):

```
deploy/
├── Dockerfile                          # já existe
├── README.md                           # já existe
└── k8s/
    ├── 00-namespace.yaml
    ├── 10-configmap.yaml
    ├── 20-deploy-pedidos.yaml
    ├── 21-deploy-contatos.yaml
    ├── 22-deploy-oportunidades.yaml
    ├── 23-deploy-relatorios.yaml
    ├── 30-sap-refresh-rbac.yaml
    ├── 31-sap-refresh-cronjob.yaml
    └── 40-keda-*.yaml                  # 4 arquivos (1 por fila)
```

Aplicar tudo em ordem:
```bash
kubectl apply -f deploy/k8s/
```

---

## Referências

- `docs/architecture.md` — seção "Kubernetes (planejado)" e decisões de
  idempotência/peek-lock que justificam `terminationGracePeriodSeconds=60`.
- `deploy/README.md` — vars obrigatórias por fila, healthchecks, troubleshooting
  comum aplicável dentro e fora do K8s.
- `.env.example` — fonte canônica das vars (espelhada em ConfigMap + Secrets).
- `src/middleware/__main__.py:31-124` — `_build_handlers` mostra exatamente
  quais integrações cada `QUEUE_NAME` precisa.
- `docs/runbook.md` — operação geral do middleware (filas, DLQ, redrive).
- KEDA: <https://keda.sh/docs/scalers/azure-service-bus/>
- Reloader (alternativa a `rollout restart` no CronJob): <https://github.com/stakater/Reloader>
