# Evolução e validações pendentes

Implementados: autenticação/MFA/convites, confirmação e recuperação por email, descoberta em fontes permitidas com fila/cotas, casos/PDF, diagnóstico, notificações e checklist, paginação principal, papéis PostgreSQL separados, backups criptografados e retenção opcional.

Ainda pendentes:

- Validar implantação real em PostgreSQL/Compose/navegador, upgrade/restauração e SMTP/TLS; executar auditorias de dependências com rede.
- Ampliar formatos de fontes oficiais e revisão jurídica de vigência/escopo; avaliar precisão com dados rotulados.
- Integrações CT, RDAP e DNS passivo histórico; detecção de imitação de marca.
- Casos colaborativos, gestão mais ampla de perfis e armazenamento externo de auditoria assinada/WORM.
- Rate limiting compartilhado, múltiplas réplicas, validação de carga e paginação dos endpoints legados.
- Backup em streaming para bases maiores e recuperação de desastre com armazenamento externo.

Nenhum item pendente é apresentado como validado. Não há envio automático de denúncias. Veja REVIEW.md e VERIFICATION.md.
