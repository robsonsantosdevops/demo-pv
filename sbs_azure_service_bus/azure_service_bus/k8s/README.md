# Kubernetes — middleware Azure Service Bus

Manifestos para executar **um Deployment por fila** (`QUEUE_NAME`), alinhado ao código em `src/middleware/` e ao `deploy/Dockerfile`.

## Pré-requisitos

1. **Namespace** `demo` (incluído em `namespace.yaml`; se já existir, o apply é idempotente).
2. **Secret** `sb-middleware-secrets` no namespace `demo` com as chaves necessárias (modelo em `secret.example.yaml`).
3. **Credencial de pull** da imagem: os Deployments referenciam `imagePullSecrets: acr-secret`. Ajuste o nome ou remova o bloco se a imagem for pública.
4. **Kubernetes ≥ 1.28** recomendado — os manifests usam `optional: true` em alguns `secretKeyRef` (Salesforce opcional na fila `oportunidades`).

## Imagem

Por defeito, o `kustomization.yaml` substitui a imagem `sb-middleware:latest` por:

`demokeeggo.azurecr.io/demokeeggo/sb-middleware:latest`

Altere `images` no `kustomization.yaml` ou faça build/push a partir da raiz do projeto:

```bash
docker build -t <seu-registry>/sb-middleware:<tag> -f deploy/Dockerfile .
docker push <seu-registry>/sb-middleware:<tag>
```

## Criar o Secret

Os Deployments usam `envFrom` com **`secretRef: sb-middleware-secrets`**: **todas** as chaves do Secret viram variáveis de ambiente (o ConfigMap entra primeiro; chaves repetidas no Secret sobrepõem). Assim não há risco de o YAML do Deployment listar um subconjunto e “esquecer” `SF_*` que existem só no Secret.

Não commite valores reais. Opções:

```bash
kubectl create secret generic sb-middleware-secrets -n demo \
  --from-literal=AZURE_SERVICE_BUS_CONNECTION_STRING='...' \
  --from-literal=SF_USERNAME='...' \
  --from-literal=SF_PASSWORD='...' \
  --from-literal=SF_SECURITY_TOKEN='...' \
  --from-literal=SF_ACCOUNT_MASTER_EXTRA='{"cnpj__c":"..."}' \
  --from-literal=sessionId='...' \
  --from-literal=SAP_BASE_URL='...' \
  --from-literal=SAP_COMPANY_DB='...'
```

Chaves opcionais (podem ser omitidas ou vazias conforme o deployment): `SF_CONSUMER_KEY`, `SF_CONSUMER_SECRET`.

### Alterou o Secret e o pod continua falhando?

O Kubernetes **não reinicia** automaticamente os pods só porque o Secret mudou (salvo se usar Reloader ou mudar o Deployment).

Depois de atualizar `sb-middleware-secrets`:

```bash
kubectl rollout restart deployment/sb-middleware-contatos -n demo
kubectl rollout status deployment/sb-middleware-contatos -n demo
```

Repita para os outros deployments (`pedidos`, `oportunidades`, `relatorios`) conforme necessário.

### Conferir se o Secret está no pod (nome, namespace, chaves)

- Namespace do workload deve ser o mesmo do Secret (manifestos usam `demo`).
- Nome do objeto deve ser exatamente **`sb-middleware-secrets`** (como nos YAML).
- Chaves **case-sensitive**: `SF_USERNAME`, não `sf_username`.

Validação rápida (sem exibir valores):

```bash
kubectl get secret sb-middleware-secrets -n demo -o jsonpath='{.data}' | wc -c
kubectl get deployment sb-middleware-contatos -n demo -o yaml | findstr /i "secretKeyRef"
```

Se `authenticate()` do Salesforce falhar, veja o **`SF_LOGIN_URL`** no ConfigMap `sb-middleware-config`:

- Sandbox “clássico”: `https://test.salesforce.com`
- Produção: `https://login.salesforce.com`
- **My Domain** (recomendado quando o login no browser é `*.lightning.force.com`): use o host **\*.my.salesforce.com** (em *Setup → My Domain*), **não** a URL `*.lightning.force.com` — o token OAuth fica em `https://<seu-host>/services/oauth2/token`.

## Aplicar

```bash
cd k8s
kubectl apply -k .
```

Apenas um subconjunto (ex.: só `pedidos`):

```bash
kubectl apply -f namespace.yaml -f configmap.yaml -f deployment-pedidos.yaml -f services.yaml
# Ajuste o services.yaml para aplicar só o Service correspondente ou use kubectl apply -f services.yaml com edição local.
```

## Health checks

| Rota        | Uso no cluster      |
|------------|---------------------|
| `/healthz` | Liveness só no Docker local; nos Deployments não há probe de liveness (durante `RESTART_DELAY_SECONDS` o HTTP pode estar em baixo). |
| `/ready`   | `readinessProbe` — pronto quando o consumer ligou ao Service Bus.    |

Após falha, o **`docker-entrypoint.sh`** espera **`RESTART_DELAY_SECONDS`** (default 300s no ConfigMap) antes de voltar a executar `python -m middleware`.

## Variáveis não secretas

`ConfigMap` `sb-middleware-config`: níveis de log, timeouts do consumer, defaults SAP, `SF_LOGIN_URL`, etc. Edite `configmap.yaml` conforme o ambiente.

## Filas e credenciais

| Deployment                   | Fila            | Credenciais típicas      |
|-----------------------------|-----------------|---------------------------|
| `sb-middleware-pedidos`     | `pedidos`       | Service Bus + Salesforce  |
| `sb-middleware-contatos`    | `contatos`      | Service Bus + Salesforce  |
| `sb-middleware-oportunidades` | `oportunidades` | Service Bus + SAP; SF opcional |
| `sb-middleware-relatorios`  | `relatorios`    | Service Bus + Salesforce + SAP |

O token SAP `sessionId` costuma ser renovado por job externo; atualize o Secret ou use ferramentas como Reloader quando o Secret mudar.

## Port-forward (debug)

```bash
kubectl port-forward -n demo deploy/sb-middleware-pedidos 8080:8080
curl -s http://localhost:8080/healthz
curl -s http://localhost:8080/ready
```
