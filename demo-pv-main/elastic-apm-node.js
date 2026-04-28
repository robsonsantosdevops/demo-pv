/**
 * Configuração do Elastic APM para Next.js.
 * Variáveis de ambiente têm precedência (defina no sistema ou no script de start).
 * @see https://www.elastic.co/guide/en/apm/agent/nodejs/current/configuring-the-agent.html
 */
module.exports = {
  serviceName: process.env.ELASTIC_APM_SERVICE_NAME || "demo-pv",
  serverUrl: process.env.ELASTIC_APM_SERVER_URL || "http://localhost:8200",
  secretToken: process.env.ELASTIC_APM_SECRET_TOKEN,
  apiKey: process.env.ELASTIC_APM_API_KEY,
  environment: process.env.NODE_ENV || "development",
  active: process.env.ELASTIC_APM_ACTIVE !== "false",
  // Logs, tracing e dependências são habilitados por padrão
  captureBody: "off",
  transactionSampleRate: 1.0,
  centralConfig: false,
};
