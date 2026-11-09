# M3-A — Arquitetura, primeira divergência e plano de lançamento

## Estado e primeira fronteira
O material M0→M2-C2B contém a persistência de matrícula e de grants, mas não
oferece uma página privada que consulte a autorização corrente para consumo.
Este novo incremento cobre **somente leitura dos acessos existentes**. Não é
prova de funcionamento de checkout, identidade operacional ou vídeo.

`FIRST_UNPROVEN_BOUNDARY=POSTGRESQL_017_019_PLUS_REAL_SESSION`
`ROOT_CAUSE=NÃO_PROVADA` (desenvolvimento, não incidente comprovado).

## Arquitetura
`Browser /mentoria/area` → `apiJson` com cookies → FastAPI
`GET /api/v2/mentoria/portal/me` → `require_principal` →
`verified_buyer` → SQL com vínculo tenant/member/order/enrollment/grant/cohort →
`allows_mentoria_access` → JSON somente metadados.

O portal não armazena tokens, tenant IDs, role ou concessões no browser.
O link de login só aceita o caminho exato `/mentoria/area` no returnPath.

## Invariantes negativas
- Principal de outro tenant: nunca lista turma de origem.
- Membro sem e-mail verificado ou membership ativa: 403.
- Pagamento REFUNDED/DISPUTED/REVIEW_REQUIRED: turma invisível.
- Pedido fora de ENROLLED, grant revogado/vencido/suspenso: turma invisível.
- Flag desligada: 503. API indisponível: frontend mostra erro, não turma.
- Sem turma ativa: tela vazia, não cria matrícula.
- Aulas, gravações e agendamento individual continuam NÃO_IMPLEMENTADOS.

## Próximos gates antes do lançamento
1. Read-only reconciliation com HEAD SHAs dos repos oficiais; importador nunca
   deve sobrescrever pré-imagem divergente.
2. Pipeline com PostgreSQL descartável: upgrades `016→017→018→019`,
   teste concorrência de vagas/eventos, regressões sem SKIP e rollback vazio.
3. Node 20.20.2 `npm ci`, `npm run typecheck`, `npm run build` e E2E real.
4. Sessão canônica de comprador em staging; teste 401/403, tenant cruzado,
   expiração/revogação e ausência de cache.
5. Asaas sandbox: webhook durável, reconciliação, perda/retry e estorno.
6. M3-B agenda/conteúdo e M4 Zoho sob autorização e controle de acesso.
7. Revisão final AO-01, autorização de PR/merge, migration staging governada,
   Railway staging, provas runtime; produção somente após novos gates.

Nenhum item desta lista é considerado aprovado por existir código ou workflow.
