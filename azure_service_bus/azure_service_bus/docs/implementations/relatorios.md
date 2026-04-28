# Implementação — Fila `relatorios` + tipo `pedido_report` / `relatorio_sap_request`

> **Status:** ✅ implementado e validado end-to-end em 2026-04-24.
> 105 testes pytest passam; 4 containers rodando no WSL; Relatorio_SAP__c
> + Relatorio_SAP_Linha__c populados na org SF a partir da Order no SAP B1.

## Contexto

O projeto `salesforce-admin` deployou no SF a feature **"Solicitar Relatório
SAP"**: custom objects `Relatorio_SAP__c` (master) + `Relatorio_SAP_Linha__c`
(detail), Apex, Flow, Quick Action na Opp, PermissionSet. Fluxo:

1. User abre uma Opp em `Closed Won` → clica na Quick Action.
2. Apex cria `Relatorio_SAP__c` com `Status__c='Solicitado'` + publica mensagem
   no Service Bus.
3. Middleware consome, consulta Order no SAP (filter `NumAtCard eq <opp_id>`),
   atualiza o `Relatorio_SAP__c` com os campos e substitui as linhas.

## Tipos sinônimos

O Apex evoluiu de **`pedido_report`** para **`relatorio_sap_request`** — o
middleware aceita ambos, com o mesmo handler. Nenhuma funcionalidade
diferente entre os dois nomes.

## Fila publicada pelo Apex

Atualmente o Apex publica na fila `pedidos` (`CMDT Azure_SB_Config.Pedidos`).
O middleware resolve isso via **ForwarderHandler** registrado no pod
`sb-consumer-pedidos`: ao receber `pedido_report` / `relatorio_sap_request`,
reenfileira a mensagem na fila `relatorios` e dá ACK. Assim a demo funciona
sem depender de mudança no Apex.

Quando o Apex for ajustado pra publicar diretamente em `relatorios` (CMDT
`Azure_SB_Config.Relatorios`), o Forwarder vira no-op e pode ser removido.

## Payload

```json
{
  "correlation_id": "ff0707cb-5ec6-4daa-9d37-419ffdc544d7",
  "opportunity_id": "006g5000003QwLCAA0",
  "opportunity_name": "PED-17",
  "account_id": "001g500000JHYNJAA5",
  "relatorio_sap_id": "a01g500000JVEF3AAP",
  "requested_by_user_id": "005g5000005FrKTAA0",
  "requested_at": "2026-04-24T19:13:33.493Z"
}
```

**Obrigatórios**: `opportunity_id`, `relatorio_sap_id`. Os demais vão pra log.

## Fluxo do handler `PedidoReportHandler`

1. Valida payload (DLQ se `opportunity_id` ou `relatorio_sap_id` faltar).
2. PATCH Relatorio_SAP__c → `Status__c='Em_Processamento'` (feedback imediato).
3. SAP: `GET /Orders?$filter=NumAtCard eq '<opp_id>'&$top=1` → pega DocEntry;
   `GET /Orders(<DocEntry>)` → traz Order completo com `DocumentLines`.
4. Order não encontrada → `Status__c='Erro'` + `Mensagem_Erro__c`. ACK.
5. Order encontrada:
   - PATCH Relatorio_SAP__c com DocEntry, DocNum, DocDate, DocDueDate, DocTotal,
     DocStatus (mapeado bost_Open→Open / bost_Close→Closed / bost_Cancelled→Cancelled),
     CardCode, NumAtCard, Comments, **8 UDFs** (U_SF_OppId, U_SF_OppName,
     U_SF_CorrelationId, U_Pedido_Id, U_Aluno_Nome, U_Aluno_Email,
     U_Curso_Nome, U_Curso_Descricao), Status='Recebido',
     Mensagem_Erro__c=null, Data_Recebimento__c=now.
   - DELETE linhas existentes de `Relatorio_SAP_Linha__c` (idempotência) +
     INSERT uma nova por `DocumentLines[i]` com LineNum, ItemCode, Quantity,
     UnitPrice, LineTotal. ACK.
6. Erros transientes (SAP 5xx/401/network, SAP `-2014` schema stale,
   SF 5xx/401) → RETRY.
7. Erros permanentes (SAP 4xx ≠ 401/408/429, SF 4xx validação) →
   `Status__c='Erro'` + ACK (dado ruim, não retry).

## Schema SF (Relatorio_SAP__c)

| Campo | Origem | Tipo |
|---|---|---|
| `Name` | auto | `REL-00000` (auto-number) |
| `Opportunity__c` | Apex | Lookup Opportunity |
| `CorrelationId__c` | Apex | UUID |
| `Status__c` | middleware | Picklist: `Solicitado` / `Em_Processamento` / `Recebido` / `Erro` |
| `Data_Solicitacao__c` | Apex | DateTime |
| `Data_Recebimento__c` | **middleware** | DateTime |
| `DocEntry__c`, `DocNum__c` | middleware (SAP) | Number |
| `DocDate__c`, `DocDueDate__c` | middleware (SAP) | DateTime |
| `DocTotal__c` | middleware (SAP) | Currency |
| `DocStatus__c` | middleware (SAP) | **Picklist restrito**: `Open` / `Closed` / `Cancelled` — mapeado de `bost_*` |
| `CardCode__c`, `NumAtCard__c`, `Comments__c` | middleware (SAP) | Text/LongText |
| `Mensagem_Erro__c` | middleware (erro) | LongText |
| `U_SF_OppId__c`, `U_SF_OppName__c`, `U_SF_CorrelationId__c`, `U_Pedido_Id__c`, `U_Aluno_Nome__c`, `U_Aluno_Email__c`, `U_Curso_Nome__c`, `U_Curso_Descricao__c` | middleware (UDFs SAP) | cópia dos UDFs gravados pela Order |

### Relatorio_SAP_Linha__c (child master-detail)

| Campo | Origem |
|---|---|
| `Relatorio_SAP__c` | reference MD pro pai |
| `Line_Number__c` | `LineNum` do SAP |
| `ItemCode__c` | `ItemCode` |
| `Quantity__c` | `Quantity` |
| `UnitPrice__c` | `UnitPrice` |
| `Total__c` | `LineTotal` |

## Arquivos

- `src/middleware/handlers/pedido_report.py` — handler principal
- `src/middleware/handlers/forwarder.py` — reenvia mensagens de `pedidos` → `relatorios`
- `src/middleware/integrations/sap/client.py` — novo método `find_order_by_numatcard(opp_id)`
- `src/middleware/integrations/salesforce/service.py` — `update_relatorio_sap`,
  `replace_relatorio_sap_linhas`, `mark_relatorio_erro`
- `src/middleware/dispatcher.py` — KNOWN_TYPES com `pedido_report` e
  `relatorio_sap_request` em `pedidos` (via Forwarder) e `relatorios`
- `src/middleware/__main__.py` — branch `queue_name=="relatorios"`
- `scripts/send.py` — `--tipo pedido_report` (com `--relatorio-id`)
- `tests/test_handler_pedido_report.py` — 10 testes

## Verificação end-to-end (executada)

- Mensagem real PED-17 (`006g5000003QwLCAA0`, Relatorio `a01g500000JVEF3AAP`)
  foi publicada pelo Apex na fila `pedidos`, caiu na DLQ como `unknown_type`
  antes desta implementação.
- Redrive: `python scripts/redrive_dlq.py --from pedidos --to relatorios
  --filter-tipo pedido_report`.
- Consumer processou em 3.5s: `Relatorio_SAP__c` ficou com `Status='Recebido'`,
  DocEntry=41384, DocNum=7447, DocTotal=16990, DocStatus='Open' (mapeado),
  U_SF_OppName='PED-17', U_Curso_Nome='Turma ITA Online',
  U_Aluno_Nome='Yasmin Baratheon'. 1 linha Relatorio_SAP_Linha__c criada.
- A segunda mensagem `relatorio_sap_request` (`a01g500000JVSUvAAP`) também
  processou com o mesmo handler.
