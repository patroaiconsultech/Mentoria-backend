# Contratos e provenance

Backend alvo: `patroaiconsultech/efata-777-backend-staging-web01`
Deployment observado em captura: `ed21ec6b-aa2f-4550-8376-f9947d0421f8`
Source commit ligado por navegação do Railway: `f43360621e8036cf8f96485e577a2a193c2baa43`.
**Revalidar deployment ativo antes de qualquer intervenção.** Os bytes efetivos em runtime não foram atestados independentemente.

Arquivos no GitHub no commit:
- `src/orkio_v2/routes.py`: https://github.com/patroaiconsultech/efata-777-backend-staging-web01/blob/f43360621e8036cf8f96485e577a2a193c2baa43/src/orkio_v2/routes.py
- `src/orkio_v2/voice_routes.py`: https://github.com/patroaiconsultech/efata-777-backend-staging-web01/blob/f43360621e8036cf8f96485e577a2a193c2baa43/src/orkio_v2/voice_routes.py
- `src/orkio_v2/auth_routes.py`: https://github.com/patroaiconsultech/efata-777-backend-staging-web01/blob/f43360621e8036cf8f96485e577a2a193c2baa43/src/orkio_v2/auth_routes.py

Contratos examinados no snapshot ZIP anterior, também localizados por caminho no commit GitHub. Exigir reconfirmação com testes de contrato contra deploy antes de GO:
- `POST /api/v2/auth/admin/otp/start` e `/verify` — autenticação legítima.
- `GET /api/v2/me`, `GET /api/v2/admin/agents` — identificar principal, tenant, agente.
- `GET/POST /api/v2/admin/voice-catalog`; `POST .../{voice_id}/preview`, `.../curation`, `.../deactivation`.
- `GET /api/v2/admin/agent-voice-assignments`.
- `PUT /api/v2/admin/agents/{agent_slug}/voice-assignment` — **pode desativar atribuição anterior**. Janela GET→PUT não atômica.
- `POST /api/v2/admin/agent-voice-assignments/{assignment_id}/validation`, `.../activation`, `.../deactivation`.
- `GET /api/v2/realtime/capabilities` — elegibilidade tenant; não prova áudio por agente nem runtime.
- `GET` de atribuições retorna metadados e versão, mas **não retorna `delivery_modes`**. Reconciliação nunca deve presumir modalidade com base nesse GET.

Revalidação e a ausência de mudanças posteriores na branch são pendências.
