# EFATÀ 777 — Mentoria IA para Negócios — M3-A

Data: 2026-11-09
Estado: SOURCE_PROPOSAL_ONLY — não aplicado em Git/Railway.

## Objetivo
Adicionar uma área privada de mentorado de **somente leitura** que consulta a
autorização real no backend a cada acesso, sem criar matrículas, pedidos, cobranças
ou conceder acesso. O conteúdo de aulas/vídeos **não** faz parte deste incremento.

## Arquivos (completos)
Backend:
- CREATE `src/orkio_v2/mentoria/portal_read.py`
- CREATE `src/orkio_v2/mentoria/portal_http.py`
- CREATE `tests/test_mentoria_m3a_portal.py`
- REPLACE `src/orkio_v2/config.py`
- REPLACE `src/orkio_v2/main.py`

Frontend:
- CREATE `src/routes/MentoriaPortal.tsx`
- CREATE `src/routes/MentoriaPortal.css`
- CREATE `tests/mentoria-m3a.test.mjs`
- REPLACE `src/App.tsx`
- REPLACE `src/routes/MentoriaLanding.tsx`
- REPLACE `src/routes/AccessPortal.tsx`

## Contrato de acesso
- GET `/api/v2/mentoria/portal/me` — somente leitura, cookie/sessão canônica.
- Exige `MENTORIA_PORTAL_ENABLED=true` no servidor (default: false).
- A identidade vem do `require_principal` e `verified_buyer` (User, Membership ativa,
  MentoriaMember ativa e e-mails verificados). Nenhum tenant no browser.
- Consulta SQL sempre restringe tenant, comprador, turma, pedido `PAID`/`ENROLLED`,
  enrollment `ACTIVE`, grant `ACTIVE` e intervalo de validade.
- O predicado de domínio `allows_mentoria_access` é aplicado novamente.
- Resposta contém somente título do programa, datas e timezone. Sem dados financeiros,
  IDs de usuário, lista de participantes, vídeo ou links privilegiados.
- Respostas com `Cache-Control: private, no-store`.

## Aplicação controlada (NÃO EXECUTADA)
1. Clonar os dois repositórios Premium oficiais; fixar HEAD SHA e branch.
2. Comparar os hashes da pré-imagem/manifesto do acumulado antes de modificar arquivo.
3. Nunca aplicar sobre `main` sem branch de revisão, diff e autorização.
4. Aplicar os arquivos completos em branch temporária depois de reconciliar conflitos.
5. Executar pytest e Node 20.20.2 com `npm ci`, typecheck/build.
6. Testar acesso HTTP real com cookies e PostgreSQL 16+ descartável.
7. Só após auditoria final AO-01 + decisão humana habilitar flag em STAGING.

## Testes executados localmente
- pytest focused M3-A: **12 PASS**
- pytest regressão selecionada Mentoria: **158 PASS, 4 SKIP PostgreSQL**
- node --test (M0/M1/M1-AI/M3-A): **17 PASS**
- Typecheck/build Vite Node20: NÃO EXECUTADOS.
- PostgreSQL real, runtime, GitHub CI, Asaas sandbox: NÃO EXECUTADOS.
- Os 13 cenários PostgreSQL anteriores do M2-B/M2-C também permanecem pendentes
  conforme histórico e não foram qualificados nesta etapa.

## Rollback
ANTES de Git: descartar este delta. Em branch aprovada: revert seletivo dos 11
caminhos declarados, sem `git clean -fd`, sem apagar registros. Na configuração
runtime, desligar primeiro `MENTORIA_PORTAL_ENABLED=false`. Não existe migration
nova no M3-A; as migrations 017-019 permanecem não aplicadas operacionalmente.

## Gate
M3A_SOURCE_LOCAL=PASS; GIT_HEAD=NOT_PROVEN; POSTGRESQL=NOT_PROVEN;
NODE20_BUILD=NOT_PROVEN; RAILWAY=NO_GO; PRODUCTION=NO_GO.
