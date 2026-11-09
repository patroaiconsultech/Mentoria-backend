# Pacote consolidado M0 → M2-B + M1-AI (2026-11-07)

**SOURCE_PROPOSAL_ONLY — não instalado em GitHub/Railway.**
Base = pacote Git de 2026-11-05, SHA256 `088714a3603f64d1648917c346e68d0dd0cfb0a8ce2917ce74885e79d11c8dfe`.
Adiciona M1-AI com **6 CREATE + 5 REPLACE**, total **43 caminhos de código**
(32 backend + 11 frontend).
`manifest.json` guarda os SHA anteriores ORIGINAIS de staging para cada caminho
do pacote acumulado (e não os SHA do delta incremental).
`official_head_sha` permanece NULL: reconciliação com HEAD real OBRIGATÓRIA.
`tools/apply_git_package.py` é apenas instrumento local; **não atômico
para os múltiplos arquivos**. Nunca execute sem revisão, backups e
ambiente controlado. Não execute `--apply` no main ou sem aprovação.

**Novo:** leia `docs/M1AI_DESENVOLVIMENTO_E_EVIDENCIAS.md`.
**Histórico:** `README.md` e docs originais preservados, mas seus
números de arquivos/testes referem-se ao candidato anterior.

Sem migration extra; flags do assistente OFF. Não há R2 admin, checkout,
matrícula, portal de vídeos ou Zoho implementados neste incremento.

Próximos gates: fixar HEAD oficial e executar conferência criptográfica
somente leitura, Node20 + build, PG7, CI e testes de segurança/privacidade
do assistente; M2-C/M3/M4 ainda dependem de desenvolvimento.
