# DG-01 | EFATÀ 777 — Mentoria M1-AI Comercial

**Data:** 2026-11-07  
**Estado:** `SOURCE_PROPOSAL_ONLY` — sem integração Git, sem Railway, sem tráfego público.  
**Baseline pai:** `EFATA777_MENTORIA_GIT_CANDIDATE_20261105.zip`  
**SHA256 pai:** `088714a3603f64d1648917c346e68d0dd0cfb0a8ce2917ce74885e79d11c8dfe`.

## Objetivo e primeira divergência

Reaproveitar os padrões de interface e as regras comerciais do assistente PatroAI
sem usar o dashboard Staff, dados de handoff, credenciais administrativas ou billing.
O frontend de mentoria M0/M1 tinha somente landing + formulário: faltava
o canal de dúvidas comerciais assistido por IA com catálogo versionado.

`ROOT_CAUSE=NÃO_PROVADA` para qualquer incidente de produção. Trata-se
de capacidade nova; nenhuma correção de runtime foi declarada.

## Desenho implementado

- **Frontend:** componente React `MentoriaAssistant.tsx` independente, estilização isolada,
  CTA apenas para o formulário workshop M1; perguntas em memória temporária;
  rótulo explícito de IA, consentimento antes do envio, sem cookies/tokens.
- **API:** POST `/api/v2/public/mentoria/assistant`, entrada rigorosa
  `{message: 3..500, ai_processing_acknowledged: true,
  no_sensitive_data_acknowledged: true}`, resposta
  `{reply: str, source: "catalog"|"ai", catalog_version: str}`.
  Não recebe tenant, role, pagamento, matrícula, histórico ou identidade.
- **Catálogo:** versão `mentoria-2026-11-v1`. Respostas oficiais para
  preço, parcelas, datas, vagas, formato, garantias e inscrição são
  *determinísticas* e não consultam IA externa.
- **IA:** adaptador opcional Responses API, host fixo
  `https://api.openai.com/v1/responses`, `store:false`, 220 tokens
  máximos de saída, sem ferramentas, resposta limitada e verificada;
  outputs contendo links/preços ou falsa confirmação são recusados.
  Perguntas não são persistidas pela aplicação; o tratamento do
  provedor externo depende da respectiva política/contrato.
- **Segurança:** feature flags independentes, key server-side,
  modelo allowlisted, origem obrigatória em staging/produção,
  JSON/body <=2048 bytes, 6 requisições/10min/IP e 200/dia globais,
  Redis fail-closed em staging/prod; até 3 chamadas simultâneas por processo.
  Limites globais de gastos em conta/provider e antiabuso adicional ainda
  exigem validação operacional; a proteção global pressupõe Redis comum
  entre instâncias.
- **Consentimento:** específico para processamento da pergunta;
  cadastro no workshop mantém consentimentos de privacidade e marketing
  separados em M1. Este chat não armazena leads nem efetua inscrição.

## Variáveis (não ativar automaticamente)

Servidor (todas desligadas por padrão, exceto a configuração de ambiente pré-existente):
```ini
MENTORIA_ASSISTANT_ENABLED=false
MENTORIA_ASSISTANT_MODEL=gpt-4.1-mini
MENTORIA_ASSISTANT_CATALOG_VERSION=mentoria-2026-11-v1
# OPENAI_API_KEY=<somente servidor, nunca Git>
# MENTORIA_OWNER_TENANT_ID=<tenant do backend, não browser>
# MENTORIA_PRIVACY_NOTICE_URL=https://.../privacidade
# MENTORIA_RATE_LIMIT_SECRET=<chave segura de 32+ chars> 
# PLATFORM_ALLOWED_ORIGINS=https://dominio-aprovado...
# REDIS_URL=<backend externo de rate limit>
```
Frontend (desligado por padrão):
```ini
VITE_MENTORIA_ASSISTANT_ENABLED=false
VITE_MENTORIA_PRIVACY_URL=https://.../privacidade
VITE_API_BASE_URL=<URL pública do backend aprovada>
```
Para ligar o chat em staging é necessário realizar análise formal de
privacidade, políticas do provedor, DNS/CORS, custos e segurança. Desligar
qualquer flag do backend impede as chamadas, mesmo com UI ativa.

## Testes executados nesta sessão

- `python -m pytest -q --tb=short tests/test_mentoria_m1ai_assistant.py
  tests/test_mentoria_workshop_registration.py tests/test_mentoria_m2_domain_contracts.py
  tests/test_mentoria_m2b_schema.py tests/test_mentoria_m2b_postgres.py
  tests/test_mentoria_pg_gate.py`
  → **134 PASS, 7 SKIP** (PostgreSQL descartável não disponibilizado).
- `node --test tests/mentoria-m0.test.mjs tests/mentoria-m1.test.mjs
  tests/mentoria-m1ai.test.mjs` → **12 PASS**.
- Parser TypeScript global de dois componentes TSX → **0 erros sintáticos**.
- `python -m compileall -q ...` → **PASS**.
- Não executados: typecheck/build real Node20.20.2, E2E browser,
  Redis/LLM real, PG7, Git HEAD, Railway/runtime.

## Invariantes / riscos

- LLM não pode criar cobrança, desconto, matrícula, sessão, permissões,
  movimentação de dados ou oferecer links externos.
- O filtro de saída não substitui red team, catálogo estruturado,
  avaliação de respostas e monitoramento financeiro do provedor.
  Uso público permanece NO-GO.
- PII minimizada por instrução e bloqueios conhecidos, mas detecção
  heurística não garante anonimização; política de dados precisa ser aprovada.
- Exige teste de concorrência e quotas distribuídas antes da abertura.
- Divergências criptográficas nos ZIPs comerciais de referência continuam
  registradas; nenhum deles foi copiado para este pacote.

## Rollback

Antes de branch Git: descartar este delta. Após aplicação local supervisionada:
desligar as duas flags, restaurar os 5 arquivos REPLACE a partir do
manifesto pai, apagar exclusivamente os 6 novos arquivos M1-AI.
**Sem migration, pagamentos, dados ou alteração de tenant a reverter.**
Nunca usar `git clean -fd` como rollback geral.

## Gate e AO-01

`NEXT_GATE=OFFICIAL_HEAD_RECONCILIATION + NODE20_BUILD + SECURITY_REVIEW`.
Documento preparado para compor o pacote final; aprovação formal pelo
AO-01 fica para a consolidação, mantendo NO-GO para produção.
