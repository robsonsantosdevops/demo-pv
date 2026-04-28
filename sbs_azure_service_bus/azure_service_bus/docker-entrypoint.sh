#!/bin/sh
# Reinicia o middleware após falha com pausa (evita CrashLoop apertado no Salesforce/SAP/Service Bus).
# Saída 0 do processo Python encerra o container normalmente (shutdown gracioso).
set -eu

DELAY="${RESTART_DELAY_SECONDS:-300}"
echo "docker-entrypoint: RESTART_DELAY_SECONDS=${DELAY}s"

while true; do
  python -m middleware
  CODE=$?
  if [ "$CODE" -eq 0 ]; then
    exit 0
  fi
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") middleware exited=${CODE}; sleeping ${DELAY}s before retry" >&2
  sleep "$DELAY"
done
