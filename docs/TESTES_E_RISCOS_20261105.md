# Evidências DG-01 — 2026-11-05
Escopo: artefatos locais de staging + overlay M0→M2-B + PG gate.

| Teste / verificação | Resultado nesta sessão | Camada |
|---|---|---|
| `pytest` 5 módulos Mentoria (domain, migration, intake, schema, PG) | 94 PASS, 7 SKIP | CONFIRMADO_EM_TESTE_LOCAL (não PostgreSQL) |
| `pytest` 6 módulos de regressão selecionados | 48 PASS | CONFIRMADO_EM_TESTE_LOCAL |
| `pytest tests/test_mentoria_pg_gate.py` | 6 PASS | CONFIRMADO_EM_TESTE_LOCAL |
| `npm test` | 480 PASS | CONFIRMADO_EM_TESTE_LOCAL |
| `npm run verify:lock` | PASS | CONFIRMADO_EM_TESTE_LOCAL |
| `python -m alembic heads` | `018_mentoria_core` | CONFIRMADO_EM_ARTEFATO_LOCAL |
| `scripts/check_migration_hygiene.py` | PASS WITH KNOWN DEBT `EFATA-AUD-001` | CONFIRMADO_EM_TESTE_LOCAL |
| `scripts/check_workflow_action_pinning.py` | FAIL, existente em `05-josue-cedar-offline.yml` com `@v4` | OPEN, fora da alteração M2 |
| `tsc --noEmit` | FALHOU por ausência de `node_modules` (JSX types não resolvidos) | NÃO_PROVADO (Node20) |
| `npm run build` em Node20 | não executado | NÃO_PROVADO |
| `pytest -q` backend completo | interrupção por timeout local (35s) | NÃO_PROVADO |
| PostgreSQL 7 cenários M2-B | 7 SKIP; ausência de PG descartável local | NÃO_PROVADO |
| Git importador em clones descartáveis | backend 29/29 + frontend 8/8; 2ª checagem idempotente; rejeição de preimage alterada e SHA ausente | CONFIRMADO_EM_TESTE_LOCAL |
| Compatibilidade com HEAD Git oficial | nenhum SHA recuperado/validado | NÃO_PROVADO |
| Railway e API operacional | não consultados | NÃO_PROVADO |

Nenhum teste PostgreSQL foi falsamente promovido a PASS. `pg_config` disponível, mas
não há binário servidor nem `psycopg` no ambiente atual.

## Gates até a homologação final
1. Fixar SHA real de cada clone oficial, reconciliar divergências via diff.
2. Corrigir débito de pinning em frente governada separada, caso continue no HEAD.
3. Rodar workflow PostgreSQL descartável (`06-mentoria-postgres-gate.yml`),
   full Alembic upgrade e os 7 cenários PG com 0 SKIP.
4. Executar Node20 `npm ci`, typecheck, build, E2E responsivo e acessibilidade.
5. Concluir M2-C (billing seguro/identidade/matrícula/controle de acesso).
6. Concluir M3 portal e M4 integrações Zoho conforme escopo aprovado.
7. Gerar pacote final acumulado, hashes/risco/rollback, revisão AO-01.
8. Git push/PR/merge, Railway e produção são gates posteriores e independentes.

`SOURCE_CANDIDATE_FOR_GIT_REVIEW=true`; `PRODUCTION_GO=false`.
