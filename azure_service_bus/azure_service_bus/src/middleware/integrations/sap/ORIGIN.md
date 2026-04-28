# Origem do cliente SAP

Cliente derivado do projeto `sap-automation-lab`:

- **Caminho original**: `C:\Users\LucianoSilverioMarti\Documents\Python Projects\sap-automation-lab\src\sap_client.py`
- **Data da cópia**: 2026-04-22

## Diferenças em relação ao original

1. **Token session não é armazenado no client**. O original recebia o token
   no construtor e o mantinha pela vida do objeto. No cluster, um job
   externo atualiza a env var `sessionId` a cada ~30min; manter cache
   estático levaria o client a usar token expirado. Aqui o client delega
   a `SapSession` (em `session.py`), que relê do ambiente sob demanda.

2. **Retry automático em 401**. Se o Service Layer devolve
   `401 Session has expired`, o client chama `session.refresh()` (que
   força re-leitura do env) e refaz a chamada uma vez. Se ainda falhar,
   propaga a exceção para o handler tratar (geralmente com RETRY).

3. **Config injetada por construtor**. `base_url`, `ssl_verify`, `timeout`
   vêm de um `SapConfig` (dataclass), em vez de vir diretamente do env.

4. **Logger stdlib**. `logging.getLogger(__name__)` em vez dos prints do
   script original.

O contrato dos métodos `get` / `post` continua idêntico ao original. Um
método auxiliar `create_order(payload)` foi adicionado para encapsular o
`POST` na URL de Orders (`config.orders_url`).

## Idempotência (convenção de uso)

O handler `oportunidade_ganha` grava **`NumAtCard = opportunity_id`** em
toda Order criada, e consulta via
`/Orders?$filter=NumAtCard eq '<opp_id>'` antes de criar. Isso é convenção
da aplicação, não do client — mas é bom saber: se outro consumidor desse
client publicar Orders, mantenha a convenção para evitar duplicatas.

> **Por que não `Comments`?** `Comments` é memo field no SAP B1 e o Service
> Layer não aceita `contains` sobre memo. `NumAtCard` é varchar(100)
> filtrável nativamente com `eq`.

## Ao atualizar

Se o original ganhar novos métodos (ex.: `delete`, `patch`), reaplique aqui
mantendo a mesma política de sessão dinâmica (`SapSession`) e retry-on-401.
