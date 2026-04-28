"use client";

import { init as initApm } from "@elastic/apm-rum";
import { useEffect } from "react";
import { setApiBaseURL } from "@/services/api";

export function ApmRumProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch("/api/config");
        const config = await res.json();
        const serverUrl = config.apmServerUrl || process.env.NEXT_PUBLIC_APM_SERVER_URL;
        const serviceName = config.apmServiceName || process.env.NEXT_PUBLIC_APM_SERVICE_NAME || "demo-pv";
        const apiUrl = config.apiUrl || process.env.NEXT_PUBLIC_API_URL;

        if (apiUrl && typeof window !== "undefined") {
          setApiBaseURL(apiUrl);
        }

        if (!serverUrl || cancelled) return;

        let origins: string[] = [];
        if (typeof window !== "undefined") {
          try {
            origins = apiUrl ? [new URL(apiUrl, window.location.origin).origin] : [window.location.origin];
          } catch {
            origins = [window.location.origin];
          }
        }

        initApm({
          serviceName,
          serverUrl,
          serviceVersion: "0.1.0",
          environment: process.env.NODE_ENV || "production",
          distributedTracingOrigins: origins,
          transactionSampleRate: 0.5, // Reduzir amostragem
        });
      } catch {
        const serverUrl = process.env.NEXT_PUBLIC_APM_SERVER_URL;
        if (serverUrl && !cancelled) {
          initApm({
            serviceName: process.env.NEXT_PUBLIC_APM_SERVICE_NAME || "demo-pv",
            serverUrl,
            serviceVersion: "0.1.0",
            environment: process.env.NODE_ENV || "production",
          });
        }
      }
    })();

    return () => { cancelled = true; };
  }, []);

  return <>{children}</>;
}