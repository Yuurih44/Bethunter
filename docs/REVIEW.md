# Revisão técnica

A revisão cobre autenticação, autorização, coleta pública, SSRF, regras, automação, relatórios, evidências, recuperação e implantação. Os resultados verificáveis estão em [VALIDATION.md](VALIDATION.md). Não é uma certificação de produção nem um pentest externo.

## Correções implementadas

| Área | Problema | Correção |
|---|---|---|
| Coleta | Coleta incompleta podia parecer ausência de indicadores | Estado de coleta e avaliação explícitos |
| Scheduler | Erro de integridade invalidava a transação de controle | Savepoint preservando erro, cota e agendamento |
| Automação | Monitoramentos podiam consumir toda a cota | Alternância entre fila e monitoramento |
| Grafo | Observações antigas sobrescreviam recentes | Preservação da observação mais recente |
| Testes | Fixture destrutiva podia apontar ao banco da aplicação | Nome de teste e autorização explícita para banco persistente |
| TLS | Hosts no mesmo IP podiam compartilhar conexão | Conexão independente e SNI por salto |
| Banco | Runtime recebia privilégios excessivos | Papéis separados para provisionamento, migração e runtime |
| PDF | Deduplicação ignorava mudanças técnicas e pareceres anteriores | Assinatura do resultado significativo, revisões e versão do modelo |
| Retenção | Registro de backup era aceito sem o arquivo correspondente | Presença, data, tamanho e hash exigidos antes de arquivar bytes |
| Checklist | Contexto regulatório antigo e datas futuras podiam ser aceitos | Correspondência de documento/versão e janela temporal válida |
| Validação de URL | Porta explícita zero não era recusada | Comparação explícita com as portas permitidas |
| Dependências | Auditorias identificaram versões com alertas conhecidos | Atualização de dependências e novas auditorias aprovadas |
| PostgreSQL local | Atualização do sistema alterou a versão de collation | Backup/restore conferido, reconstrução de índices e atualização dos metadados |
| Evidências | Exportação precisava de conferência e limites | Manifesto SHA-256, validação dos registros/documentos e cotas de tamanho/concorrência |

## Validação observada

- **189 testes aprovados em PostgreSQL real, sem testes ignorados.**
- Build TypeScript/Vite, Ruff e Bandit aprovados.
- npm audit e pip-audit sem vulnerabilidades conhecidas nas versões consultadas.
- Backup/restore em alvo separado, verificação de hashes e segredo MFA exercitados.
- Chromium/Nginx: autenticação, navegação móvel, casos, PDF, MFA, SMTP local, notificações, comparação e pacote ZIP.
- Os quatro jobs do GitHub Actions passaram, incluindo PostgreSQL 16 e Docker.

As fontes externas são mockadas na suíte determinística. Uma coleta documental separada confirmou DNS, TLS e HTTP públicos. O teste de navegador usa dados sintéticos identificados e banco isolado. As evidências e o commit validado estão documentados; resultados de uma execução não garantem versões futuras.

## Riscos e pendências

1. **Implantação pública:** configurar e validar provedor SMTP real, remetente autorizado, domínio/DNS e HTTPS público. Confirmar política de acesso e recuperação de desastre.
2. **Escala:** o MVP pressupõe um backend e um worker. Rate limiting é local ao processo; endpoints legados ainda possuem listagens amplas. Validar carga e concorrência antes de ampliar.
3. **Precisão:** termos e ações em notícias podem gerar falsos positivos. Conteúdo JavaScript, CAPTCHA e geolocalização limitam a coleta. Falta um conjunto rotulado para medir precisão.
4. **Fontes e regras:** formatos oficiais, vigência, escopo e exceções exigem acompanhamento. Ausência em lista e infraestrutura compartilhada não comprovam irregularidade.
5. **Recuperação:** backups usam memória e têm limite padrão de 256 MB. Manter cópia externa e chave separada; repetir testes de restauração. A retenção permanece opcional.
6. **Autenticidade:** auditoria não é WORM/assinada. Hashes conferem bytes, mas não comprovam autoria, veracidade ou cadeia de custódia certificada. O administrador do banco tem controle sobre os dados.

Consulte [ROADMAP.md](ROADMAP.md) para evolução e [THREAT_MODEL.md](THREAT_MODEL.md) para os limites dos controles.
