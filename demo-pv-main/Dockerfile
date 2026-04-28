# Dockerfile corrigido - usar Node.js 20
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --force || npm install

COPY . .

RUN chmod +x node_modules/.bin/next
# Instala ferramentas de debug
RUN apk add --no-cache \
    busybox-extras \
    net-tools

# Build da aplicação
RUN npm run build

# Em algumas versões/configs o Next coloca os assets em `.next/standalone/.next/static`.
# Garantimos que `/app/.next/static` exista para o estágio runner conseguir copiar.
RUN if [ -d ".next/standalone/.next/static" ] && [ ! -d ".next/static" ]; then \
      mkdir -p ".next" && cp -R ".next/standalone/.next/static" ".next/static"; \
    fi && \
    mkdir -p ".next/static"

# Produção
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
