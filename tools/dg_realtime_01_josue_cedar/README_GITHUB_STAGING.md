# DG-REALTIME-01 — Josué/Cedar | Ferramenta auditável para GitHub staging

**Target exclusivo:** `patroaiconsultech/efata-777-backend-staging-web01`, ambiente `staging-web01`.
**Agente:** Josué (`orkio`). **Provedor/voz:** OpenAI `cedar`. **Modelo:** `gpt-4o-mini-tts`. **Locale:** `pt-BR`.

## O que este diretório faz

- Preserva **byte a byte** os 22 arquivos do pacote P0.3 usado na validação de 34 testes.
- Publica scripts de **preflight offline e testes** versionados com o backend para auditoria.
- Mantém o P0.2 intencionalmente travado: `REMOTE_WRITES_ENABLED=false`.
- **Não altera** `src/`, `app/`, `migrations/`, `Dockerfile`, `railway.json` ou dados.
- Não usa secrets nem executa chamadas administrativas na CI.
- O arquivo `P03_WRITE_UNLOCK_REVIEW_ONLY.diff` é uma proposta histórica **não aprovada**, não aplicada.

## O que NÃO faz

Este commit **não cadastra Cedar**, não cria `agent_voice_assignments`, não muda Railway,
não libera o Chrome sinalizado, não executa preview pago e não realiza chamada de microfone.
A ausência da atribuição é uma questão de estado de banco/API administrativa,
que só poderá ser alterada mediante autorização AO-01 específica.

## Validação local (a partir deste diretório)

```bash
node scripts/verify_local.mjs
node --test tests/p03_readiness.test.mjs
node scripts/p03_readiness.mjs
```

As duas primeiras etapas precisam terminar com código 0; a última precisa retornar
**código 2, `execution=NO_GO`**. Não mascare esse `NO_GO` como um GO de runtime.

## Regras de aplicação

1. Criar branch a partir do HEAD pinado em staging `f43360621e8036cf8f96485e577a2a193c2baa43`.
2. Aplicar o delta pela ferramenta `APLICAR_NO_REPO.ps1` do ZIP externo.
3. Rodar a CI `05-josue-cedar-offline.yml` e abrir PR para revisão AO-01.
4. Não fazer merge/deploy até aprovação dos gates próprios de Git/Railway.
5. Mesmo após merge, somente uma **operação administrativa separadamente aprovada**
   poderá ativar a voz no tenant certo. Sem bypass nem SQL manual.

## Estado em 28/10/2026

- 34/34 testes offline passaram no Windows do operador (informado) e na preparação original.
- Runtime commit informado e reconfirmado pelo operador: `f433606...`;
  deployment informado: `ed21ec6b-aa2f-4550-8376-f9947d0421f8`.
- Conversa consultada: fingerprint do tenant `b6c09cbcbf25`, sem atribuições,
  **reportado pelo operador; não prova identidade administrativa**.
- Google Safe Browsing marcou frontend staging com suspeita de conteúdo enganoso.
- AO-01: **NO-GO para escrita, preview pago, microfone e produção**.

**Rollback de código:** fechar PR ou reverter somente os arquivos sob
`tools/dg_realtime_01_josue_cedar/` e `.github/workflows/05-josue-cedar-offline.yml`.
Sem migration, sem rollback de banco neste pacote.
