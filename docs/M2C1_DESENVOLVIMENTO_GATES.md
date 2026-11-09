# DG-01 — Mentoria EFATÀ 777 — M2-C1: Fulfillment transacional

**Data:** 2026-11-08  
**Estado:** `SOURCE_PROPOSAL_ONLY` — sem push, deploy, cobranças ou migration operacional.  
**Baseline:** ZIP acumulado M0/M1/M1-AI corrigido/M2-A/M2-B SHA-256 `8ef42c08a9c02696fdf0c04a1a925f628e4a411c0fa04e826f536f2b25adca76`.

## Objetivo / gate
Implementar somente o núcleo **backend interno** de concessão e suspensão de matrícula
após evidência persistida de reconciliação de pagamento. Nenhum endpoint público,
webhook, conexão Asaas, criação de identidade ou checkout externo é habilitado.

## Arquivos
1. `src/orkio_v2/mentoria/fulfillment.py` — CREATE. Serviço de colocação e suspensão.
2. `tests/test_mentoria_m2c_fulfillment.py` — CREATE. 14 testes SQLite de lógica/
   guardas, 2 ensaios PostgreSQL opt-in (não executados localmente).
3. `.github/workflows/07-mentoria-m2c-postgres-gate.yml` — CREATE. Qualificação
   futura em PostgreSQL descartável, impedindo SKIP nos dois cenários PG.

## Contrato e fronteira
- `place_reconciled_paid_order`: exige M2 e M2C habilitados explicitamente,
  PostgreSQL real, transação ativa do chamador, lock por tenant+turma,
  pedido `PAID` e evento de confirmação **processado**, associado a tentativa
  BOUND e payment ID não vazio.
- Confere membro ativo com e-mail verificado, preço do pedido versus oferta
  versionada, reserva ativa e capacidade sob o lock. Cria enrollment/grant,
  marca hold consumido e grava auditoria/outbox na mesma transação.
- Reserva expirada, inexistente ou turma encerrada gera `PAID_UNPLACED`,
  auditado e SEM grant; não faz matrícula automática posterior.
- `suspend_after_reconciled_adverse_fact`: exige estado financeiro adverso e
  evento processado, então suspende/revoga grant e matrícula sem apagar
  fatos financeiros. Reexecuções são idempotentes.

**Fronteira inegociável:** `processed_at` é uma condição necessária, não prova
criptográfica da autenticidade do provedor. O adapter futuro DEVE autenticar
e reconciliar com a API do provedor, conta, payment ID, montante, moeda e
event ID antes de alterar pedido/eventos. NÃO conectar este serviço a um
endpoint de browser, webhook bruto ou controle administrativo improvisado.

## Segurança
- Não recebe tenant, role, valor ou status do navegador.
- Sem API HTTP, sem credenciais, sem provedor externo, sem migration nova.
- Commit é responsabilidade do chamador. Não chamar API externa segurando lock.
- Lock order: turma → pedido → hold/matrícula.
- Feature flags `MENTORIA_M2_ENABLED` e `MENTORIA_M2C_ENABLED`, ambas false
  por padrão.
- Isolamento do tenant por filtros e FKs compostas já presentes no M2-B.
- Grant exige validação de acesso no backend (M3 ainda não implementado).
- Resgate de `PAID_UNPLACED`, alterações de identidade e chargebacks devem
  usar fluxos governados separados. Nenhum auto-unrevoke.

## Testes
Ambiente de snapshot local + overlay do acumulado corrigido.

```bash
PYTHONPATH=src python -m pytest -q tests/test_mentoria_m2c_fulfillment.py
PYTHONPATH=src python -m pytest -q \
  tests/test_mentoria_m2c_fulfillment.py \
  tests/test_mentoria_m2_domain_contracts.py \
  tests/test_mentoria_m2b_schema.py \
  tests/test_mentoria_m1ai_assistant.py \
  tests/test_mentoria_workshop_registration.py
```

**Executado:** 148 PASS e 2 SKIP nos cinco arquivos acima; 2 SKIP são PG.
Os 14 testes M2-C1 em SQLite incluem *emulação lógica explícita* com guard
substituído no teste; essa emulação NÃO comprova concorrência real. Guard
sem emulação recusa SQLite por padrão.
GitHub Actions `07` é somente proposta; não executado nesta sessão.

## Rollback
Antes de aplicação, arquivar ou descartar este delta. Após instalação autorizada:
desabilitar `MENTORIA_M2C_ENABLED`, retirar os três CREATE em revert de commit
sem tocar no esquema ou nos registros. Dados financeiros/eventos nunca são
apagados como rollback. O M2-B e módulos anteriores permanecem preservados.

## Riscos e gates
`HEAD_GIT=NOT_PROVEN`; `PG_CONCURRENCY=NOT_PROVEN`; `PROVIDER_VERIFICATION=NOT_IMPLEMENTED`;
`HTTP_IDENTITY=NOT_IMPLEMENTED`; `PAYMENT_WEBHOOK=NOT_IMPLEMENTED`;
`REDIS=NOT_PROVEN`; `FRONTEND_BUILD=NOT_PROVEN`; `RUNTIME=NOT_PROVEN`.
Não promover o serviço até adapter autenticado, reconciliação real, execução
PostgreSQL e revisão independente final AO-01.
