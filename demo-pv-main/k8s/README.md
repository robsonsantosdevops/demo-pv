# Kubernetes — demo-pv-front (Next.js)

## Recursos

- `deployment.yaml` — Deployment do frontend (porta 3000)
- `service.yaml` — Service ClusterIP (porta 80 → 3000)
- `ingress.yaml` — Ingress para expor o front (host/TLS configuráveis)

## Pré-requisitos

1. **Namespace** — todos os recursos usam o namespace `demo`:
   ```bash
   kubectl create namespace demo
   ```

2. **Secret para pull do ACR** (no namespace `demo`):
   ```bash
   kubectl create secret docker-registry acr-secret \
     --docker-server=<ACR_NAME>.azurecr.io \
     --docker-username=<ACR_USER> \
     --docker-password=<ACR_PASSWORD>
   ```

2. **Substituir no `deployment.yaml`** o placeholder `<ACR_NAME>` pelo nome do seu Azure Container Registry (ex.: `demokeeggo`).

## Aplicar

```bash
kubectl apply -f k8s/ -n demo
# ou, se já estiver no contexto: kubectl apply -f k8s/
```

## Variáveis opcionais

Descomente no `deployment.yaml` as env de Logstash e APM e ajuste os valores, ou use ConfigMap/Secret.
