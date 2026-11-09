# EFATÀ 777 / Mentoria — Diagnóstico temporário do build STAGING

## Evidência
O log Railway etapa [7/9] mostra `Successfully installed`, seguido de exit 1 ao executar um RUN que combina instalação e imports. O traceback Python não aparece no JSON exportado.

## AÇÃO
`Dockerfile`: REPLACE APENAS EM BRANCH DE DIAGNÓSTICO STAGING, após conferir a pré-imagem.
SHA-256 esperado da versão anterior do Dockerfile: `7448f6d602979c478e9925817499d4ec2ee309a4a1b4a40fcecf21297ede30df`.
Não substituir se o Dockerfile no GitHub divergir.

## Modificação
Desmembrar apenas o RUN combinado em três comandos RUN:
- Instalar dependências por lock/hashes.
- Importar `faster_whisper`, imprimindo `DIAG_FASTER_WHISPER_IMPORT_OK`.
- Importar `orkio_v2.main` com DATABASE_URL SQLite e ambiente test, imprimindo `DIAG_PLATFORM_APP_IMPORT_OK`.

Permanecem intactos: imagem base, PYTHONPATH, dependências pinadas, usuário não-root, porta, CMD, sem migrations. **Sem bypass de build**.

## Interpretação
- Falha antes de `DIAG_FASTER_WHISPER_IMPORT_OK`: localizar erro de import nativo/STT no Build Log.
- Marcador STT presente e falha antes de `DIAG_PLATFORM_APP_IMPORT_OK`: localizar import/configuração da aplicação no Build Log.
- Os dois marcadores presentes: analisar a primeira falha subsequente.

Não imprimir variáveis, tokens ou dados sensíveis. Não ativar billing, migrações ou matrícula.

## Teste/limite
Verificação estática: uma única substituição e todo o restante do Dockerfile preservado. Nenhum Docker build executado neste ambiente.

## ROLLBACK
Restaurar o Dockerfile original a partir do commit anterior. Sem mudança em banco, Railway variables ou dados.

GATE=STAGING_DIAGNOSTICO | ROOT_CAUSE=NÃO_PROVADA | PRODUCTION=NO_GO.
