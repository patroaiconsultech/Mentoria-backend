# Rollback / reconciliação

- No preflight, registrar estados anteriores por tenant/agente/locale e do catálogo, sem coletar dados de outro tenant via API.
- Em qualquer erro após POST/PUT com resposta perdida ou timeout, **não repetir**. Journal `RECONCILIATION_REQUIRED`, consulta GET governada e intervenção AO-01.
- Reconciliar ID local conhecido com os objetos remotos; se ID ausente ou objeto desconhecido, **não presumir que é nosso**. Registrar e solicitar revisão manual.
- Rollback autorizado: desativar primeiro atribuição Josué/Cedar, somente com vínculo provado e evidência de estado.
- O catálogo é global; antes de sua desativação, verificar todos os usos de forma autorizada. O backend possui guard `VOICE_CATALOG_ENTRY_IN_USE` mas isso não equivale a transação única distribuída.
- Se outra atribuição passou a usar Cedar, **não desativar o catálogo**. Deixar item para revisão.
- Se o estado remoto divergir do journal, `STOP / NO-GO`; restaurar por processo governado, sem DELETE ou SQL manual.
- Não executar rollback em produção, não trocar DSN, não rodar Alembic.
- O script P0.2 permanece bloqueado para apply/rollback até revisão explícita da versão liberada.
