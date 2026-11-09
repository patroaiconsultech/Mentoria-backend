# HANDOFF AO-01 — DG-REALTIME-01 | pacote de implantação condicionada

**Target**: staging-web01 / Josué `orkio` / OpenAI `cedar` / `pt-BR`.  
**Release**: P0.2 preservada + documentação e checks adicionais; **não é P0.3 executável**.
**GO solicitado**: conferência do pacote e dos critérios; **não solicitar GO para escrita com as evidências atuais**.

## Evidência reproduzida nesta entrega
- `node --check`: PASS_LOCAL
- `node ... --plan`: PASS_LOCAL
- `node --test`: 28 PASS_LOCAL / 0 FAIL
- Manifesto SHA256: checks internos automatizados PASS.
- `node scripts/check_gates.mjs`: código 2 e GATE_CHECK=NO_GO, conforme esperado.
- Nenhuma chamada à staging, ao provedor, login ou áudio.

## Causa e patch
- Bloqueio operacional no banco consultado: TTS habilitado, catálogo de vozes e atribuições vazios, bindings legados 0.
- P0.2 implementa write-ahead intent, reconciliação read-only e bloqueio em resposta perdida — aceito AO-01 em 28/28 testes.
- Nenhuma alteração do backend necessária para a condição inicial.
- `P03_WRITE_UNLOCK_REVIEW_ONLY.diff` propõe **apenas** desarmar trava de execução; **não aplicado**. Requer revisão independente antes de sequer ser considerado. Flags de CLI não substituem provas independentes.

## Itens bloqueadores ainda NÃO comprovados
1. Segurança da origem administrativa (Chrome sinaliza "Perigoso"). Nenhum OTP/credencial/microfone nessa origem.
2. Principal administrativo e tenant de staging; associação com Josué/orkio em sessão legítima.
3. Identidade efetiva das instâncias/volumes e ausência de DSN externo compartilhado; capturas de serviços distintos são boa evidência parcial.
4. Exclusividade operacional para mitigar janela não atômica GET→PUT; se não houver garantia, deve-se alterar backend por proposta separada com testes PostgreSQL.
5. Custo de preview: `--budget-usd 1` é confirmação e não controle financeiro real. Precisa teto efetivo e aprovação.
6. Testes de integração em staging e áudio real E2E ainda não executados.

## Risco adicional de rollback
- Catálogo global e atribuições tenant-scoped. Endpoint de desativação de catálogo tem guard de `VOICE_CATALOG_ENTRY_IN_USE`, mas rechecagem e journal ainda são exigidos. Não desativar catálogo de uso desconhecido.
- Falha de comunicação não autoriza retry automático nem rollback presumido.

## Arquivos chave
- `josue_cedar_activation.mjs` — P0.2 inalterada, lock `false`
- `tests/activation.test.mjs` — 28 testes
- `RUNBOOK_IMPLANTACAO.md`, `CONTRATOS_E_PROVENANCE.md`
- `gates/EXCLUSIVIDADE_ADMINISTRATIVA.md`, `gates/CRITERIOS_GO_NO_GO.md`, `gates/REGISTRO_DE_EXECUCAO.md`
- `P03_WRITE_UNLOCK_REVIEW_ONLY.diff` — review-only
- `ROLLBACK_E_RECUPERACAO.md`, `SHA256SUMS.txt`

## Resultado do gate
```
PACKAGE_DELIVERY=READY_FOR_REVIEW
AO01_P02_LOCAL_TESTS=28_PASS
REMOTE_WRITES_ENABLED=FALSE
STAGING_WRITE=NO_GO
PREVIEW_PAID=NO_GO
MICROPHONE_SMOKE=NO_GO
PRODUCTION_CHANGE=NO_GO
ROOT_CAUSE_AUDIO_END_TO_END=NOT_PROVEN
```
