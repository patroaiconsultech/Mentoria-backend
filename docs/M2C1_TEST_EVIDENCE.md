# M2-C1 — Evidências de teste (DG-01)
Data: 2026-11-08

Resultado de execução local **selecionada**:
- `test_mentoria_m2c_fulfillment.py`: 14 PASS, 2 SKIP (PostgreSQL indisponível).
- Regressão agregada (M2C1, domínio M2, schema M2B, M1AI, cadastro M1):
  **148 PASS, 2 SKIP**, exit code 0, execução ~1,34 s.
- `python3.13`, `pytest 9.0.2`, `SQLAlchemy 2.0.50` no ambiente local.
- Warnings preexistentes `FastAPI.on_event` deprecation (não são falhas).
- CI novo não executado; `Postgres: NOT_PROVEN`.
- Nenhuma migration, webhook, API externa, commit, push, deploy ou operação Railway.

Emulação SQLite *não prova* locks nem concorrência de PostgreSQL. Os dois
testes reais incluídos são:
  1. `test_real_pg_reconciled_placement_and_rollback`
  2. `test_real_pg_concurrent_same_order_is_idempotent`

**Critérios de GO técnico posterior:** os dois testes acima executam realmente
em banco `*_m2c_test`, sem skips; reconciliação de API do provedor autenticada,
HTTP identity e permissões comprovadas. O workflow `07` exige zero skips.
