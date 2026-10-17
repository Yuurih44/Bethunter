# Validação com rede e execução local liberadas

Resultados de execução local e integração contínua. O escopo de cada verificação é indicado abaixo.

| Verificação | Resultado observado |
|---|---|
| Aplicação nativa | Iniciador executado, PostgreSQL/API/worker/frontend/SMTP local iniciados; dados preservados |
| Suíte PostgreSQL 18 real | **189 passaram, sem ignorados**, 90,87s; TestClient normal, sem modo inline |
| Migração PostgreSQL | Upgrade e alembic check passaram no cluster exclusivo de testes |
| Privilégios | Runtime sem superusuário/criação de banco/papéis; teste rejeita DDL e exclusão de evidências |
| Backup/restore PostgreSQL | Passou em alvo separado, com hashes/documentos/PDFs e segredo MFA conferidos |
| Navegador Chromium + Nginx | Login, paginação, seleção de domínios entre páginas, caso, download de PDF, MFA, confirmação SMTP local, checklist, notificações e navegação móvel exercitados em banco sintético separado |
| Nginx | nginx -t passou; proxy real usado pelo teste de navegador. Upstream/porta/caminhos adaptados à execução nativa |
| Coleta pública externa | example.org: DNS público, TLS verificado, HTTP completo, 577 bytes, sem erros. Sem persistir análise de validação no banco real |
| TypeScript/Vite | Passou após migração Tailwind 4 |
| Ruff | Passou |
| Bandit | Nenhum achado médio/alto após ajustes documentados |
| npm audit | Zero vulnerabilidades conhecidas no relatório, incluindo dependências de desenvolvimento |
| pip-audit | Zero vulnerabilidades conhecidas nas dependências resolvidas de requirements.txt |
| Docker | Validado no GitHub Actions: build, up/health, seed sintético, smoke Chromium e privilégios runtime passaram |
| SMTP externo e HTTPS público | Não configurados: entrega na internet e certificado público da implantação não foram validados |

## Erros expostos pela validação

- Auditorias encontraram alertas na cadeia Tailwind 3 e em pydantic-settings 2.14.1, WeasyPrint 67 e cryptography 46. Atualizados para Tailwind/@tailwindcss-postcss 4.3.3, pydantic-settings 2.14.2, WeasyPrint 70 e cryptography 50; novas auditorias sem avisos conhecidos. Isso não comprova ausência de vulnerabilidades desconhecidas.
- O PostgreSQL nativo tinha collation antiga após atualização da biblioteca do sistema. Após backup/restauração conferidos, os índices foram reconstruídos (concorrentemente no banco da aplicação), a versão de collation foi atualizada em bethunter/template1/postgres, e nenhum índice inválido permaneceu. Dados preservados. O restore_check também passou a usar template0 para seu alvo separado.
- Bandit identificou um falso positivo em endereços de um dataset hosts (supressão somente B104, explicada no local). A consulta de conferência de hashes agora usa SQL estático em vez de concatenar nomes de tabelas.
- O smoke E2E ainda buscava o botão antigo de enfileirar PDF; foi atualizado para verificar o download imediato e aguardar especificamente o formulário MFA antes de preencher a senha. A revisão ampliou cobertura de checklist/notificações e viewport móvel.

## Isolamento

A suíte e o navegador usaram clusters/bancos exclusivos em .runtime/validation*, com fixtures claramente identificadas como demonstração. A conta original não recebeu dados sintéticos nem foi usada pelo navegador. Os servidores de teste são encerrados após o smoke. Capturas, senhas/chaves e bancos ficam fora do Git. O SMTP de teste captura localmente e não entrega emails pela internet.

Evidências: postgres-tests.txt, postgres-restore.txt, postgres-collation.txt, browser-e2e.txt, frontend-build.txt, nginx-check.txt, ruff-check.txt, bandit-audit.json, npm-audit.txt e pip-audit.json. Estes resultados não equivalem a pentest ou certificação de produção.

A migração Tailwind segue a [documentação oficial](https://tailwindcss.com/docs/upgrade-guide), com plugin PostCSS próprio e import CSS. Requer navegador moderno.

## GitHub Actions confirmado

A [execução 39076731836](https://github.com/Yuurih44/Bethunter/actions/runs/39076731836), commit 0ebfacd, terminou com sucesso nos quatro jobs: backend (PostgreSQL 16/Python 3.12), frontend, quality e compose-e2e. O teste Docker inclui build/up/health, navegador Chromium, PDF, MFA, SMTP local, checklist, notificações, viewport móvel e verificação do runtime sem superusuário. Resultado observado pela API oficial do GitHub e registrado em github-actions.json. Docker permanece ausente no host local; a validação de containers ocorreu no runner do GitHub.

O iniciador verifica a saúde da API e a identidade do código carregado. Os testes usam clusters separados da instalação principal. Contas de versões anteriores podem manter mínimo 50 para casos/PDFs; o perfil horário com mínimo 25 é aplicado explicitamente em Descoberta, preservando preferências até essa ação.

Pendências: SMTP externo com remetente/provedor reais, certificado HTTPS público da implantação com domínio/DNS e avaliação de carga/precisão. Não se declara prontidão irrestrita para produção.

## Relatório técnico e ferramentas de evidência

O modelo technical-report-v2 passou em renderização PDF real e download no navegador. A validação também passou por comparação de análises, exportação ZIP com manifesto conferido e verificação de PDF armazenado. Oito testes novos cobrem mudanças técnicas, isolamento entre contas, hashes/tamanho de pacote, verificador offline, corrupção de documentos/registros e mudança de versão do template. A coleta TLS adicional foi conferida com certificado público de example.org. O modelo não preenche campos ausentes em análises antigas. Veja TECHNICAL_REPORTS.md.

A execução remota 39076731836 confirmou também o novo PDF técnico, comparação de análises, pacote ZIP e verificação de integridade. Os quatro jobs passaram. A prévia E2E foi renderizada em cinco páginas e suas seções foram conferidas por extração de texto e inspeção visual; dados explicitamente de demonstração.
