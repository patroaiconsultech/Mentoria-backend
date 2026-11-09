# DG-REALTIME-01 — Pacote de implantação GATEADA (Josué / Cedar)
Data 2026-10-28 | Target staging-web01 | Estado `PROPOSAL_ONLY / NO-GO ESCRITA`

Este pacote **não realiza deploy** nem ativa voz. É a entrega completa para auditoria de uma futura ativação da voz Cedar de Josué (`orkio`).
Inclui script P0.2 **inalterado e com `REMOTE_WRITES_ENABLED=false`**, testes P0.2, comandos offline, documentação de contratos, comprovantes e decisão de GO/NO-GO.

**Abra `RUNBOOK_IMPLANTACAO.md` primeiro.** Nunca execute um diff de desarme sem revisão AO-01 específica. Nenhum segredo, OTP, cookie, senha, DSN, token ou chave privada deve ser enviado ao auditor.

Comandos seguros de validação local:
```powershell
node .\scripts\verify_local.mjs
node .\scripts\check_gates.mjs
```
A documentação do AO-01 registra **28/28 PASS_LOCAL**. Sem testes remotos, sem áudio real, sem escrita.
Arquivos `gates/*` são modelos; não representam aprovações já obtidas.

Pendente: segurança da origem, identidade/tenant legítimo, isolamento completo, exclusividade para TOCTOU, limite de custos efetivo e aprovação da versão executável pelo AO-01.
