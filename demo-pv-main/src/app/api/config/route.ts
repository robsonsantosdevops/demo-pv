import { NextResponse } from "next/server";
import { logger } from "@/lib/logger";

/**
 * Configuração pública para o client (RUM, API URL).
 * Usado pelo ApmRumProvider em runtime (K8s): use APM_SERVER_PUBLIC_URL e API_PUBLIC_URL no deployment.
 * Cada chamada gera log no servidor → Logstash.
 */
export async function GET() {
  const apmServerUrl = process.env.APM_SERVER_PUBLIC_URL || process.env.ELASTIC_APM_SERVER_URL || process.env.NEXT_PUBLIC_APM_SERVER_URL || "";
  const apmServiceName = process.env.ELASTIC_APM_SERVICE_NAME || process.env.NEXT_PUBLIC_APM_SERVICE_NAME || "demo-pv";
  const apiUrl = process.env.API_PUBLIC_URL || process.env.NEXT_PUBLIC_API_URL || "";

  logger.info("Config requested", { hasApmUrl: !!apmServerUrl, hasApiUrl: !!apiUrl });

  return NextResponse.json({
    apmServerUrl,
    apmServiceName,
    apiUrl,
  });
}
