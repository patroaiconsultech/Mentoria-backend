# EFATÀ 777 — diagnóstico isolado do build STT (09/11/2026)

**Status:** proposta diagnóstica somente para **STAGING**, NÃO é correção comprovada e NÃO está aplicada no GitHub/Railway.

## Evidências
- Deployment informado: `Mentoria-backend`, commit curto `939b1f86`, ambiente mostrado: `production`.
- `Railway Diagnose` informa que o build para no teste de `import faster_whisper`, sem mensagem de erro.
- `provenance.py` consta como corrigido no parecer do Railway; essa afirmação não é verificação independente do HEAD.
- `pip install --require-hashes` concluiu; `ROOT_CAUSE=NÃO_PROVADA`.
- Possíveis mecanismos: exceção, SIGKILL/OOM, falha de builder. Nenhum foi demonstrado.

## Gate de aplicação
1. **Não usar no Railway `production`.** Crie/seleciona ambiente STAGING com build isolado, sem billing/Asaas/migrations; configure branch de investigação com aprovação humana.
2. No repositório de `Mentoria-backend` verifique o SHA-256 de `Dockerfile` atual. Aplique este arquivo **somente se o SHA for** `de24b1539a67ac456403c82039c6308316cd8dfa7e639f3f0f52524c2fd3a005`; caso contrário, faça diff antes de substituir.
3. Substitua o arquivo completo `Dockerfile` na raiz pelo `payload/backend/Dockerfile`. Não envie a pasta `payload` nem o ZIP como conteúdo do repositório.
4. Faça commit em branch de diagnóstico e observe, no novo Build Log, marcadores `DG01_`. Não automatize merge/deploy de produção.

## PATH / AÇÃO / MOTIVO
- **PATH:** `Dockerfile` (raiz do backend)
- **AÇÃO:** REPLACE, condicionada ao SHA preexistente
- **MOTIVO:** acrescentar logs antes/depois de `import faster_whisper` com código de saída e contadores de memória cgroup.

## Detalhes técnicos e interpretação
- `DG01_STT_CHECK_BEGIN` ausente: etapa não chegou a iniciar ou o log não registrou a saída.
- `DG01_PYTHON_RUNNING` presente: interpretador Python iniciou antes da importação.
- `DIAG_FASTER_WHISPER_IMPORT_OK`: importação completou.
- `DG01_STT_IMPORT_EXIT_CODE=1` (ou outro não zero) com traceback: falha do comando; ler a exceção.
- `DG01_STT_IMPORT_EXIT_CODE=137`: processo recebeu SIGKILL; verificar aumento de `oom_kill` em `DG01_CGROUP_AFTER` versus `BEFORE` e outras evidências de recursos. **137 isoladamente não prova OOM**.
- Marcador inicial presente mas código de saída ausente: pode ter sido interrompido o shell/builder ou perdido o log.
- `exit code 0`: etapa STT passou; acompanhar a próxima verificação de `orkio_v2.main`.

O patch mantém `--require-hashes`, os `RUN` seguintes, usuário não root, CMD de origem e saída **não zero** em caso de import com falha. Não contorna gates. O diagnóstico lê apenas métricas não secretas da cgroup.

## Testes locais
`python -m unittest discover -s tests -v`

Os testes verificam sintaxe do bloco shell, comportamento do código de retorno 0 e 37 e retenção dos gates. **Não substituem Docker/Railway nem reproduzem a causa real**.

## Riscos e rollback
- Risco de recompilar grande imagem em STAGING. Não há mutação de banco.
- Rollback: reverter o commit diagnóstico ou restaurar o Dockerfile preexistente (`de24b1539a67ac456403c82039c6308316cd8dfa7e639f3f0f52524c2fd3a005`).
- Depois de identificar a causa, substituir novamente pelo Dockerfile de produção aprovado. AO-01 deve revisar as evidências antes de qualquer promoção.

## Handoff AO-01
`PATCH_SCOPE=Dockerfile.RUN_STT_IMPORT`, `ROOT_CAUSE=NÃO_PROVADA`,
`GIT_WRITE=NO`, `RAILWAY_DEPLOY=NO`, `PRODUCTION=NO_GO`.
