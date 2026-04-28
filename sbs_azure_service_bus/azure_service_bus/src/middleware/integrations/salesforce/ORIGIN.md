# Origem do cliente Salesforce

Este cliente foi derivado do projeto `salesforce-admin`:

- **Caminho original**: `C:\Users\LucianoSilverioMarti\Documents\Python Projects\salesforce-admin\client.py`
- **Data da cópia**: 2026-04-22

## Diferenças em relação ao original

O client original depende de dois módulos globais (`config.py` que lê
`.env` no import e `utils.logger.logger`). Para evitar efeito colateral no
import dentro do middleware, foram feitas adaptações mínimas:

1. **Config injetada por construtor**: o `SalesforceClient` agora recebe
   um `SalesforceConfig` (dataclass) no `__init__`, em vez de ler
   `SF_CONFIG` global. O middleware carrega essa config em
   `integrations/salesforce/config.py`.

2. **Logger stdlib**: trocado `from utils.logger import logger` por
   `logging.getLogger(__name__)`, coerente com o resto do middleware
   (JSON logger configurado em `logging_setup.py`).

3. **Métodos e fluxo de autenticação preservados**: as 3 estratégias
   (`_auth_oauth2`, `_auth_soap`, `_auth_oauth2_cli`) e os helpers
   (`get`/`post`/`delete`/`query`/`describe`) estão idênticos em
   comportamento e assinatura.

4. **`patch()` agora retorna `dict | None`**: o original devolvia `None`
   sempre. Aqui retorna o body JSON quando houver (usado pelo endpoint de
   upsert External ID, que devolve `{id, created, success}` no 201).

5. **Novo método `upsert_by_external(sobject, field, value, payload)`**:
   não existe no original. Faz
   `PATCH /sobjects/<sobject>/<field>/<value>` — o endpoint nativo do SF
   para upsert idempotente por External ID. Usado pelo handler
   `pedido_criado` via `SalesforceService.upsert_opportunity_by_correlation`.

6. **Retry automático em 401 INVALID_SESSION_ID**: access token SF tem TTL
   de ~2h; pods longos eventualmente veem session expirada. O wrapper
   `_request` detecta 401 com `INVALID_SESSION_ID` no body, chama
   `authenticate()` de novo e refaz a chamada 1x. Transparente ao chamador.
   O original levantava `PermissionError` e deixava a retentativa pro
   caller — o que no middleware virava DLQ por `MaxDeliveryCountExceeded`
   em qualquer pod com >2h de vida.

## Ao atualizar

Se precisar puxar mudanças do `salesforce-admin`, compare linha a linha e
reaplique aqui — não importar diretamente para não ressuscitar o
acoplamento a `SF_CONFIG` global. Preserve as adições (#4 e #5) porque
elas são específicas do middleware.
