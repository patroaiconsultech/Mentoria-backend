# Matriz de liberação — Efata 777 / Josué / Cedar
| Gate | Base documental disponível | Situação |
| --- | --- | --- |
| Source staging | Captura Railway vinculando deployment `ed21ec6b-...` a `f433606...` | Revalidar SHA/deployment ativo |
| Segregação | staging `postgres-efata-recovery` / volume `postgres-volume-q5Co`; produção `Postgres` / volume `postgres-volume` | Estrutura distinta; aprovação AO-01 pendente |
| Principal/tenant | Josué / slug `orkio` confirmado como candidato no código | Sessão administrativa/tenant não comprovados |
| Origem segura | Chrome exibiu `Perigoso` em frontend staging e Premium | Não liberada; não autenticar/usar microfone |
| Concorrência | `PUT` desativa assignment anterior; GET não é mutex | Exclusividade formal ou patch transacional separado |
| Preview financeiro | Limite de US$ 1 apenas proposto | Controle financeiro real não implementado/aprovado |
| GO escrita | AO-01: NO-GO | Bloqueio mantido |
| Áudio real | Não testado | NÃO_PROVADO |

**Sequência posterior ao GO externo (não executar agora):**
confirmar principal/tenant e snapshot, obter exclusividade, criar entrada
`REVIEW_REQUIRED`, preview único pago com custo efetivamente controlado,
aprovação humana do áudio, curadoria `APPROVED`, atribuição `DRAFT`,
validação `VALIDATED`, ativação `ACTIVE`, capability e smoke WebRTC+TTS.
Nunca escrever com base somente em indicadores visuais ou flags locais.

**Falha ambígua:** preservar journal, `RECONCILIATION_REQUIRED`, GET seguro;
não repetir POST/PUT nem rollback automático. Provenance de modalidade não
é plenamente recuperável pelo GET atual.
