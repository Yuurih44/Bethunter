# Validação final solicitada

A validação local foi repetida após as correções. **Não foi possível validar tudo em execução real neste ambiente.** O estado está registrado em validation-results.json.

| Verificação | Resultado |
|---|---|
| Backend/API/segurança/regras/filas/PDF/backup SQLite | 179 passaram; 2 testes PostgreSQL ignorados; 21,65s |
| TypeScript/Vite com dependências reais | Passou, 4,59s |
| Sintaxe Python | Passou |
| Parse YAML Compose/HTTPS/CI | Passou; não equivale a executar Compose |
| Alembic upgrade/check/downgrade/reaplicação SQLite | Passou |
| PostgreSQL ao vivo | Tentativa de conexão falhou com OperationalError; sockets locais restritos |
| Navegador Playwright | Chromium encerrou no lançamento; interface não validada visualmente |
| Nginx | Parser reconheceu sintaxe; teste completo falhou ao criar socket 8080. Upstream foi adaptado para endereço numérico e caminhos temporários para esta checagem |
| Docker/Podman | Ausentes; containers não construídos/iniciados |
| npm audit | Falhou por EAI_AGAIN; sem resultado de vulnerabilidades |
| Ruff/Bandit/pip-audit | Ausentes; tentativa normal de instalação falhou; não executados |
| SMTP externo/TLS público | Não validados; exigem serviço/domínio configurados |
| Restore PostgreSQL | Pendente; depende de PostgreSQL acessível e alvo separado |

O backend, worker, frontend e SMTP local não estavam acessíveis pelo terminal do agente. Não foi criado certificado, enviado email externo ou protocolada denúncia. Os PDFs da suíte foram renderizados de verdade, mas com dados sintéticos de teste. Serviços externos são mockados nessa suíte.

## Para concluir no host

No terminal normal do Kali:

```bash
cd /home/kali/bethunter
./iniciar.sh
./iniciar.sh status
python3 scripts/restore_check.py
```

O restore_check cria e remove somente um alvo PostgreSQL temporário; preserva o banco da aplicação e gera uma cópia criptografada. Precisa dos serviços acessíveis e das chaves configuradas.

Em ambiente com Docker, o workflow .github/workflows/tests.yml contém teste PostgreSQL e smoke Playwright em projeto Compose descartável com fixtures explicitamente sintéticas. Não execute seeds/testes destrutivos contra dados reais. A execução remota do workflow não foi observada aqui.

Para ferramentas de qualidade, instale requirements-dev.txt em ambiente de desenvolvimento isolado e execute os comandos do job quality. Falhas de rede e ausência de ferramentas não são resultados de ausência de vulnerabilidades. Consulte REVIEW.md para os riscos restantes.
