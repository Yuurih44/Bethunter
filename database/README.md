# Modelo de dados

PostgreSQL é o banco da implantação. SQLite em memória existe apenas como opção de teste; não é o banco configurado no Compose.

| Tabela | Função / relacionamentos |
|---|---|
| users | Email único, hash Argon2id, role com constraint |
| sessions | Hash do token, usuário FK/index, CSRF e validade |
| domains | Proprietário FK/index, hostname indexado, origem/data, unicidade proprietário+nome |
| analyses | Domínio FK/index, data indexada, score 0–100, classificação, JSON, revisão |
| indicators | Análise FK/index, tipo e valor observado |
| evidence | Análise FK/index, coleta, SHA-256 e payload |
| official_sources | URL, data de consulta/atualização, estado, erro, hash e empresas/domínios/atos |
| regulatory_rules | Versão única, início/fim de vigência e pesos/justificativa |
| cases | Proprietário FK/index, estado/prioridade com constraints, notas e criação |
| case_domains | Associação N:N com chave composta |
| reports | Caso FK/index, data, snapshot, SHA-256 e bytes PDF |
| complaints | Relatório FK único, estado preparado ou confirmação declarada, protocolo/referência |
| audit_logs | Usuário FK/index, horário, ação e detalhes |
| discovery_feeds | Fonte própria, URL única por usuário, licença/autorização, limites e cursor |
| discovery_runs | Consultas com estado, hash, contagens e erro |
| discovery_candidates | Associação fonte/domínio, primeira/última observação e consulta correspondente |
| analysis_jobs | Fila durável, domínio único, estado, tentativas, erro e análise associada |
| automation_quotas | Cota diária UTC e próximo horário por usuário |
| schedules | Domínio FK único, intervalo validado, próxima execução indexada, estado e último erro |

Os perfis/permissões são representados pelo campo role restrito e dependências de autorização, sem tabelas de permissões editáveis neste MVP. As tabelas não têm exclusão em cascata de evidências/casos; nenhuma API de exclusão é oferecida.

As migrações são DDL congelado gerado pelo Alembic e revisado na criação, não importam modelos mutáveis para alterar o passado. Para evoluir:

```bash
cd backend
alembic revision --autogenerate -m "descricao"
# Revise o arquivo, especialmente operações destrutivas, antes de aplicar.
alembic upgrade head
alembic check
```

Testes recriam o esquema por design; use sempre banco exclusivo. Em produção, faça backup antes de migrações e teste restauração. Hashes não substituem assinatura digital/ancoragem externa. JSON contém metadados heterogêneos e evidências públicas; dados sensíveis de investigação exigem política operacional de proteção.

`schema.sql` é o SQL gerado offline das quatro migrações para o dialeto PostgreSQL. É uma referência; use Alembic para controlar a versão na implantação. A geração desse arquivo não confirma execução em um servidor PostgreSQL.

A migração0004 acrescenta active/MFA ao usuário, atividade e verificação MFA à sessão, marcação de agendamento automático e tabelas invitations, auth_throttles, mfa_enrollments, mfa_recovery_codes, regulatory_notices, system_schedules, workflow_policies e workflow_runs. Os últimos relacionam análise/caso/relatório e mantêm política por proprietário. A atualização preserva contas existentes, com MFA inicialmente desativado.

## Migração 0005

Adiciona email_tokens (hash, finalidade, validade), mail_jobs (payload criptografado e tentativas), report_jobs (snapshot, fingerprint único por caso, status), raw_documents (bytes/hash/origem/proprietário) e security_events. Acrescenta modo de confirmação de email, estado de arquivamento PDF, índice de expiração de sessão e índice composto de análise por domínio/id. Runtime não aplica DDL; app.migrate usa credencial migradora e restringe alterações de evidências/auditoria/documentos.
