# Critérios de liberação — AO-01

Estado inicial de TODOS os gates: NO-GO.

| Gate | Prova exigida | Se faltar |
| --- | --- | --- |
| Source/deployment | ID de deployment e SHA atuais, diff/guards conservados | STOP |
| Isolamento | produção `Postgres/postgres-volume`; staging `postgres-efata-recovery/postgres-volume-q5Co`; verificar IDs e resolved config, além de qualquer ponte externa | STOP |
| Identidade | `/api/v2/me` e catálogo de agentes em sessão **legítima e origem liberada**; tenant efetivo igual ao esperado, Josué `orkio` | STOP |
| Origem administrativa | classificação de Chrome/Safe Browsing investigada e liberação documentada do host usado na autenticação; não usar domínio sinalizado | STOP |
| Exclusividade | janela assinada, administradores alinhados e GET imediatamente antes do PUT | STOP |
| Custos | limite de US$ 1 oficialmente aprovado **e aplicável**, consumo real monitorado; flags não impõem limite | STOP |
| AO-01 | GO explícito para versão executável e desarme da trava | STOP |
| Verificação funcional | voz atribuída e capability elegível, sem interpretar indicador como áudio real | NÃO DECLARAR PASS_RUNTIME |

Não são provas: `--ao01-go`, `--security-cleared`, um JSON alterado pelo operador, o nome do banco, nem um HTTP 200 isolado.

Nenhuma origem com alerta “Perigoso” pode receber credenciais administrativas/microfone sem triagem e liberação específica.
