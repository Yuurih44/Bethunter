# Interface de operações

Direção escolhida pelo usuário: estilo Wazuh, mantendo a identidade BetHunter e tema escuro.

Referências primárias pesquisadas:

- [Navegação do dashboard Wazuh](https://documentation.wazuh.com/current/user-manual/wazuh-dashboard/navigating-the-wazuh-dashboard.html).
- [Fluxos e painéis de threat hunting Wazuh](https://documentation.wazuh.com/current/getting-started/use-cases/threat-hunting.html).

Também foram consideradas referências de Elastic Security e OpenCTI antes da escolha. A implementação visual é original; não reutiliza logo, assets ou código da interface Wazuh e não representa integração ou afiliação com o produto.

## Aplicação da referência

- Navegação agrupada em Monitoramento, Operações e Administração.
- Cabeçalho compacto, breadcrumb com a página atual e botão real de atualização.
- Fundo grafite/azul, painéis planos, tipografia compacta e amarelo para atenção.
- Métricas de inventário no topo, evolução de coletas e distribuição por prioridade.
- Tabela operacional com filtro textual, período e links para a análise correspondente.
- Resumo real da fila automática e relatórios preparados/encaminhamentos declarados.
- Abas funcionais de visão geral e últimas análises; layout responsivo e navegação móvel com fechamento por overlay.
- Sem contadores aleatórios, indicadores de serviços online sem medição ou ações decorativas.

Os filtros do dashboard aplicam-se ao histórico temporal e às até oito análises mais recentes retornadas pela API. O inventário e a distribuição por score mostram o conjunto completo do usuário, explicitamente identificado. Não se apresenta uma lista parcial como histórico exaustivo.

A interface possui build TypeScript/Vite e testes de navegador, incluindo navegação móvel. Consulte VALIDATION.md para o escopo da verificação visual e automatizada.
