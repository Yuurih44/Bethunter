# Modelo de ameaças

## Ativos e atores

Ativos: credenciais, cookies, casos, evidências, PDFs, trilha de auditoria, integridade de regras/fontes e rede interna da implantação. Atores considerados: usuário não autenticado, usuário autenticado malicioso, página pública hostil, DNS hostil e operador do banco. O administrador de infraestrutura é uma parte privilegiada; a aplicação não o impede de alterar banco ou arquivos.

| Ameaça | Controle implementado | Limite residual |
|---|---|---|
| SSRF / metadados / redes internas | Host normalizado, rejeição de IP/portas/credenciais/reservados, todas as respostas DNS públicas, pinning IP, SNI original e revalidação por salto | Defesa em profundidade recomenda política de egress; alterações futuras no coletor devem manter pinning |
| DNS rebinding / redirecionamento privado | Não há resolução implícita HTTP após validação; nova validação em cada salto | Não cobre comprometimento da rede do host ou kernel |
| Respostas hostis / disponibilidade | Limites de corpo e resposta, compressão recusada, timeouts, semáforo e agendamento mínimo | Parsing/PDF e consultas síncronas podem consumir CPU; manter instalação pequena e monitorada |
| Roubo de senha / sessão | Argon2id; cookie HttpOnly, SameSite Strict, Secure em HTTPS; token aleatório persistido por hash e expiração de 8h | TOTP com segredo criptografado e recuperação de uso único; TLS deve ser configurado na implantação |
| CSRF | Cookie Strict + token por sessão + Origin exato em mutações | Não substitui prevenção de XSS |
| SQL Injection | SQLAlchemy com parâmetros, IDs tipados e validação Pydantic | Acesso administrativo ao banco permanece privilegiado |
| XSS | React escapa texto; nenhum dangerouslySetInnerHTML; CSP em Nginx; PDF escapa HTML e bloqueia recursos externos | Conteúdo exportado deve continuar tratado como não confiável |
| IDOR / vazamento entre usuários | owner_id nas raízes e validação em todos os acessos a filhos | Sem colaboração multiusuário sobre o mesmo caso |
| Escalação de privilégio | Convite vinculado ao email, uso único e papéis limitados; viewer só altera sua própria segurança; administração exige MFA; promoção offline auditada | Quem executa comandos no container tem autoridade administrativa |
| Brute force | Limites locais por IP/operação, contador persistido por identidade, hash fictício e concorrência Argon2 limitada | Limites IP locais sem Redis; contador por identidade compartilhado via banco; conta pode sofrer negação temporária de login |
| Fonte antiga / falsa atribuição | Datas e hash, última falha prevalece, ausência não pontua, TLD não autoriza, revisão humana | Lista não resolve decisões judiciais/jurisdições e vigência jurídica |
| Adulteração de evidência | Hash do payload e PDF preservado com hash; snapshot e auditoria | Sem assinatura/ancoragem externa; DB admin pode adulterar |
| Vazamento de segredos | .env ignorado, logs sem cookies/password/body, sem credenciais no frontend | Política operacional e varredura de segredos do repositório ainda necessárias |

## Fluxos de confiança

A entrada do usuário nunca vira SQL ou shell. URLs são reduzidas a hostname para coleta. O coletor faz apenas GET público em portas padrão, não envia autenticação nem executa scripts. RIPEstat usa endpoint fixo; não aceita URL arbitrária de API pelo navegador. O importador oficial restringe portal/redirects a gov.br e falha quando não reconhece formato.

O PDF não faz solicitações externas. A lista de bloqueio é download explícito, não execução de comandos nem modificação de rede. Denúncias são preparadas, sem enviar mensagens a terceiros.

## Operação segura

Use HTTPS e COOKIE_SECURE=true, origem exata, banco sem exposição pública, backups protegidos e controle de acesso ao host. Dados de investigação e notas podem conter dados pessoais; defina finalidade, minimização e retenção. Este documento não é uma certificação de segurança nem uma análise jurídica de conformidade.

Antes de escalar: rate limiting compartilhado, monitoramento externo, assinatura de evidências e auditoria externa. Fila durável, cotas, paginação, recuperação por email e agregações SQL foram adicionadas; precisam de validação de carga em PostgreSQL.

## Descoberta e fila

Fontes são limitadas por host configurado pelo operador, HTTPS obrigatório em todos os saltos, DNS/IP público validado e fixado, resposta sem compressão até 2 MB e timeout total de 30s. Registros inválidos são contados; documento vazio ou formato incompatível falha explicitamente. Lotes de até 100 e fila de até 1.000 por usuário por padrão evitam transformar a importação em varredura indiscriminada. As tentativas da fila têm cota diária persistida e atraso mínimo; fontes possuem intervalo mínimo de uma hora. Uma referência de licença não prova por si só autorização de uso, e o operador deve revisar o arquivo. A origem em lista comunitária não pontua risco nem autoriza atribuição criminal.

## Controles adicionais de conta

Convites não comprovam posse do email. O terminal do operador é a fronteira para provisionamento e recuperação excepcional de MFA. Segredos TOTP dependem da preservação da chave Fernet. Códigos e convites não entram em auditoria; somente hashes são persistidos. Consulte [SECURITY.md](SECURITY.md). Host e HTTPS são validados pela configuração; a sessão também expira por inatividade sem interação. Esses controles possuem testes automatizados em PostgreSQL; cargas concorrentes maiores ainda exigem avaliação específica.

A reconciliação automática é habilitada por padrão e limitada por conta/lote/cota. Ela não aumenta a allowlist, não habilita contas inativas ou de leitura, não retoma itens pausados individualmente e não declara fontes como verificadas sem coleta. As tentativas automáticas da fila são limitadas a três, com espera crescente. Descoberta comunitária automática deve ser desligada com AUTO_SETUP se a política do operador exigir provisionamento manual; a pausa geral interrompe execução de tarefas da conta.

A revisão em [REVIEW.md](REVIEW.md) identifica pendências operacionais, com correções implementadas para privilégios do banco, subprocesso PDF, proxy e retenção; a validação ao vivo segue pendente. No coletor, keep-alive foi desativado para impedir compartilhamento de conexão TLS por hosts distintos com o mesmo IP fixado. Testes em banco persistente agora exigem nome de teste e autorização explícita de reset, para proteger dados reais.
