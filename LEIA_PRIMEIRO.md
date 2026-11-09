# DG-01 — Mentoria IA para Negócios / Backend — patch causal de build (09/11/2026)

## Evidência de primeira divergência
Build Railway: 2026-11-09T17:49:07Z, deployment ID `3b75c9d0-ea8d-55e1-956b-95e082dcdeb3`.
- `src/orkio_v2/config.py`, linha 7: `from .provenance import resolve_build_provenance`.
- `ModuleNotFoundError: No module named 'orkio_v2.provenance'`.
- `Dockerfile` já foi detectado, o `pip install --require-hashes` concluiu sem erro.
- `ROOT_CAUSE` comprovada apenas para ESTE build: módulo ausente do contexto de build.
- O arquivo foi recuperado **sem alterações** do snapshot de staging fornecido e é idêntico à cópia no pacote completo de restauração de 09/11/2026.

## Um único arquivo de código
`src/orkio_v2/provenance.py`
- AÇÃO: CREATE na branch realmente implantada, **somente se ausente**.
- SHA-256: `cd0bad0a3e4c5951c618d020bc113b368bc0566bf693eba5e74d5672f9294749`
- É consumido por `config.py` e `main.py`.
- Não cria credenciais, não faz bypass de tenant, role ou auth, não altera DB e não faz migrations.

## Como aplicar
1. Na branch de revisão do repositório **Mentoria backend** que o Railway constrói, confira `src/orkio_v2/provenance.py`.
2. Se ausente, copie somente o arquivo desse ZIP para o caminho exato. Não copie a pasta `src` como uma subpasta extra.
3. Se o arquivo já existir nessa branch, compare o SHA; **não substitua se diferir**. Verifique branch/commit e `.dockerignore`.
4. Confira o diff e commit de forma controlada, sem modificar outras camadas.
5. Em Railway STAGING, confirme que o serviço aponta para esse commit e execute novo build, com as flags da mentoria inativas.

## Verificação
- AST Python: PASS.
- SHA-256 igual à baseline staging: PASS.
- Smoke tests isolados de normalização SHA, precedência do SHA, fallback ferroviário,
  ausência de SHA e payload: **7 PASS**.
- Build Docker no Railway após este patch: **NÃO EXECUTADO**.
- Import de todo o app após patch: **NÃO PROVADO** — outras ausências podem aparecer.

Com checkout local:
```bash
python -m py_compile src/orkio_v2/provenance.py
PYTHONPATH=src python -c 'from orkio_v2.provenance import resolve_build_provenance, runtime_provenance_payload; print("PROVENANCE_IMPORT_OK")'
```

## Rollback
Remover somente `src/orkio_v2/provenance.py` no commit de correção, caso ele tenha sido criado.
Reverter o commit específico sem tocar em dados, migrations ou secrets.

## Próximo gate / AO-01
Observar `DIAG_PLATFORM_APP_IMPORT_OK` no novo log. Se a importação ainda falhar, ler a **primeira exceção nova**.
Restaurar o Dockerfile de diagnóstico para a versão original somente após aprovar o import e verificar o diff.
`GIT_HEAD_MENTORIA=NOT_PROVEN`; `RAILWAY_RUNTIME=NOT_PROVEN`; `PRODUCTION=NO_GO`.
