This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Logs (Logstash) e APM (Elastic)

A aplicação envia **logs para o Logstash** e está instrumentada com **Elastic APM** para **tracing** e **dependências**.

### Logstash (logs)

- Os logs do servidor (Winston) são enviados ao Logstash via **TCP** quando as variáveis abaixo estiverem definidas.
- Use o logger em código server-side: `import { logger } from "@/lib/logger"` (API routes, Server Components, `instrumentation.ts`).
- Endpoint **POST /api/log** aceita eventos do client e reenvia ao Logstash (body: `{ "level": "info", "message": "..." }`).

**Variáveis de ambiente:**

| Variável        | Descrição                    | Exemplo        |
|-----------------|-----------------------------|----------------|
| `LOGSTASH_HOST` | Host do Logstash (input TCP)| `logstash`     |
| `LOGSTASH_PORT` | Porta do input TCP          | `28777`        |
| `LOG_LEVEL`     | Nível do logger             | `info`, `debug`|

**Exemplo de pipeline Logstash (input TCP):**

```ruby
input {
  tcp { port => 28777 type => "nodejs" codec => json }
}
filter {
  json { source => "message" }
}
output {
  elasticsearch { hosts => ["elasticsearch:9200"] }
  # ou stdout { codec => rubydebug }
}
```

### Elastic APM (tracing e dependências)

- O agente **Elastic APM** é carregado antes do Next.js nos scripts `dev` e `start`, gerando **tracing**, **métricas** e **dependências** no APM Server.
- Configuração em `elastic-apm-node.js` na raiz; variáveis de ambiente têm precedência.

**Variáveis de ambiente:**

| Variável                   | Descrição              | Exemplo                    |
|----------------------------|------------------------|----------------------------|
| `ELASTIC_APM_SERVICE_NAME` | Nome do serviço no APM | `demo-pv`                  |
| `ELASTIC_APM_SERVER_URL`   | URL do APM Server      | `http://localhost:8200`    |
| `ELASTIC_APM_SECRET_TOKEN` | Token (se exigido)     | —                          |
| `ELASTIC_APM_API_KEY`      | API key (alternativa)  | —                          |
| `ELASTIC_APM_ACTIVE`       | Desativar: `false`     | `true` (padrão)            |

**Endpoints úteis:**

- **GET /api/health** — health check (gera log no servidor → Logstash).

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
