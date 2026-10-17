# Operação e atualização

## Linux/Kali local

Execute no terminal normal do computador:

```bash
cd /home/kali/bethunter
./iniciar.sh stop
./iniciar.sh
./iniciar.sh status
```

Acesse http://localhost:8080. O stop preserva o banco. Não use sudo. O iniciador prepara migrações e separa os papéis de runtime e migração. Segredos persistem em `.runtime/local.env`; não compartilhe esse arquivo. Este terminal do agente não permite abrir sockets: a nova versão não foi observada rodando aqui.

## Email

Foi criado `app.maildev`: SMTP local de captura em 127.0.0.1:1025. **Não envia mensagens para caixas na internet.** Veja mensagens da própria conta em Segurança ou, como operador, execute:

```bash
./iniciar.sh inbox
```

Links são sensíveis e expiram. Capturas são privadas e limpas após sete dias pelo worker. Confirmação local é identificada como local; não é aceita como comprovação real em produção. Verificação e recuperação usam tokens únicos; recuperação de senha preserva a exigência de MFA.

Para entrega real configure SMTP_MODE=smtp, SMTP_HOST, SMTP_PORT (normalmente 587), SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM e SMTP_STARTTLS=true, com domínio/remetente autorizado pelo provedor. Produção exige REQUIRE_EMAIL_VERIFICATION=true, APP_ENV=production, HTTPS, cookie seguro e chave de autenticação persistente. Aceitação pelo SMTP não comprova entrega na caixa postal.

## Compose novo

```bash
python3 scripts/configure.py
docker compose up --build -d
```

O configurador gera somente segredos ausentes. Banco, provisionador, migrador e runtime usam credenciais distintas. Backend/worker não recebem a senha administrativa. A migração restringe alteração/exclusão de evidências e auditoria pelo runtime. O administrador do banco continua tendo controle dos dados.

**Volume legado:** editar POSTGRES_USER não altera os papéis existentes. Para o volume dedicado antigo com administrador bethunter, configure primeiro e execute `python3 scripts/upgrade_compose.py`: o script faz backup criptografado antes de parar os serviços e preparar o bootstrap. Depois execute Compose. Para instalações personalizadas, faça migração administrada dos papéis. Nunca use down -v para atualizar ou recuperar dados.

## Backups e restauração

```bash
./iniciar.sh backup
python3 scripts/restore_check.py
```

O segundo comando testa restauração em outro banco temporário e confere hashes e segredos MFA, sem substituir o banco original. Requer PostgreSQL acessível no host. Backup automático é diário, com sete cópias por padrão; falhas aparecem nos alertas. Preserve BACKUP_ENCRYPTION_KEY separadamente: sem ela os backups não podem ser abertos. A chave AUTH_ENCRYPTION_KEY está dentro do arquivo criptografado para permitir recuperar MFA. Copie backups para armazenamento externo protegido; o volume local não protege contra perda do computador.

Restauração manual: no ambiente do backend, defina RESTORE_DATABASE_URL para um banco vazio separado e execute `python -m app.backups restore --file /caminho/copia.bhbackup --config-output /caminho/novo/restored-auth.env`. Nunca aponte ao banco de produção. O arquivo de configuração de saída deve ser novo. Limite padrão 256 MB; criptografia usa memória e precisa de planejamento para bases maiores.

## Relatórios e operação

A API retorna 202 com job_id ao enfileirar PDF. Acompanhe a página Relatórios; o worker renderiza em subprocesso com prazo e limites. Não é um sandbox de sistema operacional completo. Há deduplicação, limite de 20 tarefas pendentes por conta, snapshot de 2 MB, PDF de 5 MB e cota de 100 MB por conta. Até 50 análises por domínio entram no snapshot, com contagem total e aviso; o histórico original permanece no banco.

REPORT_RETENTION_ENABLED=false por padrão. Ative somente após testar restauração: arquiva bytes de PDFs preparados antigos, preservando metadados/evidências, mínimo recente por caso e PDFs com confirmação. Exige backup concluído nas últimas 48h, arquivo presente e hash correspondente antes de arquivar bytes. Alertas mostram fila atrasada, falhas, heartbeat e situação do backup; não são notificações externas. Mantenha um backend e um worker neste MVP.

## HTTPS opcional

Com domínio e DNS próprios, configure PUBLIC_HOSTNAME, ORIGIN=https://seu-dominio, COOKIE_SECURE=true e requisitos de produção acima, e use `docker compose -f docker-compose.yml -f docker-compose.https.yml up --build -d`. Caddy precisa alcançar portas 80/443. Exemplo usa rede 172.29.0.0/24; alteração exige ajustar IP do edge e confiança no Nginx. Nenhum certificado público ou entrega SMTP externa foi validado nesta sessão.

## Verificação

CI inclui testes PostgreSQL, privilégios, backup/restore, build, análise estática, auditorias de dependências e smoke Playwright em Compose descartável. A existência do workflow não comprova execução bem-sucedida. Consulte VERIFICATION.md para os resultados locais e pendências reais.


## Correção de PDFs e descoberta frequente

Em Casos, **Gerar e baixar PDF** enfileira e processa o documento com os mesmos limites, sem depender de um worker ativo para o pedido manual. Em Relatórios, tarefas pendentes têm **Gerar e baixar agora**. Falhas ficam registradas; não se apresenta um download como concluído quando o navegador apenas recebeu a solicitação. Perfis de leitura não podem gerar, e isolamento por proprietário é aplicado também no processamento.

O diagnóstico em Descoberta/Relatórios mostra heartbeat, fontes/erros/próxima consulta, fila, cota e limiar de PDF. **Ativar descoberta horária e PDFs de revisão** aplica à própria conta: fonte padrão habilitada, 100 candidatos por hora e mínimo 25 para casos/PDFs. Configurações anteriores são preservadas até esse comando explícito. Novas contas usam esses padrões. Monitoramentos individuais permanecem com seu intervalo; a cota compartilhada continua em 100 tentativas/dia e atraso de 30s. Atingir a cota suspende análises até o próximo dia UTC; não é paralisação do worker.

A configuração anterior usava 50 candidatos/dia e mínimo 50, acima do score técnico usual, causando pouca descoberta e ausência de PDFs automáticos. Não foi encontrada prova de falha do renderizador nos logs locais; os logs registraram coletas externas com falhas DNS/TLS. A nova interface expõe causas, e o worker tenta novamente seu ciclo após erro transitório de banco em vez de encerrar silenciosamente.


## Central de notificações e checklist

Acesse **Notificações** na navegação para consultar avisos atuais do banco e os dez PDFs mais recentes dos últimos sete dias. O filtro permite mostrar avisos reconhecidos. **Marcar como visto** registra reconhecimento por usuário na auditoria, de forma idempotente. Não resolve a causa e não remove alertas do dashboard. Se o conteúdo do aviso mudar, ele recebe nova identificação e pode aparecer como não reconhecido. Não há email, push ou envio a terceiros por essa central. A consulta considera os últimos 2.000 reconhecimentos por conta.

Em cada caso, **Ver checklist de revisão** confere os registros atuais: domínios associados, existência e completude das últimas análises, coleta nas últimas 24h, evidências estruturadas, parecer humano e disponibilidade do contexto regulatório. A checagem não realiza nova coleta de rede, não certifica a qualidade do parecer ou legalidade e não bloqueia encerramento ou exportação. Uma pendência regulatória deve permanecer visível quando não houver contexto verificável. Dados e reconhecimentos são isolados por proprietário.

Deduplicação de relatórios considera mudanças técnicas/regulatórias e correções dos pareceres incluídos. O checklist compara documento/versão do contexto usado na análise com o atual; datas futuras não contam como coleta recente. Reconhecer notificações não resolve a falha indicada.
