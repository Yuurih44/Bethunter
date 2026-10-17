# Validação com rede e execução local liberadas

As restrições anteriores foram removidas e as verificações foram repetidas. Os resultados anteriores continuam históricos; esta validação os substitui nas áreas abaixo.

| Verificação | Resultado observado |
|---|---|
| Aplicação nativa | Iniciador executado, PostgreSQL/API/worker/frontend/SMTP local iniciados; dados preservados |
| Suíte PostgreSQL 18 real | **181 passaram, sem ignorados**, 79,26s; TestClient normal, sem modo inline |
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
| Docker | Ausente localmente. GitHub Actions executou build/up/seed; smoke original falhou por teste desatualizado. Correções preparadas para repetir CI |
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
