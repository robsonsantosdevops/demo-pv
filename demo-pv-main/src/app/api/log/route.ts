import { NextRequest, NextResponse } from "next/server";
import { logger } from "@/lib/logger";

/**
 * Endpoint para o client enviar eventos de log ao servidor;
 * o servidor reenvia ao Logstash (e o APM já captura erros/traces no servidor).
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { level = "info", message, ...meta } = body as { level?: string; message: string; [k: string]: unknown };
    const levelNorm = (level as string).toLowerCase();
    if (levelNorm === "error") {
      logger.error(message, meta);
    } else if (levelNorm === "warn") {
      logger.warn(message, meta);
    } else if (levelNorm === "debug") {
      logger.debug(message, meta);
    } else {
      logger.info(message, meta);
    }
    return NextResponse.json({ ok: true });
  } catch (e) {
    logger.error("Failed to process log from client", { error: String(e) });
    return NextResponse.json({ ok: false }, { status: 400 });
  }
}
