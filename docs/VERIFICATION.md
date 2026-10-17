# Verificação realizada

Ambiente: Linux, Python 3.14.7, Node 24.22. Destino Compose/CI: Python 3.12, PostgreSQL 16 e Node 22. Resultados desta revisão:

| Verificação | Resultado observado |
|---|---|
| Backend/API/segurança com SQLite e mocks externos | **179 passaram, 2 ignorados**, 21,65 s |
| TypeScript e build Vite com dependências reais | Passou, 2322 módulos; aplicação 179,80 kB antes de gzip |
| Migração 0005 | Upgrade, check, downgrade para 0004, upgrade e novo check passaram em SQLite temporário |
| Alembic check | No new upgrade operations detected |
| SQL offline PostgreSQL | Gerado até 0005 em database/schema.sql; não equivale a executar no PostgreSQL |
| Sintaxe Python | compileall passou |
| Compose e CI | Configurados; execução de containers e CI remoto não observada |
| Iniciador local | ./iniciar.sh check não inicia: sandbox bloqueia sockets |
| SMTP | Protocolo local e fila testados em processo/mocks; nenhum email entregue na internet |
| Backup/restore | SQLite real com criptografia, hashes e segredo MFA passou; PostgreSQL não executado |
| Navegador | Smoke Playwright criado; lançamento Chromium bloqueado no ambiente |
| Auditorias de dependências/estática | Não executadas com sucesso; ferramentas ausentes e instalação/repositórios inacessíveis |

Os dois testes ignorados exigem PostgreSQL real: restauração e privilégios dos papéis. Não são apresentados como aprovados. Logs: [test-results.txt](test-results.txt) e [frontend-build.txt](frontend-build.txt).

## Cobertura

Cadastro/login, Argon2id, CSRF/origem, convites, MFA e recuperação de uso único, sessões/inatividade, controle de acesso e isolamento; tokens de email, confirmação local distinta de SMTP real, reset preservando MFA e revogação de sessões; SSRF, DNS rebinding, pinning, redirecionamentos e limites; regras regulatórias conservadoras; CSV e fontes; fila/monitoramento/pausa/cotas/retry; paginação com mais de mil registros; contexto informativo para reduzir falsos positivos e download de evidência bruta com hash; PDF real em subprocesso, deduplicação, regeneração de arquivados, limites e falhas; alertas, backup criptografado/restauração e retenção com proteção de PDFs confirmados.

Fixtures são sintéticas e restritas a bancos de teste. Não são descobertas reais. E2E possui seed explicitamente marcado como demonstração e recusa banco com usuários existentes.

## Modo de teste local

```bash
BETHUNTER_INLINE_TESTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
```

Este modo usa HTTPX ASGITransport e dispatch em processo, pois o sandbox impede sockets/threadpool normal. Exercita rotas, middleware e transações, mas não comprova concorrência ou servidor TCP. O CI usa TestClient normal. Nunca execute a suíte contra banco real: fixtures recriam o esquema e bancos persistentes exigem nome de teste e autorização explícita.

## Pendências reais

Validar em terminal normal: reinício da instalação, migração de cópia do banco existente, PostgreSQL/Compose, papéis mínimos, backup/restore, login/MFA/email, navegador desktop/móvel, PDF, coleta externa e fontes oficiais atuais. Validar SMTP real e HTTPS somente após configurar domínio/provedor. Auditorias Ruff/Bandit/pip-audit/npm audit estão no CI; sua execução remota ainda não foi observada. Não há afirmação de ausência de vulnerabilidades ou aprovação para produção.

O terminal desta sessão não pode abrir sockets nem alcançar o localhost externo do usuário. Nenhum servidor foi iniciado aqui. Instruções de operação: [OPERATIONS.md](OPERATIONS.md).

A revisão de PDFs/descoberta acrescentou testes de geração manual sem worker com PDF real/download, autorização por proprietário, perfil horário idempotente, allowlist e score 25 gerando tarefa automática. Alterações de runtime precisam ser carregadas reiniciando a instalação; não houve reinício do host pelo agente.

Notificações/checklist: cinco testes adicionais passaram, cobrindo pendências reais, uso da última análise em vez de parecer antigo, reconhecimento idempotente sem ocultar falha operacional, isolamento por proprietário e notificações de PDF sem conteúdo sensível embutido. Não há mudança de esquema nesta etapa. Build completo passou novamente.

## Revisão completa posterior

Foram reproduzidas e corrigidas falhas na assinatura de deduplicação do PDF, correspondência de contexto normativo do checklist e retenção com arquivo de backup inexistente. Também corrigidas datas futuras e porta explícita zero. Cinco verificações adicionais na suíte; teste de contexto cobre também cenário positivo com hash/versão atuais. Migração voltou a passar com reversão/reaplicação; saída em migration-check.txt. npm audit falhou por EAI_AGAIN, saída em npm-audit.txt. Nenhum diagnóstico de ausência de vulnerabilidades foi obtido. Detalhes e pendências em REVIEW.md.

A solicitação de validação integral foi executada até o limite do ambiente: ver VALIDATION.md e validation-results.json. Foram tentados PostgreSQL, Chromium, Nginx, instalação de auditores e npm audit; continuam bloqueados conforme evidências, sem aprovação de produção.
