# EFATÀ 777 — DG-01 — M2-C2A | Reconciliação financeira segura + workflow M2-C1

Data: 2026-11-08
Gate: SOURCE_PROPOSAL_ONLY — NÃO executar em produção, staging ou Git sem gates próprios.
Parentesco: Mentoria_EFATA777_Acumulado_M2C1.zip
Parent SHA-256: `274ddfc77e64239679a2b9ca54ca9505fc4f3b6fe57fa1d09955079a80bbfe4e`

## ESTADO ATUAL E OBJETIVO
M0/M1/M1-AI/M2-A/M2-B/M2-C1 preservados. O M2-C1 exige evento financeiro previamente processado, mas não implementava a prova de autenticidade do provedor. M2-C2A adiciona o primeiro caminho interno de autenticação e reconciliação Asaas, sem registro de rotas HTTP públicas. Ajusta também a qualificação PostgreSQL do workflow 07 apontada pelo AO-01.

## EVIDÊNCIA E PRIMEIRA DIVERGÊNCIA
- `07-mentoria-m2c-postgres-gate.yml` anterior tinha `pull_request`, postgres:16 flutuante, porta 5432 fixa e validação JUnit por quantidade; divergência confirmada no artefato.
- Os repositórios Premium oficiais foram consultados via GitHub público; HEAD SHA completo e commits implantados NÃO comprovados. O alvo desta proposta é o snapshot de staging, não uma branch oficial.
- Asaas documenta webhook com `asaas-access-token`, reentregas at-least-once e eventos PAYMENT_CONFIRMED/PAYMENT_RECEIVED/REFUNDED/CHARGEBACK. A autenticação do header isoladamente não equivale a pagamento confirmado.
- `ROOT_CAUSE=NÃO_PROVADA` para incidentes de produção: este incremento é evolução, não hotfix de runtime.

## IMPLEMENTAÇÃO E ARQUIVOS (COMPLETOS NO PAYLOAD)
1. `backend/.github/workflows/07-mentoria-m2c-postgres-gate.yml` — REPLACE no DELTA, CREATE relativo ao Git original: exclusivamente workflow_dispatch com `expected_sha` 40-hex, checkout e identidade SHA, imagem PostgreSQL com digest pinado, porta dinâmica, prova local de serviço CI descartável e testes nominais (2 M2-C1 + 2 M2-C2) com zero SKIP.
2. `backend/src/orkio_v2/mentoria/asaas_reconciliation.py` — CREATE: autenticação timing-safe do header e parsing restrito; GET somente leitura com URL HTTPS Asaas fixa, no-redirect, no ambient proxy, API key exclusivamente server-side; cálculo em centavos via Decimal; mapeamento conservador de estados.
3. `backend/src/orkio_v2/mentoria/financial_ledger.py` — CREATE: gravação idempotente por event_id, binding de attempt/provider/order/tenant, bloqueio canônico cohort → order → attempt, comparação referência/valor, redutor conservador, auditoria/outbox no mesmo contexto transacional e suspensão após fato adverso, sem auto-matrícula.
4. `backend/src/orkio_v2/mentoria/m2c2_pipeline.py` — CREATE: orquestrador INTERNO que autentica e consulta o provedor ANTES de abrir transação; não instala endpoints.
5. `backend/tests/test_mentoria_m2c2_reconciliation.py` — CREATE: testes negativos, replay, segurança do provedor, quantias, mudança de estado, rollback e 2 testes opt-in de PostgreSQL real.

## FLUXO CONFIÁVEL PROPOSTO
Webhook Asaas → header `asaas-access-token` com `compare_digest` → validar estrutura → GET /payments/{id} no Asaas com API key no servidor → resolver tentativa vinculada pelo payment_id persistido → transação PostgreSQL explícita → bloqueio cohort/ordem → comparar externalReference, preço, moeda e tenant derivado do banco → reducer financeiro → evento/auditoria/outbox → suspensão em fato adverso.

**Pagamento reconciliado nunca cria matrícula automaticamente.** A matrícula permanece responsabilidade do M2-C1 após checar todas as condições; até aqui não existe ingress HTTP ou worker ativo.

## TESTES / EVIDÊNCIA
Execução local em Python 3.13 com dependências disponíveis no sandbox, contra overlay derivado do ZIP de staging, sem URL operativa. Comando:

`python -m pytest -q --tb=short tests/test_mentoria_m1ai_assistant.py tests/test_mentoria_m2_domain_contracts.py tests/test_mentoria_m2b_schema.py tests/test_mentoria_m2b_postgres.py tests/test_mentoria_m2c_fulfillment.py tests/test_mentoria_m2c2_reconciliation.py tests/test_mentoria_pg_gate.py tests/test_mentoria_workshop_registration.py`

Resultado observado: **192 PASS, 11 SKIP**, warnings de lifecycle FastAPI. 11 SKIP = 7 M2-B PostgreSQL, 2 M2-C1 PostgreSQL, 2 M2-C2 PostgreSQL. Workflow YAML também carregado via parser BaseLoader, não executado no GitHub. Testes de integração Asaas real, concorrência PostgreSQL, webhook HTTP e identidade real NÃO executados. `PASS_LOCAL != PASS_RUNTIME`.

## GATES
- SOURCE_PROPOSAL_ONLY = true
- GIT HEAD SHA = NOT_PROVEN; `git apply` / commit / push / PR = NO-GO
- 06 PostgreSQL CI permanece com gatilhos anteriores: fora deste patch. Qualificação plena requer revisar 06 separadamente.
- PG real M2-C1/M2-C2 = NOT_PROVEN; digest de container deve ser confirmado pela execução CI.
- Provedor Asaas sandbox/produção = NOT_PROVEN
- Endpoint webhook durável, fila de entrada, retry, reconciler periódico, observabilidade = NOT_IMPLEMENTED
- Autenticação HTTP de comprador, sessão, membership e autorização de conteúdo = NOT_IMPLEMENTED
- Checkout operacional, concessão de matrícula real, frontend build, Railway = NO-GO
- Multi-account Asaas requer mapeamento explícito por conta, nunca fallback global.

## RISCOS
- Webhook não é garantia de recebimento nem ordenação; autenticação do token não dispensa consulta ao pagamento remoto.
- O payload do evento não pode fornecer tenant, valor autoritativo, acesso nem identidade.
- Provider GET pode observar um estado anterior a outro evento concorrente; estados terminais não podem ser reativados por notificação atrasada. Reconciliation periódica ainda é necessária.
- A aplicação de fatos adversos exige revisão do consumo real do grant para negar acesso imediatamente, mesmo se worker de suspensão falhar.
- Política de privacidade, dados financeiros, retenção, erros upstream e assinatura do provedor dependem de confirmação em ambiente autorizado.

## ROLLBACK
1. Sem instalação: descartar delta. O M2-C1 original permanece intacto.
2. Em branch de desenvolvimento futuramente autorizada: desativar `MENTORIA_M2C2_ENABLED`, remover os quatro arquivos CREATE e restaurar workflow 07 ao conteúdo anterior, com commit revert específico; verificar diff contra HEAD fixado.
3. **Não apagar registros de pagamento/evento/auditoria/outbox.** Reverter código não equivale a reverter um pagamento real.

## PRÓXIMO GATE E HANDOFF AO-01
Usar estes artefatos somente para desenvolvimento local. Antes de integrar: reconciliar HEAD Git oficial; executar imagem/CI PostgreSQL descartável com quatro cenários nomeados zero SKIP; validar provedor sandbox; introduzir inbound durável e identidade backend sem tenant vindo do browser; preparar resultados para auditoria formal no pacote final. Auditoria formal AO-01 não realizada por DG-01.
