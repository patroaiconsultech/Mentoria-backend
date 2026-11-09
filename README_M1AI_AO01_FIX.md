# Correções AO-01 integradas no candidato Git acumulado

- Base: pacote Git M0→M2-B + M1-AI de 2026-11-07,
  SHA-256 `091e4658e0a94afe69b1c08addf94a4207f443594569d79cbc218974fa1a24b3`.
- Dois arquivos completos substituídos:
  `backend/src/orkio_v2/mentoria/assistant_routes.py` e
  `backend/tests/test_mentoria_m1ai_assistant.py`.
- O manifesto **acumulado** mantém os SHA de pré-imagem da base original
  de staging em `old_sha256` e atualiza exclusivamente os `new_sha256`
  dos dois arquivos. São **43 paths** (32 backend + 11 frontend).
- Não há mudanças no frontend, no schema, nas migrations, nos endpoints de billing
  nem na identidade. Flags permanecem desativadas.
- Testes do patch: 41 PASS; regressão selecionada: 141 PASS;
  testes PostgreSQL: 7 SKIP por ausência de ambiente isolado.
- Documento detalhado: `docs/M1AI_AO01_CORRECOES.md`.
- `official_head_sha` backend/frontend continuam `null`: necessário reconciliar
  antes de instalar a branch. Railway e produção continuam NO-GO.

**Não executar automaticamente o importador**: ele não é atomicamente transacional.
Sem prova do HEAD, nenhuma aplicação em repositório oficial está autorizada.
