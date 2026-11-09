# DG-01 — Mentoria Backend, Falha de Import 2026-11-09

**Gate:** PATCH CANDIDATO, não aplicado a GitHub/Railway, AO-01 deve auditar.

## Estado atual — comprovação

Log recebido `logs.1794250421739.json`, deployment `039c8d94-dbd0-5b42-85bc-d60eec8b984f`:
- [7/11] pip instalação concluída
- [8/11] `DIAG_FASTER_WHISPER_IMPORT_OK`
- [9/11] `ModuleNotFoundError: No module named 'orkio_v2.database'`
- O Dockerfile efetivamente compilado no log contém o passo simples `RUN python -c "import faster_whisper; ..."` (e não os marcadores `DG01_STT_CHECK_BEGIN` do patch instrumentado).
- HEAD remoto Git e deploy commit SHA completo não verificados.

## Correção causal mínima

`PATH: src/orkio_v2/database.py`
`ACTION: CREATE`, **somente se estiver ausente na branch efetivamente construída**.
Arquivo completo extraído sem alterações da baseline de staging de backend já fornecida pelo usuário.
SHA256: `834b1d77f98768f65479d275447366f7cf8cb6a8010ba2542dca44038e806367`.

**Nunca substituir um `database.py` já presente ou divergente.**
O arquivo contém criação do engine SQLAlchemy e `SessionLocal`: não execute migrations ou crie dados para testar import.

## Preflight antes de novo build

Em um clone local da branch efetiva do backend:

```bash
python tools/audit_backend_modules.py /caminho/para/Mentoria-backend
```

Se quiser o relatório estruturado:

```bash
python tools/audit_backend_modules.py /caminho/para/Mentoria-backend --json
```

O script lê arquivos, sem executar/importar a aplicação, e só lê 160 caminhos `src/orkio_v2/` da baseline. Reporta `MISSING`, `DIVERGENT`, `MAIN_IMPORT_MISSING`. Divergências de hash são informativas: podem ser atualizações legítimas. Não copiar arquivos automaticamente por essa razão.

**Aplicação:** criar branch, verificar HEAD e diff; salvar arquivo `payload/backend/src/orkio_v2/database.py` no caminho `src/orkio_v2/database.py`, depois reexecutar auditoria e testes; não escrever na main automaticamente.

## Testes

```bash
python -S -m unittest discover -s tests -p 'test_backend_audit.py' -v
python -m compileall -q payload/backend/src/orkio_v2/database.py
```

Testes reais PostgreSQL, import no Docker Linux e Railway runtime continuam **NOT_PROVEN**.

## Riscos

1. O último ZIP de GitHub enviado pelo usuário precede os reparos recentes; as 138 ausências de source aferidas nele não provam o estado atual de Git.
2. `database.py` cria o engine na importação com variável de ambiente ativa; `DATABASE_URL` real deve ser gerida somente server-side.
3. Mesmo após restaurar o arquivo, outros imports ausentes podem impedir o boot. Verificador de inventário deve preceder novo build.

## Rollback

Reverter apenas o commit que criou `src/orkio_v2/database.py`; se arquivo existia, abortar e revisar sem sobrescrever. Restaurar Dockerfile original do diagnóstico após terminar a qualificação.

## AO-01

Review `CREATE src/orkio_v2/database.py`, SHA, log da etapa 9/11, auditoria do clone real, testes e rollback. Produção: NO_GO.
