# DG-REALTIME-01 — P0.3 preparação (não executável para escrita)
Data: 2026-10-28. Destino exclusivamente `staging-web01`, Josué (`orkio`), Cedar.

Este pacote preserva **byte a byte** o executável e os 28 testes P0.2 auditados.
`REMOTE_WRITES_ENABLED=false`. Nenhum `--apply`, `--rollback` nem preview
deve ser executado. Não é um deployment Railway nem substitui o backend.

## Nova contribuição P0.3
`scripts/p03_readiness.mjs` verifica os SHA-256 fixados de P0.2, confirma
o bloqueio de escrita e apresenta pendências documentais, sempre retornando
`NO_GO` e código 2. Mesmo marcar todas as flags como `true` não libera a
implantação. Os 6 testes negativos estão em `tests/p03_readiness.test.mjs`.

## Testes seguros no Windows (na pasta extraída)
```powershell
node --check .\josue_cedar_activation.mjs
node --test .\tests\activation.test.mjs
node --test .\tests\p03_readiness.test.mjs
node .\scripts\p03_readiness.mjs
Write-Host "READINESS_EXIT=$LASTEXITCODE"
```
Esperado: P0.2 28 PASS, P0.3 6 PASS, readiness `NO_GO`, código 2.

## Gates que NÃO podem ser substituídos por flags
- Evidência do commit/deployment ativo
- Banco da staging e ausência de compartilhamento indevido
- Principal administrativo + tenant + Josué (`orkio`) via canal seguro
- Triagem e liberação documentadas da origem sinalizada pelo navegador
- Exclusividade de administradores/automação durante GET→PUT
- Limite financeiro real do preview, não apenas `--budget-usd 1`
- Revisão independente AO-01 de qualquer versão que libere escritas

Ver `P03_HANDOFF_AO01.md`.
