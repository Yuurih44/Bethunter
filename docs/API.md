> Atualização: a implementação posterior adicionou SMTP/verificação/recuperação, papéis PostgreSQL separados, backups, paginação e fila PDF. Consulte [OPERATIONS.md](OPERATIONS.md) para o comportamento atual e [VERIFICATION.md](VERIFICATION.md) para validações e pendências. As observações históricas abaixo não substituem esses documentos.

# API BetHunter

Swagger em `/api/docs`, OpenAPI em `/api/openapi.json`. JSON UTF-8. Erros FastAPI usam `detail`; 401 sem sessão válida, 403 origem/CSRF/perfil inválido, 404 registro ausente ou de outro proprietário, 409 conflito, 422 entrada inválida, 429 limite e 504 coleta excedida.

## Sessão

```bash
curl -i -c cookies.txt http://localhost:8080/api/auth/register \
  -H 'Origin: http://localhost:8080' -H 'Content-Type: application/json' \
  --data '{"email":"analista@exemplo.com","password":"substitua-por-senha-longa"}'
```

A resposta contém `id`, `email`, `role` e `csrf`. Guarde o cookie e use o csrf recebido nas mutações. Não coloque senhas reais no histórico de shell em operação; o exemplo é documental. A interface evita essa necessidade.

```bash
curl -b cookies.txt http://localhost:8080/api/domains \
  -H 'Origin: http://localhost:8080' -H 'Content-Type: application/json' \
  -H 'X-CSRF-Token: SUBSTITUA_PELO_TOKEN_RECEBIDO' \
  --data '{"value":"example.org"}'
```

## Rotas

| Método | Rota | Finalidade |
|---|---|---|
| GET | /api/health | Conexão básica com banco |
| POST | /api/auth/register | Cadastro de analista e sessão |
| POST | /api/auth/login | Nova sessão |
| GET | /api/auth/me | Usuário e CSRF da sessão atual |
| POST | /api/auth/logout | Revogação e remoção do cookie |
| GET / POST | /api/domains | Listar até 1.000 / cadastrar domínio |
| POST | /api/domains/{id}/analyze | Coleta pública limitada e persistência |
| GET | /api/analyses | Até 1.000 análises mais recentes |
| PATCH | /api/analyses/{id}/review | Parecer humano: {review} |
| GET | /api/dashboard | Métricas reais de todo o inventário próprio |
| GET / POST | /api/cases | Listar / abrir casos |
| PUT | /api/cases/{id} | Substituir título, notas, estado, prioridade e domínios |
| POST | /api/cases/{id}/reports | 202: enfileira snapshot; retorna job_id/status/report_id; worker prepara PDF |
| GET | /api/reports | Metadados e situação informada |
| GET | /api/reports/{id}/pdf | Bytes PDF preservados |
| POST | /api/reports/{id}/confirmation | Declaração humana de protocolo recebido |
| POST | /api/discovery/import | Importar {csv: "domain\n..."} |
| GET | /api/intelligence/graph | Nós e relações observadas, até 2.000 indicadores |
| POST | /api/blocklists | {domain_ids:[1],format:"hosts" ou "adblock" ou "domains"} |
| GET | /api/schedules | Estado dos agendamentos próprios |
| POST | /api/schedules | Criar/alterar {domain_id,interval_hours,enabled} |
| GET | /api/sources | Últimas 30 consultas oficiais e registros importados |
| POST | /api/sources/sync | Consultar fonte oficial (admin) |
| GET | /api/rules | Regras versionadas |
| POST | /api/rules | Nova versão (admin) |
| GET | /api/audit | Últimos 500 eventos próprios |

Caso:

```json
{"title":"Investigação documental","notes":"Conclusão e limitações do analista","priority":"normal","status":"open","domain_ids":[1]}
```

Status: open, investigating, closed. Prioridade: low, normal, high. Para reabrir, envie o caso com status open. O PUT exige todos os campos que se pretende preservar; campos omitidos retornam aos defaults do schema.

Regra:

```json
{"version":"revisao-2026-01","effective_from":"2026-01-01T00:00:00Z","effective_until":null,"weights":{"betting_content":25,"cross_domain_redirect":15},"rationale":"Justificativa técnica, escopo e referências normativas revisadas pelo administrador"}
```

Datas de regra exigem fuso horário. Versões não podem ser sobrescritas. Pesos inteiros de 0 a 100. Chaves não reconhecidas são recusadas.

Confirmação de encaminhamento:

```json
{"protocol":"PROTOCOLO-RECEBIDO","confirmation":"Referência da confirmação recebida do canal oficial, com data e canal"}
```

A API armazena `confirmed_by_analyst`, sem afirmar validação externa. Não faz POST a Fala.BR.

## Limites

Corpo de mutação: 300.000 bytes. Cadastro: 5 por hora por IP; login: 10 por minuto por IP e email; coletas: 6 por minuto por usuário; sincronização oficial: 2 por minuto por admin. Os limites são por processo e não equivalem a proteção distribuída. Sucesso de `/health` confirma apenas a consulta simples do banco, não disponibilidade de fontes externas.

## Descoberta automática

| Método | Rota | Finalidade |
|---|---|---|
| GET | /api/discovery/catalog | Fonte pesquisada, hosts permitidos e limites reais |
| GET / POST | /api/discovery/feeds | Listar/cadastrar fonte própria |
| PATCH | /api/discovery/feeds/{id}/state | {enabled: true/false} |
| GET | /api/discovery/runs | Até 50 consultas com hash e contagens |
| GET | /api/discovery/jobs | Últimas 100 tarefas, totais por estado e uso diário |
| POST | /api/discovery/queue | Enfileirar até 100 domínios próprios sem análise/tarefa |
| POST | /api/discovery/queue/pause | Pausar tarefas aguardando, sem cancelar coleta em curso |
| POST | /api/discovery/queue/resume | Retomar tarefas pausadas |
| POST | /api/discovery/jobs/{id}/action | {action: pause/resume/retry} |

`POST /api/discovery/import` aceita `auto_analyze: true` opcional (padrão false) e retorna `queued`. Fontes exigem `name`, `url` HTTPS em host permitido, `format` (csv/json/domains/hosts), `permission_reference` e opcionalmente `interval_hours`, `batch_size`, `auto_analyze`, `enabled`. Cadastro de fontes limitado a cinco tentativas por minuto por usuário. A criação de fila manual é limitada a duas por minuto. Todos os endpoints preservam autenticação, CSRF, perfis e isolamento por proprietário.

Não há endpoint que aceite uma URL arbitrária e amplie a allowlist do operador. O campo de licença é uma declaração documentada do usuário, não uma validação jurídica automática. Consulte AUTOMATION.md.

`GET /api/version` é público e retorna build_id (hash dos arquivos Python, fixado ao carregar o processo) e required_schema_revision. O iniciador usa esse identificador para detectar servidores antigos; ele não divulga segredos e não substitui a verificação de saúde do banco.

## Segurança e fluxo automático

`GET /api/auth/policy` é público e informa o modo de cadastro. Cadastro padrão exige `invitation`, email correspondente e senha de 15–128 caracteres. Login recebe `email`, `password` e, quando MFA ativo, `otp_code` ou `recovery_code`. A resposta de sessão inclui `mfa_enabled`; cookie e CSRF continuam obrigatórios nas mutações autenticadas.

| Método/rota | Uso |
|---|---|
| GET /api/auth/security | Estado do MFA e política de sessão |
| POST /api/auth/mfa/setup | Senha atual; retorna segredo e URI privados por 10min |
| POST /api/auth/mfa/confirm | `{code}`; ativa MFA, gira sessão e retorna `{user,recovery_codes}` |
| POST /api/auth/mfa/disable | Senha e segundo fator; revoga sessões |
| POST /api/auth/password | Senha atual, segundo fator se ativo e `new_password`; gira sessão |
| GET /api/auth/sessions | Sessões da própria conta |
| POST /api/auth/sessions/revoke-others | Reautenticação; encerra outras sessões |
| GET/POST /api/security/invitations | Admin com MFA; emissão exige reautenticação, email, role analyst/viewer, hours 1–72 |
| POST /api/security/invitations/{id}/revoke | Admin com MFA e reautenticação |
| GET/PUT /api/automation/workflow | Política própria: enabled, recurring_hours, minimum_score, create_cases, prepare_reports |
| GET /api/automation/history | Execuções próprias, casos/PDFs e falhas |
| GET /api/regulatory/context | Último contexto oficial e validade da consulta |
| POST /api/regulatory/sync | Admin com MFA; consulta nova do contexto |

Reautenticação usa `password`, `otp_code` ou `recovery_code`. Códigos TOTP não podem ser reutilizados; códigos de recuperação funcionam uma vez. Convite é retornado só na emissão, nunca na listagem. Nenhuma rota verifica posse do email ou envia mensagens.

O resultado de nova análise inclui `verdict`: code, label, explanation, requires_human_review=true, crime_determined=false e limitações; estado regulatório e contexto ficam preservados junto às evidências. Análises antigas mantêm seu snapshot original e precisam de nova coleta para os campos novos.

`GET /api/automation/status` retorna automatic_setup, enabled, last_reconciliation, next_reconciliation, daily_limit e delay_seconds, com estado persistido do worker. A política enabled controla descoberta/fila/agendamentos da conta. A reconciliação padrão encontra inventário pendente mesmo quando uma importação não pede enfileiramento imediato. Pausas individuais não são revertidas. AUTO_SETUP controla o provisionamento/reconciliação do servidor.

## APIs operacionais atuais

- GET /api/inventory?page=1&size=25&q=texto&priority=high: inventário paginado.
- GET /api/pages/{domains,analyses,cases,reports,audit,report-jobs}: paginação; size máximo 200.
- GET /api/analyses/{id}: detalhe próprio.
- GET /api/operations/alerts: filas, falhas, heartbeat e alertas permitidos ao perfil.
- GET /api/evidence/documents/{id}: documento bruto autorizado, download e hash.
- POST /api/report-jobs/{id}/{retry,discard}: tratamento de falhas próprias.
- POST /api/auth/email/request e /email/confirm: confirmação de email.
- POST /api/auth/password/request-reset e /password/reset: recuperação com token e MFA quando habilitado.
- GET /api/auth/email/local-inbox: somente mensagens da própria conta, ambiente local.
- POST /api/auth/activity: atividade real da interface; polling GET não renova inatividade.

PDF arquivado retorna 410. Fila não significa relatório concluído nem denúncia enviada.

## Processamento e diagnóstico

- POST /api/report-jobs/{id}/generate: processa tarefa própria pendente com limites; retorna status/report_id/error, inclusive falha persistida. Pode retornar 409 se em execução ou automação pausada. Sem envio de denúncia.
- GET /api/automation/diagnostics: heartbeat, fila, fontes e cota efetiva da conta.
- POST /api/automation/continuous: aplica perfil horário explícito na própria conta; fonte deve ser permitida pelo servidor, limite de cinco solicitações/minuto, com auditoria.

## Apoio à revisão

- GET /api/notifications: avisos atuais, PDFs recentes, quantidade não reconhecida e estado por usuário.
- POST /api/notifications/acknowledge: JSON {notification_id}; só aceita identificador presente nos avisos da própria conta e registra auditoria sem duplicar reconhecimento. Não altera a causa do alerta.
- GET /api/cases/{id}/checklist: verificações calculadas dos registros atuais; não realiza coleta externa nem modifica o caso. Retorna 404 para caso de outro proprietário.

## Evidências e comparação técnica

- GET /api/analyses/{id}/compare?previous_id=N: compara uma análise própria com a anterior do mesmo domínio; sem anterior retorna available=false. Referência cruzada ou de outra conta retorna 404.
- POST /api/cases/{id}/evidence-export: exporta ZIP limitado com snapshot, documentos originais, README e manifesto SHA-256. 409 para hash divergente; 422 para escopo/tamanho excessivo; 429 para limite de exportação. A conclusão gera auditoria. Corpo pode ser vazio.
- GET /api/reports/{id}/integrity: confere bytes armazenados do PDF; status verified, mismatch ou unavailable para bytes arquivados. Não verifica autenticidade ou arquivo externo.

O PDF técnico usa template versionado technical-report-v2. Consulte TECHNICAL_REPORTS.md para limites, metodologia e verificação offline.
