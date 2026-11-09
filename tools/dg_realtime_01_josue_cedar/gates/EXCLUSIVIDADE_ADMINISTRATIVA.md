# Janela de exclusividade administrativa — staging Josué/Cedar

**Estado: NÃO ASSINADO / NO-GO.** Este documento é uma proposta de controle operacional, não um mutex atômico.

- Alvo: serviço `efata-777-backend-staging-web01`, ambiente `staging-web01`; tenant e principal devem ser confirmados por sessão legítima.
- Operador responsável: _____________________
- Auditor AO-01: _____________________
- Janela UTC início/fim: _____________________
- Outros administradores e automações responsáveis por voz informados e com modificações suspensas: [ ] comprovado
- Inspeção independente de mudanças concorrentes durante a janela: [ ] comprovado
- Antes de PUT: GET de atribuições do tenant + GET do catálogo; abortar diante de qualquer conflito, ambiguidade ou mudança.
- Após PUT: reler atribuição por ID conhecido, registrar versão/estado e timestamps, não executar repetição automática.
- Limite do controle: o GET→PUT **não é atômico**; exclusividade declarada não impede escritor não cooperante. Se não for possível assegurar a janela, **NO-GO** até patch backend transacional/condicional aprovado com testes PostgreSQL.
- Nenhuma escrita enquanto AO-01 mantiver NO-GO.
- Assinaturas operador/AO-01: _____________________ / _____________________

Risco residual aceito (apenas após GO independente): _____________________
