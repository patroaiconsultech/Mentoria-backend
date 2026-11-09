# DG-01 — Mentoria M1-AI | Correções preventivas AO-01
**Data:** 2026-11-07  
**Estado:** `SOURCE_PROPOSAL_ONLY` · `AI_ACTIVATION=NO_GO`  
**Escopo:** somente `backend/src/orkio_v2/mentoria/assistant_routes.py` e `backend/tests/test_mentoria_m1ai_assistant.py`.

## Evidência original
Revisão AO-01 informou duas divergências presentes no pacote M1-AI:
1. `openai_api_key`/modelo verificados antes das respostas determinísticas.
2. `asyncio.wait_for(asyncio.to_thread(...))` liberava semáforo após timeout da requisição,
   antes de o worker bloqueante necessariamente terminar.

Os dois pontos foram reproduzidos em leitura do fonte ORIGINAL do ZIP de 2026-11-07.
`ROOT_CAUSE=PROVADA_EM_CÓDIGO` para os dois riscos locais; sem incidente de produção provado.

## Patch mínimo causal
- **Catálogo:** mantém feature flag, validação do tenant proprietário, URL HTTPS de privacidade,
  versão do catálogo, avisos de consentimento e perguntas válidas. Respostas `authorized_reply`
  acontecem antes da verificação de configuração exclusiva do provedor. Perguntas gerais
  continuam `503 MENTORIA_ASSISTANT_CONFIGURATION_MISSING` sem chave/modelo permitido.
  Nenhum segredo sai do servidor.
- **Timeout/concorrência:** limita a três chamadas externas simultâneas *por processo*.
  Após adquirir capacidade, cria task com `asyncio.to_thread` e callback de término.
  Usa `asyncio.shield` ao aguardar timeout de resposta. A capacidade **só é devolvida
  quando a task termina**, mesmo se a resposta HTTP expirar ou a requisição for cancelada.
  Exceções tardias são consumidas, sem registrar conteúdo potencialmente sensível.
  Se workers travarem, limite fecha e a API retorna 503 (fail-closed).

## Paths entregues
- `backend/src/orkio_v2/mentoria/assistant_routes.py` — AÇÃO: REPLACE;
  motivo: catálogo independente de configuração externa + ciclo de vida correto da concorrência.
- `backend/tests/test_mentoria_m1ai_assistant.py` — AÇÃO: REPLACE;
  motivo: testes negativos de falta de chave/modelo, timeout com três workers bloqueados
  e cancelamento da requisição.

## Testes executados em workspace local montado dos ZIPs de staging + candidato
Ambiente do ensaio: Python 3.13.5; sem chaves reais.
Comando focal:
`PYTHONPATH=src python -m pytest -q tests/test_mentoria_m1ai_assistant.py`
**41 PASS**, 2 avisos de depreciação.

Comando regressivo:
`PYTHONPATH=src python -m pytest -q --disable-warnings tests/test_mentoria_m1ai_assistant.py tests/test_mentoria_workshop_registration.py tests/test_mentoria_m2_domain_contracts.py tests/test_mentoria_m2b_schema.py tests/test_mentoria_pg_gate.py tests/test_mentoria_migration.py`
**141 PASS**, 2 avisos.
Teste de banco PG:
`PYTHONPATH=src python -m pytest -q tests/test_mentoria_m2b_postgres.py`
**7 SKIP** (nenhum PG descartável configurado).
Resultados locais não provam staging, Railway, concorrência entre múltiplos workers,
limite Redis compartilhado, autenticação de webhook nem integração externa real.

## Riscos residuais
- O semáforo é por processo; multiplos workers/instâncias exigem orçamento e admissão
  distribuídos para uma garantia global de concorrência. Existe rate limit diário externo
  na camada de middleware, **não homologado aqui com Redis real**.
- Um worker de rede bloqueado indefinidamente mantém sua capacidade ocupada
  até o término. Isso é preferível a novos disparos fora do limite, mas precisa observabilidade.
- O filtro textual de respostas do modelo não constitui prova completa de segurança factual.
- Verificação de HEAD oficial, Node 20 frontend build, PostgreSQL e runtime continuam pendentes.

## Rollback
Antes de Git/deploy: descartar este delta e usar as pré-imagens do M1-AI.
Depois de integração autorizada: desligar `MENTORIA_ASSISTANT_ENABLED` e restaurar
exatamente os dois arquivos de pré-imagem, sem alterar migrations e dados.
Os hashes das pré-imagens constam de `manifest.json`.

## Próximo gate
`AO01_PREVENTIVE_CODE_RECHECK`, depois consolidação final de módulos;
`GIT_APPLICATION=NO_GO`; `AI_ACTIVATION=NO_GO`;
`MIGRATION_OP=NO_GO`; `RAILWAY=NO_GO`; `PRODUCTION=NO_GO`.
