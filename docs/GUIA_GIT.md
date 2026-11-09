# Procedimento novo de integração Git — seguro e reversível

## 1. Fixação de target (obrigatório, separado por repo)
Use as URLs **oficiais**:
- Backend: `https://github.com/patroaiconsultech/efata-777-backend-premium-final-20260917`
- Frontend: `https://github.com/patroaiconsultech/efata-777-frontend-premium-final-20260917`

Clone ou atualize a branch `main` na sua máquina autorizada. Anote:
`git rev-parse HEAD`, `git status --porcelain`, branch, árvore e estado do PR.
O SHA HEAD dos repos oficiais **não foi verificado nesta sessão**.
Nunca assuma que staging ZIP = HEAD Git = Railway runtime.

## 2. Faça branch sem alterar `main`
Exemplo *a executar por operador habilitado* em CADA clone, a partir de main limpo:
```bash
git switch -c feature/mentoria-git-20261105
git rev-parse HEAD  # COPIE o SHA de 40 caracteres
git status --porcelain
```

## 3. Inspecione, não force
Com o pacote descompactado (diretório contendo `tools/`, `payload/` e `manifest.json`):
```bash
python tools/apply_git_package.py --repo backend --target /CAMINHO/CLONE_BACKEND --mode check
python tools/apply_git_package.py --repo frontend --target /CAMINHO/CLONE_FRONTEND --mode check
```
Se aparecer `STOP_NO_WRITE`, o **HEAD não é compatível com os preimages do snapshot**.
Parar, abrir o arquivo existente e fazer rebase/manual review com novo manifesto; **não usar `--force`**.

## 4. Aplicação local (somente após checagem e autorização operacional)
```bash
python tools/apply_git_package.py --repo backend --target /CAMINHO/CLONE_BACKEND --mode apply --expected-head SHA_BACKEND_40_HEX
python tools/apply_git_package.py --repo frontend --target /CAMINHO/CLONE_FRONTEND --mode apply --expected-head SHA_FRONTEND_40_HEX
```
O importador **não** faz `git add`, `commit`, `push`, PR, merge, migration nem deploy.

## 5. Diff, qualidade, testes
No backend:
```bash
git diff --check
python -m pytest -q tests/test_mentoria_m2_domain_contracts.py tests/test_mentoria_migration.py tests/test_mentoria_workshop_registration.py tests/test_mentoria_m2b_schema.py tests/test_mentoria_pg_gate.py
python -m alembic heads
```
No frontend com **Node 20.20.2** e npm 10.8.2:
```bash
npm ci
npm run check
npm run build
```
Para aprovação de PostgreSQL, criar PR e executar workflow isolado `06-mentoria-postgres-gate.yml`.
Ele testa as 7 corridas/DDL em PostgreSQL descartável e **falha com qualquer SKIP**.
Não apontar o job para produção. Teste local de SQLite não equivale a PostgreSQL.

**Validar também** OpenAPI, HTTP auth, SSRF/secrets, console de erros, E2E e cenários
de cross-tenant antes de autorizar matrícula/cobrança.

## 6. Gates separados
`DESIGN → SOURCE REVIEW → PG CI → REVIEW AO-01 FINAL → HUMAN APPROVAL → GIT COMMIT/PUSH → PR → MERGE → RAILWAY STAGING → RUNTIME → PRODUÇÃO`.

Não confundir este pacote com GO para Git push ou para deploy. A **auditoria formal AO-01**
fica reservada ao pacote final da plataforma, de acordo com a diretriz do projeto.

## 7. Rollback
Antes de aplicar: nenhum efeito. Depois de `--apply`, sem commit e sem migration:
revisar `git status`, restaurar **somente** arquivos modificados da mentoria após confirmação,
e excluir **somente** arquivos novos enumerados no manifesto. Não usar `git clean -fd` global.
Se houver commit futuro, aplicar revert revisado sobre o commit correspondente.
Migrations financeiras nunca devem ser revertidas com DROP sem avaliação de dados existentes.
Feature flags de captação e M2 devem permanecer OFF até os respectivos gates.
