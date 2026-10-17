# Revisão técnica completa — 17/10/2026

Revisão de código e verificações locais do backend, frontend, autenticação, coleta/SSRF, classificação, fontes, automação, relatórios, backups, migrações, iniciador, Compose e CI. Não é certificação de produção nem pentest externo.

## Erros encontrados e corrigidos nesta revisão

| Prioridade | Problema reproduzido / impacto | Correção |
|---|---|---|
| Alta quando retenção habilitada | O registro de backup concluído permitia arquivar PDFs mesmo se o arquivo tivesse sido removido | Retenção exige arquivo presente, tamanho limitado, data válida e SHA-256 correspondente; caso contrário preserva os bytes |
| Média | Fingerprint de PDF ignorava mudança de certificado/infraestrutura/contexto e correção de parecer antigo; podia reutilizar PDF desatualizado | Assinatura inclui resultado técnico/regulatório significativo, classificação e pareceres incluídos, excluindo somente metadados voláteis de coleta |
| Média | Checklist podia aprovar verificação regulatória usando uma análise vinculada a documento/versão anterior | Exige contexto verificado na análise com hash e versão iguais aos do contexto atual |
| Média | Datas futuras eram aceitas como coleta recente no checklist | Janela de 24h agora também termina no instante atual |
| Baixa | Normalização aceitava porta explícita zero por tratar zero como ausência de porta | Rejeita qualquer porta explicitamente diferente de 80/443 conforme o esquema |

Os testes de deduplicação, contexto/data futura e retenção com arquivo ausente falharam antes da correção. Depois passaram, inclusive a suíte completa. A presença/hash de um backup não prova restaurabilidade; o exercício de restauração continua necessário.

Outros ajustes: serialização por conta ao reconhecer notificações, para evitar reconhecimentos duplicados concorrentes em PostgreSQL; alertas administrativos passam a indicar arquivo de backup ausente ou vencido; contexto de build Docker exclui arquivos de banco, dumps e chaves privados. Não houve alteração de esquema nem exclusão de dados existentes.

## Resultado observado

- **179 testes passaram, 2 ignorados** (PostgreSQL indisponível), 21,59s.
- TypeScript/Vite passaram com dependências reais; aplicação 179,80kB antes de gzip.
- compileall passou; Compose, override HTTPS e CI têm YAML válido.
- Alembic: upgrade 0005, check, downgrade 0004, upgrade/check passaram em SQLite temporário.
- Dependências Python diretas instaladas coincidem com requirements.txt.
- npm audit tentou consultar o serviço, mas falhou com EAI_AGAIN; sem diagnóstico de vulnerabilidades.
- Ruff, Bandit, pip-audit e Docker ausentes. CI contém essas verificações, mas execução remota não observada.

Evidências: test-results.txt, frontend-build.txt, migration-check.txt e npm-audit.txt.

## Áreas revisadas

| Área | Controles / resultado da revisão | Limite da evidência |
|---|---|---|
| Autenticação e contas | Argon2id, sessões por hash, CSRF/origem, convites, TOTP/recuperação de uso único, email e reset preservando MFA, isolamento por conta | Testes em processo; SMTP externo e múltiplos processos não validados |
| Coleta | DNS público, rejeição de redes reservadas, pinning por salto, verificação TLS, proxy de ambiente ignorado, limites de corpo/tempo, compressão recusada | Mocks; handshake e rotas externas não validados nesta revisão |
| Regras e fontes | Ausência/falha/antiguidade não prova irregularidade; regras versionadas; score explicado; revisão humana | Parser oficial específico; revisão jurídica contínua necessária |
| Automação | Fonte horária configurável, fila/cotas/pausas/retry, justiça entre fila e monitoramento e heartbeat | Não busca toda a internet; depende de fontes e serviço ativo |
| PDF/evidências | Renderização real em subprocesso, limites, deduplicação corrigida, snapshot/hash, geração manual, cotas e retenção protegida | Subprocesso não é isolamento completo do sistema operacional |
| Banco e recuperação | Migração congelada, papéis separados, privilégios de runtime e backup criptografado com chave MFA | Migração/restore SQLite reais; papéis e restore PostgreSQL pendentes |
| Interface | Build completo, paginação, ações integradas, diagnósticos, notificações e checklist | Sem teste visual/browser nesta sessão |
| Operação | Iniciador identifica versão, Compose/CI/HTTPS configurados, segredos excluídos do pacote | Sandbox bloqueia sockets e não iniciou o servidor |

Logs locais inspecionados não continham tracebacks de backend/worker; havia falhas DNS/TLS nas coletas. Isso não comprova ausência de erros ou execução da nova versão.

## Pendências e riscos restantes

1. **P1: validação real de implantação.** Exercitar PostgreSQL, upgrade de cópia do banco existente, papéis mínimos, backup/restore, Compose, navegador, TLS e SMTP real. Não considerar pronto para exposição pública só pelos testes locais.
2. **P1: auditorias de dependências/estática.** Reexecutar Ruff/Bandit/pip-audit/npm audit em ambiente com ferramentas e rede. Nenhum resultado de ausência de vulnerabilidades foi obtido.
3. **P2: escala e concorrência.** MVP pressupõe um backend e um worker. Rate limiting permanece local ao processo; endpoints legados de relatórios/agendamentos carregam listagens amplas, embora a interface principal use paginação. Validar carga/locks PostgreSQL antes de ampliar.
4. **P2: precisão e fontes.** Termos/ações em uma notícia ainda podem gerar falso positivo. Há limitação com páginas JavaScript, CAPTCHA, geolocalização e fontes indisponíveis; falta conjunto de avaliação rotulado de precisão. Caso/PDF automático não é conclusão jurídica.
5. **P2: armazenamento e recuperação.** Backup criptografa em memória, com limite padrão de 256MB. Cópia local pode ser perdida com o host; manter cópia externa e chave separada. Hash não substitui teste de restauração. Retenção permanece desabilitada por padrão.
6. **P3: evolução.** Auditoria não é WORM/assinada; administrador do banco tem controle. Não há CT/passive DNS completo, detector de imitação de marca ou casos colaborativos por equipe.

## Correções anteriores preservadas

Coleta incompleta sem classificação limpa indevida; scheduler com savepoint após erro de integridade; alternância da cota entre descoberta/monitoramento; grafo mantendo observação recente; proteção da fixture destrutiva contra banco real; conexões TLS separadas por hostname; papéis PostgreSQL separados; recuperação de email/MFA; fila/cotas PDF; paginação e diagnóstico; geração manual sem worker; fonte horária e limiar de caso/PDF explícitos por conta.
