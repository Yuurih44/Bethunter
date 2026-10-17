# Evolução e validações futuras

Implementados e exercitados: autenticação/MFA/convites, email local e recuperação, descoberta com filas/cotas, casos/PDF, diagnóstico, notificações/checklist, paginação principal, papéis PostgreSQL, backup/restore e retenção opcional. PostgreSQL, navegador e Docker/CI passaram conforme VALIDATION.md.

Ainda pendentes:

- SMTP de entrega externa e HTTPS público com domínio próprio; avaliação de produção, carga e recuperação de desastre em armazenamento externo.
- Ampliar formatos oficiais e revisão jurídica de vigência/escopo; avaliar precisão com dados rotulados.
- CT, RDAP, DNS passivo histórico e detecção de imitação de marca.
- Casos colaborativos, gestão mais ampla de perfis e auditoria assinada/WORM.
- Rate limiting compartilhado, múltiplas réplicas e paginação dos endpoints legados.
- Backup em streaming para bases maiores.

Não há envio automático de denúncias. Resultados de teste não certificam legalidade ou ausência de falhas.
