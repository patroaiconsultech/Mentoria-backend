# Handoff AO-01 — DG-REALTIME-01 P0.3 (preparação)
**Estado:** GO para leitura/testes locais. NO-GO para execução/staging/produção.

## Objeto
Endurecimento da cadeia de entrega local; não é a P0.3 de desbloqueio de escrita.
A P0.2 foi mantida byte a byte, inclusive seu bloqueio `REMOTE_WRITES_ENABLED=false`.

## Novos arquivos
- `scripts/p03_readiness.mjs` — valida os hashes P0.2, trava de escrita,
  alvo `staging-web01` e esquema das oito flags de gate; termina sempre NO-GO.
- `tests/p03_readiness.test.mjs` — seis testes: baseline íntegra, autoaprovação
  por flags não concede GO, script adulterado, testes adulterados, esquema
  incompleto e target incorreto.
- `README_P03.md`, este handoff e novo manifesto SHA-256.

## Contratos revalidados (fonte, não runtime)
No código `f433606` do backend staging, `PUT /api/v2/admin/agents/{agent_slug}/voice-assignment`
desativa o assignment ativo anterior antes de criar o DRAFT. Falta operação atômica
condicional/idempotente para concorrência real. GET de `agent-voice-assignments`
retorna tenant-scoped, mas omite `delivery_modes`, limitando reconciliação.
A P0.3 de preparação **não altera** esses contratos.

## Evidências pendentes (não preencher por inferência)
1. Confirmação independente do deployment/source SHA atual.
2. Aprovação explícita AO-01 da segregação efetiva do banco.
3. Principal administrativo e tenant autenticados por origem segura.
4. Triagem/liberação da origem sinalizada; não inserir credenciais ou microfone.
5. Janela de exclusividade e ausência de escritor concorrente; se impraticável,
   propor patch backend condicional com teste PostgreSQL separado.
6. Controle real/aprovado de custos. `--budget-usd 1` não é teto de fornecedor.
7. Auditoria de versão desbloqueada separada; patch `false → true` NÃO aplicado.

## Estado e rollback
Sem escrita remota, sem migração e sem deploy. Rollback local: descartar a
pasta P0.3 e usar o pacote P0.2 cujo SHA já foi auditado. Em produção,
nenhuma ação autorizada.

## Próximo gate
AO-01: revisar P0.3 de preparação, validar evidências externas e decidir
se uma P0.3 executável pode ser proposta. `PASS_LOCAL != PASS_RUNTIME`.
