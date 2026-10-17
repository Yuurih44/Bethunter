# Arquitetura e decisões

## Fronteiras

A SPA usa Axios na mesma origem; Nginx serve os assets e encaminha `/api`. O backend não recebe credenciais de alvos. O usuário fornece um domínio/URL e o normalizador retorna somente hostname IDNA. As coletas começam em `https://domínio/`, sem dados de sessão, cookies de alvo ou parâmetros fornecidos pelo usuário.

O SQLAlchemy mantém transações parametrizadas. Cada domínio/caso possui owner_id. Análises, evidências, relatórios e denúncias são acessados através desse proprietário. Fontes oficiais e versões de regras são globais, escritas apenas por admin. Não existe compartilhamento implícito de casos entre analistas.

Perfis são uma enumeração com constraint no banco: analyst cria e revisa dados próprios; viewer consulta dados próprios; admin acrescenta gestão de fontes/regras. Permissões estão centralizadas nas dependências `current_user` e `admin`.

## Coleta

DNS A e AAAA têm prazo de 3 segundos por tipo. Todos os IPs resolvidos precisam ser globais e não reservados. A conexão HTTPX usa um IP já validado como destino; o hostname original segue em Host e SNI para verificação do certificado. Isso elimina uma segunda resolução implícita antes da conexão. Cada salto repete normalização e DNS. Não se usam proxies de ambiente. IP literals, credenciais, portas não padrão e nomes reservados são rejeitados.

A captura TLS usa `asyncio.open_connection` com IP fixo, SNI original e contexto SSL verificado. O certificado é uma observação da conexão, não uma afirmação de titularidade. Certificados expirados ou inválidos geram erro explícito; não se ignora a verificação.

HTTP: até cinco requisições, timeout de operação de 8s, 512.000 bytes de conteúdo, conteúdo comprimido recusado, 30s de limite total HTTP. A análise tem limite global de 60s. O backend limita quatro coletas simultâneas por processo. Worker dedicado executa uma por vez. A resposta armazenada contém metadados, trecho textual, termos encontrados e hash do corpo; não executa HTML/JS.

## Pontuação e regulação

Padrão technical-v1: betting_content 25 e cross_domain_redirect 15. Não há peso por TLD, erro de rede, falta de ASN, ausência em lista ou infraestrutura compartilhada. Soma limitada a 100. Cada resultado inclui fatores e pesos usados.

Níveis técnicos: 0 sem indicadores; 1–49 requer investigação; 50–74 suspeito; 75–100 evidências relevantes de possível irregularidade. **A situação regulatória não verificada prevalece como classificação textual**, mantendo o score técnico visível e suas limitações. Score zero com erro não significa que o domínio foi liberado ou integralmente analisado.

Novas regras têm versão única, início/fim de vigência e justificativa. A regra vigente com início mais recente prevalece. Uma nova versão não reescreve análises históricas. A revisão humana registra parecer separado e auditado; não modifica retroativamente os fatores observados.

Fonte oficial: consultas registram URL, horário, data de atualização identificada, empresas, domínio exato, CNPJ, atos e SHA-256 do documento. A última tentativa prevalece: uma falha nova impede reaproveitamento silencioso de lista antiga. Se faltar data, estiver no futuro ou a fonte/documento tiver idade superior ao limite, o estado é not_verified. listed significa correspondência exata em documento recente, sem afirmar autorização jurídica atual irrestrita. not_found não representa irregularidade.

## Evidências e relatórios

Cada análise armazena um JSON de resultados e evidência com payload, momento e SHA-256 do JSON serializado com chaves ordenadas. O relatório copia caso, histórico completo de análises, fontes e evidências para snapshot. O PDF é renderizado uma única vez, armazenado em BYTEA no PostgreSQL e exportado sem regeneração. Seu SHA-256 corresponde aos bytes baixados. Revisões posteriores exigem novo relatório.

O PDF escapa todo texto e bloqueia carregamentos externos. Notas nunca são interpretadas como HTML. A conclusão vem do analista ou registra explicitamente sua ausência. Report/Complaint separados permitem preparar documento sem afirmar envio. Confirmações são declarações do analista com protocolo e referência obrigatórios; não existe integração de protocolo com Fala.BR.

## Worker e descoberta

CSV: coluna domain, até 1.000 linhas, 250.000 caracteres dentro de corpo máximo de 300 KB. Registros inválidos são enumerados, duplicidades normalizadas são eliminadas e a origem csv é persistida. A importação não navega pelos domínios na requisição. Com auto_analyze=true, cria tarefas persistidas, respeitando a cota da fila.

Agendamentos: um por domínio, intervalo de 1 a 8.760 horas, pausa/retomada, próximos/últimos horários e último erro. Worker consulta a cada 30s quando ocioso. No PostgreSQL usa SELECT FOR UPDATE SKIP LOCKED e mantém o lock durante a coleta e persistência. Reinício após rollback permite tentar novamente; após commit calcula o próximo horário a partir do momento atual, sem recuperar execuções antigas em rajada. Interrupção do worker durante coleta pode repetir uma observação após reinício; não há exatamente uma vez em toda falha possível.

RIPEstat é um adaptador opcional de infraestrutura atrás de uma Protocol Python. Usa endpoints fixos, IP público validado e o mesmo coletor SSRF. Não produz achados artificiais quando desabilitado. Fontes externas comerciais exigem implementação específica e não estão incluídas.

## Operação

Alembic aplica DDL congelado, não depende de create_all em startup. create_all aparece apenas nas fixtures de teste. JSON serve para detalhes de coleta heterogêneos, enquanto identificadores, proprietário, score, status e datas são colunas indexadas/relacionais. Backups criptografados e retenção opcional estão implementados; a implantação deve preservar as chaves, manter cópia externa, testar restauração e configurar criptografia de disco e HTTPS.

Logs JSON de requisições não registram senha, cookie, corpo ou segredos. A auditoria registra ações de negócio com usuário e data. O rate limiting local usa IP de conexão e/ou ID de usuário, não confia em X-Forwarded-For recebido diretamente. Sessões são armazenadas somente pelo hash SHA-256 do token aleatório; expiram após oito horas. Há revogação imediata por logout, mas não há tarefa de limpeza de sessões expiradas.

## Evolução: descoberta e layout

A migração 0003 acrescenta fontes, consultas, proveniência, fila e cotas diárias persistidas. O mesmo worker atende fontes, agendamentos e fila sem deixar a fila impedir verificações agendadas. Limites e semântica de falhas estão em AUTOMATION.md. A direção visual escolhida é o estilo de operações Wazuh, implementado originalmente em OperationsOverview.tsx/operations.css, conforme DESIGN.md.
