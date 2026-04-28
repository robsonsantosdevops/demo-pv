import { NextResponse } from "next/server";
import { logger } from "@/lib/logger";

/**
 * API route de health check.
 * Usa o logger (logs enviados ao Logstash quando LOGSTASH_HOST/PORT estão definidos).
 */
export async function GET() {
  logger.info("Health check requested");
  return NextResponse.json({
    status: "ok",
    service: process.env.ELASTIC_APM_SERVICE_NAME || "demo-pv",
    timestamp: new Date().toISOString(),
  });
}
