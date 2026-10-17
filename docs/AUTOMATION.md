# Descoberta e análise automática

A automação consulta listas públicas específicas, extrai candidatos, elimina duplicidades, registra origem e coloca candidatos na fila de análise. Não procura todos os domínios da internet, não gera nomes aleatórios, não faz varreduras de portas, não explora vulnerabilidades e não envia denúncias.

## Ativar

Atualize a aplicação preservando os dados:

```bash
cd Bethunter
./iniciar.sh stop
./iniciar.sh
```

O iniciador aplica as migrações até 0005 antes de iniciar API e worker. No Compose use `docker compose up --build -d`; provisionador e migrador executam antes do backend/worker com credenciais separadas.

Abra http://localhost:8080/discovery. Com `AUTO_SETUP=true` (padrão), o worker configura automaticamente a fonte pública do catálogo para contas ativas de analista/administrador. Isso também atende contas existentes. Não é necessário clicar para ativar. A mesma URL não é duplicada; fontes já cadastradas e pausadas permanecem pausadas. A allowlist de rede e o limite de dez fontes continuam sendo respeitados.

O worker começa a consultar em seu próximo ciclo; se estiver analisando outro domínio, termina essa tarefa antes de continuar. As contagens e o histórico da tela são atualizados a cada 10 segundos. O dashboard consulta seus dados a cada 15 segundos. Atualizações da tela não significam que há novos resultados a cada intervalo.

## Fonte pesquisada

**StevenBlack/hosts — gambling-only**:

- [Projeto e descrição da variante](https://github.com/StevenBlack/hosts/tree/master/alternates/gambling-only).
- [Dataset público em formato hosts](https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/gambling-only/hosts).
- [Licença MIT do projeto](https://github.com/StevenBlack/hosts/blob/master/license.txt).
- [Origem das listas e licenças MIT descritas pelo mantenedor](https://github.com/StevenBlack/hosts/blob/master/alternates/gambling-only/readme.md).

O catálogo referencia o dataset público e sua licença. A consulta de uma fonte só gera registros após importação pelo backend; referências documentais não são usadas para preencher métricas ou simular análises.

É uma lista comunitária internacional de conteúdo de apostas, com fontes voltadas também a outros países. Não comprova operação no Brasil, ausência de autorização, controle comum ou irregularidade. Sua presença não adiciona pontos de risco. A classificação continua dependente das observações técnicas e da situação regulatória explicitamente verificada ou não verificada.

O BetHunter não baixa executáveis desse projeto, não executa seus scripts e não altera `/etc/hosts`. Somente lê o dataset em HTTPS. Nenhum dataset é redistribuído junto com o código desta entrega; o catálogo contém referências e atribuição. Preserve e confira as licenças de origem antes de redistribuir conjuntos de dados ou documentos derivados.

## Limites padrão

| Limite | Padrão |
|---|---|
| Fontes por usuário | 10 |
| Consulta da fonte sugerida (novas contas/perfil horário) | A cada hora |
| Candidatos processados por consulta da fonte sugerida | 100 |
| Intervalo configurável por fonte | 1 a 8.760 horas |
| Candidatos configuráveis por consulta | 1 a 100 |
| Download máximo por fonte | 2.000.000 bytes, sem compressão |
| Registros máximos no documento | 100.000 |
| Tempo total de consulta da fonte | 30 segundos |
| Tarefas pendentes + pausadas por usuário | 1.000 |
| Tentativas automáticas por usuário/dia UTC | 100 |
| Atraso mínimo entre tentativas automáticas | 30 segundos |
| Coleta por domínio | Limite global de 60 segundos |

O cursor percorre lotes sucessivos da lista, dando a volta ao chegar ao fim. Os lotes são definidos pela posição no documento consultado; se a fonte muda de ordem, alguns domínios podem reaparecer ou demorar mais a entrar. Unicidade no banco evita duplicar domínios/tarefas. Não é um monitor exaustivo nem uma garantia de cobertura de todos os sites brasileiros.

Cotas são persistidas, sobrevivem a reinícios e contam falhas. Não são contagens fictícias nem probabilidades de crime. Fila e agendamentos recorrentes compartilham a mesma cota diária e atraso mínimo. Coletas manuais continuam com limite próprio por minuto. Uma tarefa já analisada manualmente antes de a fila alcançá-la é encerrada sem repetir coleta. Falhas na fila têm até três tentativas automáticas no total, com espera mínima de cinco minutos após a primeira e dez minutos após a segunda. Depois disso, a falha permanece para revisão; o controle manual de nova tentativa continua disponível.

## CSV e inventário existente

No importador CSV, marque **Analisar novos candidatos automaticamente**. A análise ocorre no worker, não durante a requisição de importação. A opção fica ligada por padrão na interface. Ela controla a fila imediata da importação; com a automação geral habilitada, o worker também encontra e enfileira domínios pendentes do inventário.

**Enfileirar até 100 domínios sem análise** permite aproveitar o inventário já cadastrado. Domínios com análises, tarefas existentes ou que ultrapassem o limite da fila não são duplicados.

## Pausa e retomada

**Pausar fonte** impede novas importações; não cancela tarefas já criadas. **Pausar fila atual** pausa tarefas aguardando, pulando linhas já bloqueadas por uma coleta em andamento. Uma tarefa em execução pode concluir. **Retomar fila pausada** retoma as tarefas pausadas. Falhas elegíveis têm tentativas automáticas limitadas; **Tentar novamente** permite uma tentativa manual após revisar a causa.

## Outras fontes

Formatos aceitos: CSV com coluna `domain`, JSON com array de strings/objetos `{domain}`, um domínio por linha e hosts com `0.0.0.0`, `127.0.0.1` ou `::` como prefixo de bloqueio.

Cadastre nome, URL HTTPS, formato e referência de licença/autorização. O host precisa estar em `DISCOVERY_ALLOWED_HOSTS`; por padrão somente `raw.githubusercontent.com`. Essa allowlist é configurada pelo operador, não ampliada por um usuário da API. Todos os saltos precisam continuar em HTTPS e em hosts permitidos, com DNS público validado e IP fixado. Um host permitido não garante a qualidade ou a licença de todos os seus arquivos: revise o documento escolhido.

Configuração no `.env` do Compose; no iniciador nativo, edite `.runtime/local.env` ou exporte essas variáveis no terminal antes de iniciar:

```dotenv
DISCOVERY_ALLOWED_HOSTS=raw.githubusercontent.com
AUTO_ANALYSES_PER_DAY=100
AUTO_ANALYSIS_DELAY_SECONDS=30
AUTO_QUEUE_LIMIT=1000
```

Não coloque segredos ou tokens de APIs privadas nas URLs. O adaptador atual é para documentos públicos sem autenticação. Mecanismos de busca, CT, DNS passivo e APIs pagas exigem conectores adicionais.

## Persistência e evidências

A migração 0003 cria discovery_feeds, discovery_runs, discovery_candidates, analysis_jobs e automation_quotas. Cada consulta salva estado, data, hash e contagens reais. Candidatos guardam associação com a fonte e primeira/última observação. Cada domínio pode ter somente uma tarefa de descoberta, com histórico de tentativas na auditoria.

A análise automática preserva a origem, referência de licença, hash do documento e associação observada. Esses dados acompanham evidências e snapshots dos PDFs. Erros não geram autorização nem irregularidade automática.

O worker usa locks PostgreSQL `FOR UPDATE SKIP LOCKED`, mantém a transação da tarefa até persistir a análise e serializa a cota por usuário. Em caso de interrupção antes do commit, a tarefa permanece na fila; uma coleta externa pode ser repetida após reinício. Não há promessa de exatamente uma solicitação externa em toda falha possível. O estado visível permanece queued durante a coleta sob lock; a interface não simula um progresso em tempo real.

## Fluxo após a coleta

A política individual em Descoberta começa habilitada para novas análises: monitoramento a cada 24h; rascunho de caso e PDF se houver IP público observado e score >=50 ou sinal de possível incompatibilidade com contexto oficial reconhecido. A política permite ajustar intervalo, limiar e etapas. As regras técnicas padrão somam até 40, portanto uma coleta com apenas termos/redirecionamento pode não abrir um caso.

Cada análise possui registro de execução idempotente. Novas análises podem preparar novos snapshots de relatório no mesmo caso automático. Um caso encerrado pelo analista não é reaberto automaticamente. Falha de PDF/fluxo não descarta a análise: registra falha para inspeção. Desativar o fluxo impede execução das fontes, fila e agendamentos da conta, sem apagar ou alterar suas pausas individuais. Reativar o fluxo retoma os itens habilitados e preserva os itens pausados individualmente. Uma coleta já em andamento pode concluir. Mudanças de intervalo afetam novos agendamentos; existentes têm ajuste individual.

O worker consulta contexto normativo oficial e tabela documental a cada 6h por padrão (`AUTO_OFFICIAL_SYNC`, `OFFICIAL_SYNC_HOURS`). A consulta precisa ser recente, reconhecida e aplicável temporalmente. Uma última falha invalida verificação atual. Não há atualização automática de código do parser: alteração de formato requer manutenção.

PDFs automáticos são rascunhos, com notas explícitas e limitações. A situação da denúncia permanece preparada; não há envio, protocolo inventado ou decisão jurídica automática. A fonte do catálogo é configurada automaticamente; fontes adicionais podem ser selecionadas pelo analista. Não se enumeram todos os domínios da internet. A cota diária compartilhada inclui a fila e os agendamentos individuais, mas não a coleta manual; monitore também o volume desses agendamentos e a retenção de PDFs.

## Reconciliação automática

O worker verifica até 20 contas por ciclo e reconcilia cada conta no máximo uma vez por minuto. Em cada passagem pode enfileirar até 100 domínios ainda sem análise/tarefa, respeitando a fila máxima. Domínios já analisados e sem agendamento recebem monitoramento com coleta nova, sem reinterpretar snapshots antigos como atuais. Uma nova fonte do catálogo começa com lote de 50 e intervalo de 24h. Históricos, falhas, cotas e pausas sobrevivem a reinícios.

A tela informa a última passagem registrada do worker, inclusive quando nenhuma tarefa nova foi criada. Um horário antigo ou ausente não comprova que o worker está funcionando. Inventário, casos, relatórios e histórico do fluxo consultam a API a cada 15s; o painel de fontes/fila usa 10s. Isso atualiza a visualização, sem inventar novas coletas.

`AUTO_SETUP=false` desabilita a reconciliação automática de fontes, inventário e retries. Não cancela tarefas existentes; para interromper a execução da conta, use a pausa geral do fluxo. A sincronização normativa global possui controle separado `AUTO_OFFICIAL_SYNC`.

Autenticação, confirmação de MFA, revisão humana, encerramento de casos, confirmação de protocolos e envio de denúncias continuam dependendo de ação humana. Automatizar esses atos não é parte do modo automático.

A preferência entre fila de descoberta e monitoramento recorrente alterna a cada ciclo do worker único. Isso evita que o monitoramento tenha prioridade fixa sobre toda a cota. Não é garantia de prazo ou distribuição exatamente igual entre todas as contas quando o orçamento de consultas é insuficiente. Coleta HTTP/DNS incompleta recebe veredito específico; uma falha de persistência da análise agendada é isolada por savepoint para permitir registrar o erro e o próximo agendamento.
