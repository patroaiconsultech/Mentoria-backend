# Runbook de implantação condicionada — Josué / Cedar

**Status atual: NO-GO EXECUÇÃO, GO entrega para revisão.** Não é deploy de código ao Railway. A mudança prevista é ativação de **dados governados** na staging após gates.

## 0. Conferência local (sem rede)
No PowerShell, após extrair o ZIP numa pasta local:
```powershell
node .\scripts\verify_local.mjs
node .\scripts\check_gates.mjs
```
Esperado: 28 testes PASS e `GATE_CHECK=NO_GO`. Não copiar informações de login ao pacote.

## 1. Congelar target
Confirmar ambiente `staging-web01`; backend `efata-777-backend-staging-web01`; deployment ativo e SHA `f433606...` ou novo SHA autorizado; banco `postgres-efata-recovery`, volume `postgres-volume-q5Co`, produção `Postgres/postgres-volume`. Comparar IDs concretos e ausência de ligação externa.
Reconfirmar backups/retorno da staging se aplicável, sem tocar em produção.

## 2. Provas e aprovação
Registrar em `gates/REGISTRO_DE_EXECUCAO.md` prova de principal administrativo legítimo e tenant esperado por origem segura. Confirmar `orkio` no catálogo do tenant, sem confiar em browser para role/tenant.
Registrar laudo de triagem e liberação da origem. Receber GO específico AO-01. Aprovar e implementar teto financeiro de preview; um flag `--budget-usd 1` não limita faturamento.
Obter compromisso formal de exclusividade administrativa durante a operação ou parar e propor garantia atômica no backend.
**Não usar nenhum formulário de login nem microfone num domínio marcado “Perigoso”.**

## 3. Versão de execução
A P0.2 entregue contém `REMOTE_WRITES_ENABLED=false`. O diff `P03_WRITE_UNLOCK_REVIEW_ONLY.diff` é uma **proposta não aplicada**, que exige nova auditoria independente.
Até esse GO: **não executar `--apply`, `--rollback`, OTP ou preview pago**. Não editar a trava diretamente por conta própria.

## 4. Sequência pós-GO (não executar ainda)
Com versão executável aprovada, sessão legítima e alvo revisto, preencher tenant esperado apenas na estação local, via leitura autorizada (nunca em mensagens públicas).
Inspecionar catálogo e atribuições; abortar em caso de Cedar duplicada ou atribuição existente.
Gravar journal antes de cada escrita e executar estritamente uma operação de cada vez:
1. POST catálogo Cedar (`REVIEW_REQUIRED`).
2. POST preview TTS único, escutar MP3 e registrar aprovação humana.
3. POST curadoria (`APPROVED`).
4. GET pre-PUT e garantia de exclusividade.
5. PUT atribuição `orkio/pt-BR` (`DRAFT/UNVALIDATED`).
6. POST validação (`VALIDATED`).
7. POST ativação (`ACTIVE`).
8. GET capability: saída elegível, `binding_source=admin_assignment`, segmentos elegíveis.
9. Apenas após liberação de segurança, realizar smoke com áudio real e evidência de entrada/transcrição/resposta/reprodução/limpeza.

Qualquer falha ou estado desconhecido: STOP. Não repetir POST/PUT, não fazer rollback cego.

## 5. Comandos pós-GO — somente referência, NÃO LIBERADOS
A CLI da P0.2 tem `--apply` e `--rollback`, mas **ambos permanecem bloqueados** em código.
O modo `--reconcile` exige acesso autenticado e só é permitido quando origem e identidade foram liberadas; não executar como alternativa para contornar o alerta de navegador.

## 6. Rollback
Seguir `ROLLBACK_E_RECUPERACAO.md` e comprovar cada vínculo antes de desativar. Catálogo global exige cuidado com usos em outros tenants.

## 7. Aceite
`PASS_LOCAL` não significa `PASS_RUNTIME`. Não declarar voz funcional sem áudio recebido, transcrito, sintetizado e reproduzido. GO final é do AO-01 e do operador.
