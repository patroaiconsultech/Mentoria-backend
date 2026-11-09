# DG-01 | EFATÀ 777 | Mentoria M2-C2B
**Data:** 2026-11-08 · **Estado:** `SOURCE_PROPOSAL_ONLY` · **Gate:** desenvolvimento isolado  
**BASE:** `Mentoria_EFATA777_Acumulado_M2C2A_20261108.zip`  
**SHA-256 BASE:** `ba11b791891a2497c6d5661937a5fac8e036c01ae5d2daddae32a9712c852e68`

## OBJETIVO
Fechar as fronteiras que AO-01 identificou como ausentes no M2-C2A:
1. GET de identidade do comprador derivada da sessão canônica, sem mutação.
2. POST de entrada Asaas autenticada, com registro durável, confirmação APÓS commit e trabalhador separado.
Sem checkout, sem auto-matrícula, sem criação de admin, sem execução operacional.

## EVIDÊNCIAS / PROVENANCE
- Inspeção de snapshot de staging fornecido e ZIP acumulado M2-C2A.
- Backend Premium oficial visualizável no GitHub; HEAD SHA completo e compatibilidade NÃO_PROVADOS.
- A árvore Alembic proposta tem head local `019_mentoria_webhook_inbox`; isso NÃO prova a migração no PostgreSQL.
- A conta Asaas e o formato sandbox real NÃO foram validados.
- Nenhum Railway, Git, push, banco PostgreSQL real, cobrança ou token real utilizado.

## NOVO FLUXO — WEBHOOK
```
POST /api/v2/mentoria/webhooks/asaas
    flags OFF por padrão → corpo JSON <=32768 bytes
    authToken exclusivo no header `asaas-access-token` (comparação segura)
    autenticação + parsing de ID/tipo/paymentId
    PostgreSQL: resolver payment_attempt BOUND por payment_id no servidor
    → gravar inbox sanitized, UNIQUE(provider,event_id), commit
    → somente então HTTP 200 {received:true}
    (duplicata coincidente → 200, replay contraditório → 409)
    ↓ não depende da conexão HTTP
internal process_one(receipt_id)
    claim com FOR UPDATE SKIP LOCKED, lease e limite 12 tentativas
    → commit da claim
    → Asaas GET somente leitura (fora da transação)
    → transação: revalidar lease/payment binding
    → persist_verified_event M2-C2A
    → status PROCESSED na MESMA transação do ledger
    (falha transitória → RETRY com backoff; conflito → REVIEW)
```
A inbox salva **somente**: tenant derivado do banco, attempt, payment id, evento, tipo, fingerprint, estado, horários, tentativas, código fixo de erro. Não guarda JSON bruto, nome, e-mail, API key nem token.

O worker é função interna **sem scheduler em execução**. O agendamento periódico, alarme de filas REVISÃO, reprocessamento governado e reconciliação financeira periódica são gates posteriores, não funcionalidades operacionais concluídas.

A consulta financeira independente do Asaas e o ledger M2-C2A permanecem inalterados; somente a passagem autenticada pelo banco é nova. Eventos sem tentativa previamente vinculada são recusados (503 para retry); deve-se configurar um webhook Asaas exclusivo para cobranças da Mentoria, evitando alimentar esta rota com eventos de produtos não vinculados. Esta política requer validação operacional com o sandbox.

## NOVO FLUXO — COMPRADOR
```
GET /api/v2/mentoria/buyer/me
    require_principal (session nativa / OIDC conforme configuração)
    → User canônico + external_subject igual + email verificado
    → Membership ACTIVE do mesmo tenant no PostgreSQL
    → MentoriaMember ACTIVE, email verificado, issuer="efata-canonical-user",
      subject=User.id, tenant_id da sessão
    → 200 {"status":"ready"} (sem PII, pedido ou privilégios)
```
Não aceita `tenant_id`, usuário, papel ou oferta do browser. Não cria `MentoriaMember`, usuário, sessão, pedido, grant ou matrícula. Fluxo de provisionamento/ligação legítima deve ser concluído em incremento próprio antes da ativação do checkout.

## ARQUIVOS COMPLETOS
No ZIP: `payload/backend/<path>` contém os 22 arquivos criados/substituídos completos, com SHA.
- 019: tabela `mentoria_webhook_inbox` aditiva e FK composta contra tentativa/tenant/provider.
- ORM: `MentoriaWebhookInbox`.
- `m2c2b_buyer.py`, `m2c2b_http.py`, `m2c2b_ingress.py`, `m2c2b_worker.py`.
- `main.py` e `config.py`: rota e gates, sem ativar.
- `routes.py`, `tests/conftest.py` e testes de head: 018→019 apenas onde a expectativa de migration head mudou.
- Workflow 07: acrescenta dois testes PostgreSQL nomeados, invocação manual com SHA/PG descartável preservada.

## TESTES REALIZADOS
Execução local `python -m pytest -q` com 10 módulos Mentoria + 7 suites contratuais selecionadas:
**268 PASS, 13 SKIP, 2 warnings**. Os 13 SKIP são cenários PostgreSQL sem servidor descartável.
- `test_mentoria_m2c2b_boundaries.py`: 20 PASS (lógica HTTP, chave, duplicata, proteção tenant, lease/retry).
- `test_mentoria_m2c2b_migration.py`: 4 PASS (head local, DDL 019 isolado SQLite, downgrade vazio, bloqueio com recibos).
- `test_mentoria_m2c2b_postgres.py`: 2 SKIP, código preparado para PostgreSQL real (concorrência, rollback).
- `compileall`: PASS em Mentoria e migration 019.
- `python -m alembic heads`: `019_mentoria_webhook_inbox`.
- A cadeia Alembic **001→019 não foi executada** em PostgreSQL.
- A suite completa de Knowledge já apresentava 2 falhas não relacionadas à Mentoria nos snapshots anteriores. Não se alterou lógica Knowledge; não declarar full-backend PASS.

## FLAGS E SECRETS
`MENTORIA_M2C2B_ENABLED=false` (default) e ainda dependente de `MENTORIA_M2_ENABLED=true`, `MENTORIA_M2C2_ENABLED=true`; somente laboratório isolado poderá habilitar.
`MENTORIA_ASAAS_WEBHOOK_TOKEN`: segredo separado do billing da EFATÀ; nunca enviar ao browser ou logs, nem repetir `ASAAS_API_KEY`.
A rota do comprador usa a mesma flag mas não autoriza grants, checkout ou matrícula.

## MIGRATION 019 — UPGRADE/DOWNGRADE E RISCOS
- Dependência provisória `018_mentoria_core`; reconciliar com Alembic HEAD oficial antes do gate.
- Upgrade cria nova tabela + 2 índices, unique(provider,eventId), FK tenant/attempt/provider, restrições de estado/attempts. **Sem alterações/destruição das tabelas existentes, sem backfill**.
- PostgreSQL: ainda medir locks da FK, versão, check constraints e compatibilidade em base descartável. CREATE TABLE com FK pode adquirir locks breves nas tabelas referenciadas.
- Downgrade somente se a inbox estiver vazia. Com registros, aborta (não há rollback de dados financeiros por DROP).
- Rollback operacional preferível: desativar ingestão/worker, revert controlado de código e preservar recibos/ledger para reconciliação.

## RISCOS RESIDUAIS / NO-GO
- PG real concorrência + migration 017→018→019, Asaas sandbox, retry/observabilidade operacionais,
  reconciliação periódica, identidade native/OIDC HTTP real, consumo de grant após estorno,
  reconciliação com HEAD oficial, CI GitHub workflow 07, staging/produção.
- O teste de ORM/DDL em SQLite não prova locks ou performance PostgreSQL.
- Só há suporte para **uma configuração de webhook Asaas por vez** nesta proposta;
  múltiplas contas, rotação de chaves e quórum financeiro requerem desenho posterior.
- Toda tentativa de ativação antes dos gates = `NO-GO`.

## ROLLBACK
Nenhuma alteração foi feita em Git/Railway/DB operacional. Para descartar este delta, retirar arquivos M2-C2B criados e restaurar os caminhos substituídos com suas pré-imagens verificadas. Não aplicar `git clean -fd`.
Se já houver eventos duráveis após futura autorização de migration: desligar flags, suspender worker e preservar inbox, pagamentos, matrículas, outbox e auditoria. Não usar downgrade destrutivo.

## HANDOFF AO-01 (auditoria final)
Entregar: ZIP, manifesto SHA-256, diff dos 22 arquivos, logs dos 268 testes selecionados,
execução real PostgreSQL sem SKIP, SHA do checkout/HEAD, CI do commit candidato,
prova Asaas sandbox, testes de autorização HTTP, rollback e evidência do runtime.
AO-01 independente aprovará ou rejeitará os respectivos gates; este relatório não é aprovação.
