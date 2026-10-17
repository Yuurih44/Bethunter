# Fontes e integrações

## SPA/MF

Referências oficiais consultadas na pesquisa:

- [Página da SPA](https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas).
- [Serviço de consulta a empresas autorizadas](https://www.gov.br/pt-br/servicos/consultar-as-empresas-autorizadas-a-operar-apostas-de-quota-fixa).
- [Página de tabela referenciada pelo importador](https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/lista-de-empresas/empresas-autorizadas-1/empresas-autorizadas).

A pesquisa encontrou a referência da tabela, mas a tentativa de abertura durante esta sessão retornou **404**. Isso não foi convertido em alegação sobre empresas ou regulação. A consulta ao vivo do backend não pôde ser validada por restrições de rede. O importador tem testes com fixtures sintéticas e registra falha se a página não existe, muda de formato ou não fornece data verificável.

O adaptador reconhece linhas HTML de tabela com colunas número/empresa/CNPJ/marcas/domínios/atos e data `documentModified .value`. Extrai apenas domínios `.bet.br` listados expressamente nessa tabela. Essa extensão serve para reconhecer o formato da fonte, **não para atribuir legalidade** a domínios pesquisados. Nenhum resultado é determinado apenas pelo sufixo.

A data identificada é a atualização documental da página; não garante vigência individual de cada ato. O importador não interpreta PDFs ou imagens nem presume autorização atual a partir de documento antigo. Estados distintos: imported, undated e failed. Mesmo imported exige idade aceitável e revisão de escopo.

`OFFICIAL_SOURCE_URL` permite ajustar a página da tabela caso o portal oficial mude. O backend valida que o hostname inicial e todos os saltos são www.gov.br/gov.br. Não configure URLs de sites privados ou listas de terceiros como oficiais. A variável é configuração de servidor, não campo fornecido por usuários.

Não existe afirmação de que a lista consultada resolve autorizações estaduais, liminares, revogações ou alterações normativas atuais. Esses dados devem ser registrados e revisados nas notas do caso e na justificativa das regras. Fontes indisponíveis ou sem data não produzem verificação regulatória atual.

## RIPEstat

Adaptador opcional `RIPEstatProvider`, desativado por padrão (`ENRICH_ASN=false`). Consulte as condições do provedor antes de usar em seu contexto e monitore limites. A coleta é pontual, restrita ao primeiro IP público observado no domínio analisado.

- [Network Info](https://stat.ripe.net/docs/data-api/api-endpoints/network-info.html): prefixo e ASN anunciante de um IP, baseado em RIPE RIS.
- [Prefix Overview](https://stat.ripe.net/docs/data-api/api-endpoints/prefix-overview): organizações associadas aos ASNs anunciantes.

Armazenam-se URL, data da coleta, hash da resposta, IP, prefixo, ASNs e holders disponíveis. Falha gera erro/ausência explícita, não score de suspeita. Os resultados são observações de roteamento; não comprovam hospedagem ou operador comum.

## DNS, TLS e HTTP

DNS público é consultado pelo resolvedor configurado no host/container. Apenas A/AAAA são consultados no MVP. TLS é uma conexão ao IP validado com nome original e validação padrão do certificado. HTTP parte da raiz HTTPS e segue redirecionamentos públicos validados. HTML é lido como texto estático; não se executa JavaScript.

O histórico começa com as coletas próprias. Não há integração ativa com DNS passivo comercial, Certificate Transparency, mecanismos de busca, serviços de reputação pagos ou WHOIS histórico. Nenhuma credencial é solicitada ou inventada para esses serviços.

## Expansão

A interface `InfrastructureProvider` em `backend/app/providers.py` é o contrato de enriquecimento por IP. Provedores novos devem limitar destinos, tempo, tamanho e concorrência, guardar fonte/data, usar segredos apenas no servidor e testar com mocks. Fixtures de demonstração não devem alimentar métricas reais. Para descoberta via terceiros é necessário um adaptador específico, checagem de licença/termos, quota e registro de origem; a versão atual importa CSV autorizado e consulta arquivos públicos configurados em CSV/JSON/domains/hosts, com catálogo StevenBlack gambling-only, origem e fila limitada. Consulte AUTOMATION.md.

## Descoberta comunitária pesquisada

A lista [StevenBlack gambling-only](https://github.com/StevenBlack/hosts/tree/master/alternates/gambling-only) foi pesquisada e aberta pela ferramenta web. O projeto documenta a [licença MIT](https://github.com/StevenBlack/hosts/blob/master/license.txt) e as fontes de apostas. O catálogo da aplicação guarda referência/atribuição, sem redistribuir o dataset. A lista é internacional e não é uma fonte regulatória brasileira; a presença não pontua risco. Formatos, limites, origem e estado de verificação ao vivo estão em [AUTOMATION.md](AUTOMATION.md).

## Contexto normativo reconhecido em 17/10/2026

A [página oficial da SPA](https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas) apresenta aviso sobre a MP 1.394/2026. O [texto oficial](https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/mpv/mpv1394.htm) e as [explicações da SPA](https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/medida-provisoria-ndeg-1-394-2026-entenda-as-novas-regras-para-as-apostas-de-quota-fixa) devem ser examinados para escopo, exceções e prazos; o software não decide enquadramento jurídico individual.

O adaptador `spa-alert-mp1394-2026-v1` reconhece o aviso explícito em cabeçalhos da SPA, registra URL, consulta, hash e vigência temporal, e exige consulta nas últimas 24h por padrão. Aviso ausente, fonte indisponível, consulta futura/vencida ou formato desconhecido resulta em situação não verificada. Uma alteração de norma exige revisão do adaptador, não extrapolação automática.

A tabela usada passou para [a página de empresas](https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/transparencia-ativa-processos-de-autorizacao-de-apostas-de-quota-fixa/empresas-autorizadas). Ela é documental/histórica e não basta para declarar autorização atual. O contexto é armazenado separadamente; a presença histórica nunca cria um veredito de legalidade. Termos de apostas com alerta oficial geram somente possível incompatibilidade para revisão de atividade, território e exceções. Sem termos observados, o enquadramento continua não confirmado.

As URLs oficiais documentam a proveniência da integração. A verificação operacional depende da consulta registrada pelo backend; referências documentais não substituem uma coleta atual. A suíte usa mocks para testes determinísticos.
