// src/lib/apm.ts
// Inicialização do Elastic RUM Agent para Next.js
//
// Instalação:
//   npm install @elastic/apm-rum @elastic/apm-rum-react
//
// Variáveis de ambiente necessárias no .env.local:
//   NEXT_PUBLIC_APM_SERVICE_NAME=poliedro-frontend
//   NEXT_PUBLIC_APM_SERVER_URL=http://localhost:8200
//   NEXT_PUBLIC_APP_ENV=development

import { init as initApm } from '@elastic/apm-rum';

const apm = initApm({
    serviceName: process.env.NEXT_PUBLIC_APM_SERVICE_NAME || 'poliedro-frontend',
    serverUrl: process.env.NEXT_PUBLIC_APM_SERVER_URL || 'http://localhost:8200',
    environment: process.env.NEXT_PUBLIC_APP_ENV || 'development',

    // Só coleta em produção — evita ruído no dev
    active: process.env.NODE_ENV === 'production',
    logLevel: 'warn',

    // Coleta Core Web Vitals automaticamente (LCP, FID, CLS, TTFB)
    pageLoadTransactionName: typeof window !== 'undefined' ? window.location.pathname : '/',
});

export default apm;