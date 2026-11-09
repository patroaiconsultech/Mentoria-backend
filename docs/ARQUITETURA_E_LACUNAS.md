# Arquitetura — domínios e responsabilidades

`Landing/Workshop (M0/M1) → Identidade (M2-C) → Oferta/Pedido (M2-A/B)
→ Pagamento reconciliado (M2-C) → Matrícula (M2-C) → Grant (M2-C)
→ Portal e gravações (M3) → Integração Zoho (M4).`

## Estado técnico de cada área
| Domínio | Presente neste pacote | Não provado |
|---|---|---|
| Landing e formulário | React, rota `/mentoria`, M1 | Node20 build, E2E público |
| Captação | POST `/api/v2/public/mentoria/workshop-registrations`, middleware, migration 017 | PostgreSQL runtime, política LGPD |
| M2-A | Redutor financeiro e predicado de acesso isolados | Id autenticada/provider real |
| M2-B | 12 modelos/tabelas, migration 018, reserva sob row lock | concorrência PostgreSQL real |
| Billing | Apenas contratos internos, SEM checkout | webhook, settlement, disputes, reconciliação |
| Membros/Grants | Schema, SEM autorização HTTP | matrícula, revogação, auditoria de acesso |
| Portal/Vídeos | Fora deste pacote | gravações e Zoho |
| Railway | Fora deste pacote | implantação, predeploy, logs |

## Critérios mínimos para M2-C
- Auth adapter MUST derive tenant and subject from trusted server verification.
- Price snapshot ONLY from published offer in DB. No browser price/role.
- Verified payment via provider signed/authenticated webhook AND reconciliation;
  deduplicate event_id, reject mismatch/unknown and keep events immutable.
- Atomic hold→enrollment + grant in PostgreSQL with cohort lock.
- Revocation after chargeback/refund and fail-closed before access.
- Account for late payment after hold expiry without overselling.
- Admin capabilities explicit, no implicit superadmin.
- Add integration tests: 401, 403, cross-tenant, replay, out-of-order, webhook spoof,
  refund/chargeback, terminal errors, 50+1 reservation race.
- External provider credentials server-side only; feature flag OFF by default.

## Rail
Do not set auto-migration command or `seed_demo.py` for the Mentoria.
Deploy is a separate human gate and must prove source SHA and runtime identity.
