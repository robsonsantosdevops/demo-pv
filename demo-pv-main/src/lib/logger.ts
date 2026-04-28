/**
 * Logger que envia logs para o Logstash (TCP) e para o console em desenvolvimento.
 * Use apenas em código server-side (API routes, Server Components, instrumentation).
 */

import winston from "winston";

// Transport Logstash (Winston 3.x) - só adiciona se host/porta estiverem definidos
const logstashHost = process.env.LOGSTASH_HOST;
const logstashPort = process.env.LOGSTASH_PORT;
const serviceName = process.env.ELASTIC_APM_SERVICE_NAME || process.env.NEXT_PUBLIC_APP_NAME || "demo-pv";

const transports: winston.transport[] = [
  new winston.transports.Console({
    format: winston.format.combine(
      winston.format.timestamp(),
      winston.format.colorize(),
      winston.format.simple()
    ),
  }),
];

if (logstashHost && logstashPort) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const LogstashTransport = require("winston-logstash/lib/winston-logstash-latest");
    const logstashTransport = new LogstashTransport({
      host: logstashHost,
      port: Number(logstashPort),
      node_name: serviceName,
      max_connect_retries: -1,
    });
    logstashTransport.on("error", (err: Error) => {
      // Falha ao enviar para Logstash (conexão ou pipeline) — aparece no console do pod
      console.error("[logger] Logstash transport error:", err.message);
    });
    transports.push(logstashTransport);
  } catch (err) {
    console.error("[logger] Failed to load winston-logstash:", err);
  }
}

export const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || "info",
  defaultMeta: {
    service: serviceName,
    env: process.env.NODE_ENV,
  },
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  transports,
});

logger.on("error", (err) => {
  console.error("[logger] Winston error:", err.message);
});
