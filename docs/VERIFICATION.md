# Evidências de verificação

A validação atual está em [VALIDATION.md](VALIDATION.md); o resumo estruturado, em validation-results.json. Os registros abaixo identificam as verificações executadas e seus resultados.

| Evidência | Resultado |
|---|---|
| postgres-tests.txt | 189 testes aprovados em PostgreSQL 18, TestClient normal, sem ignorados, dependências atualizadas |
| postgres-restore.txt | Restauração da base da instalação em alvo separado, com hashes e segredo MFA conferidos |
| postgres-collation.txt | Índices reconstruídos e metadados de collation corrigidos; nenhum índice inválido |
| browser-e2e.txt | Chromium/Nginx: login, paginação, caso, PDF técnico, MFA, SMTP local, checklist, notificações, comparação, exportação ZIP e integridade; capturas móveis inspecionadas |
| nginx-check.txt | Teste de configuração passou com porta/upstream/caminhos adaptados ao ambiente nativo |
| frontend-build.txt | TypeScript e build Vite aprovados com Tailwind 4 |
| ruff-check.txt | Verificação estática aprovada |
| bandit-audit.json | Nenhum achado médio/alto após ajustes |
| npm-audit.txt | Zero vulnerabilidades conhecidas, incluindo dependências de desenvolvimento |
| pip-audit.json | Zero vulnerabilidades conhecidas nas dependências resolvidas de requirements.txt |
| github-actions.json | Quatro jobs aprovados no GitHub, incluindo PostgreSQL 16 e E2E em Docker |

A suíte usa fontes externas mockadas para ser determinística. Adicionalmente, uma coleta não persistida de example.org confirmou DNS público, certificado TLS e HTTP sem erros. O teste E2E usa banco isolado e dados identificados como demonstração; não altera a conta real.

As capturas e credenciais de testes não são publicadas. Clusters PostgreSQL de validação foram encerrados; a instalação nativa permaneceu ativa e saudável. A auditoria externa SMTP/HTTPS da implantação exige provedor e domínio configurados. Ausência de alertas conhecidos não equivale a ausência de vulnerabilidades ou pentest concluído.
