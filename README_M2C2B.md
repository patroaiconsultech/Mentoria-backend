# EFATÀ 777 | Mentoria M2-C2B | Entrega para desenvolvimento local

`SOURCE_PROPOSAL_ONLY` — **não executar contra Railway, Git main, Asaas ou PostgreSQL operacional**.

**Base imutável**: `Mentoria_EFATA777_Acumulado_M2C2A_20261108.zip`
SHA-256: `ba11b791891a2497c6d5661937a5fac8e036c01ae5d2daddae32a9712c852e68`

Este pacote é um patch incremental, não um repositório inteiro. O acumulado
M0 → M2-C2B contém os arquivos completos, inclusive todos os incrementos anteriores.

## PATH / AÇÃO / MOTIVO
Veja `manifest.json` para CREATE/REPLACE, SHA anterior e novo SHA de cada
caminho. Os 22 arquivos alterados deste incremento estão em
`payload/backend/<PATH>`. Nenhum frontend foi alterado no M2-C2B.
A aplicação futura exige reconciliação byte a byte com o HEAD oficial e
um commit/branch aprovado. **Não substituir diretórios do repositório às cegas.**

## Instalação local para REVISÃO DE CÓDIGO
1. Verificar ZIP SHA, CRC, `SHA256SUMS.txt` e manifesto.
2. Conferir que os arquivos em `payload/backend/` são os arquivos completos.
3. Usar o importador existente apenas após reconciliação/autorizações. O
   modo dry-run não equivale a correspondência com o remoto.
4. Fazer testes em ambiente isolado:
```
export PLATFORM_ENVIRONMENT=test PLATFORM_AUTH_MODE=test
export DATABASE_URL='sqlite:///:memory:'
PYTHONPATH=src python -m pytest -q tests/test_mentoria_m2c2b_boundaries.py \
    tests/test_mentoria_m2c2b_migration.py
PYTHONPATH=src python -m alembic heads
```
Não configurar `MENTORIA_M2C2B_ENABLED=true` em ambiente de usuários.
O workflow 07 foi ampliado, mas **ainda não foi executado em GitHub Actions**.
Sua execução exige autorização de commit exato e banco PG descartável.

## Testes executados
- Regressão selecionada: **268 PASS, 13 SKIP PostgreSQL**.
- Ensaio DDL 019 isolado em SQLite: 4 PASS; PostgreSQL real: NÃO_PROVADO.
- Testes HTTP/identidade/worker locais: 20 PASS.
- Alembic graph local: `019_mentoria_webhook_inbox (head)`.
- Build frontend, integração Asaas sandbox, middleware com sessão real, Railway:
  NÃO EXECUTADOS.
- Duas falhas existentes de Knowledge fora da suíte selecionada não foram corrigidas.

## Flags / Segredos
`MENTORIA_M2C2B_ENABLED=false` default; `MENTORIA_ASAAS_WEBHOOK_TOKEN`
obrigatório para rota em laboratório, exclusivo da Mentoria, mínimo 32
caracteres. Manter `MENTORIA_M2_ENABLED` e `MENTORIA_M2C2_ENABLED`
inativas fora de laboratório isolado. Não compartilhar tokens em logs,
frontend, scripts públicos ou AO-01.

## Rollback
Sem Git/DB operational: descartar delta. Após execução autorizada em DB,
DESLIGAR flags, suspender worker e reverter código sem apagar histórico.
Migration 019 impede downgrade com registros duráveis.

Ver detalhes técnicos e riscos no `docs/M2C2B_ARQUITETURA_TESTES_ROLLBACK.md`.
