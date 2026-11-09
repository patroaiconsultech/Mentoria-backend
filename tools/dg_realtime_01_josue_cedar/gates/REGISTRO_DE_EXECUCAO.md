# Diário de execução e evidências — modelo não preenchido

- Identificação da mudança/GO AO-01:
- Hash do ZIP e hash do executável liberado:
- Deployment ativo e SHA do backend staging na janela:
- Principal/tenant confirmados (evidência sanitizada, IDs em cofre restrito):
- Isolamento e volume IDs confirmados:
- Origem administrativa liberada, data e prova:
- Exclusividade (pessoas envolvidas, início/fim, aceite de risco TOCTOU):
- Teto efetivo de custo aprovado / mecanismo de controle:
- Estado prévio do catálogo e das atribuições:
- Caminho seguro do journal local e backup (não anexar credenciais):
- `operation_id`, `catalog_id`, `assignment_id` (registrar em evidência restrita):
- Resultado de cada etapa (HTTP, code, correlation_id), sem tokens:
- Reprodução MP3 auditada e aceite humano:
- Capability após ativação (tenant/binding_source/mode):
- Realtime sessão, entrada, transcrição, TTS e reprodução (somente após liberação da origem):
- Ações de rollback e estados reconciliados:
- GO/NO-GO final AO-01:

Em caso de resposta perdida, `RECONCILIATION_REQUIRED`: parar e documentar; não repetir POST/PUT e não executar rollback automático ambíguo.
