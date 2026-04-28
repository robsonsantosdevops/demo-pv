/**
 * Instrumentação do Next.js — executada no servidor ao iniciar.
 * APM já é carregado via --require=elastic-apm-node/start.js no CMD (config via env).
 * Logger e log de bootstrap (Logstash se configurado).
 */

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { logger } = await import("./lib/logger");
    logger.info("Next.js server started", {
      runtime: process.env.NEXT_RUNTIME,
      nodeVersion: process.version,
    });
  }
}
