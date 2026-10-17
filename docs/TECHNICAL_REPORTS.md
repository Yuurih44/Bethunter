# Relatórios técnicos e evidências

## PDF técnico v2

Em **Investigações**, abra um caso e use **Gerar e baixar PDF**. O modelo técnico inclui:

1. Identificação, escopo, data do snapshot e versão do modelo.
2. Metodologia de coleta pública e limites da preservação.
3. Resumo por domínio, score, classificação e situação da coleta.
4. DNS/IPs, certificado TLS, cadeia HTTP, conteúdo e fatores explicados.
5. Proveniência, fontes regulatórias, datas e hashes disponíveis.
6. Parecer humano, erros e histórico de verificações incluídas.
7. Registro de evidências, pendências de revisão e limitações.

A coleta TLS passa a preservar subject, emissor, número de série, validade, SAN, fingerprint SHA-256 do certificado DER, IP consultado, protocolo e cifra negociados. Esses dados aparecem somente em **novas coletas**; análises antigas não recebem informações inventadas.

Campos não coletados ficam explícitos. Falta de evidência não é prova de ausência de atividade. O relatório não determina crime, não atribui operador por IP/ASN e não envia denúncias.

A versão do modelo participa da deduplicação. Gerar novamente um caso produz o modelo novo quando necessário; PDFs anteriores mantêm seus bytes/hash originais. O limite padrão continua em 50 análises recentes por domínio, snapshot de 2 MB e PDF de 5 MB. O histórico total e eventual truncamento aparecem no documento.

## Comparação entre análises

Em **Domínios → Detalhes**, use **Comparar com análise anterior**. O sistema compara as observações preservadas do mesmo domínio: IPs adicionados/removidos, TLS, redirecionamentos, hash/tamanho do conteúdo, ASN, fatores/score, regra e contexto regulatório. Se houver só uma coleta, isso é informado. A API também aceita previous_id para escolher outra análise anterior do mesmo domínio/proprietário.

Diferença entre observações não comprova comprometimento, mudança de operador ou irregularidade. Nenhuma requisição ao alvo é realizada pela comparação.

## Pacote de evidências

No caso, **Exportar pacote de evidências** gera um ZIP com:

- case.json: snapshot do caso e histórico recente, com os limites declarados.
- documents/ID.bin: bytes originais disponíveis, com extensão neutra.
- README.txt: instruções de manuseio.
- manifest.json: caminhos, tamanhos, SHA-256, proveniência e contagem de documentos indisponíveis.

A exportação verifica os hashes dos documentos e registros estruturados antes de concluir; uma divergência interrompe o download com erro. São incluídos somente documentos da conta ou fontes oficiais públicas referenciadas. Há limite de 20 MB expandidos, 1.000 documentos, duas exportações simultâneas por processo e três solicitações por conta/minuto. Cada exportação concluída é auditada.

O pacote corresponde ao snapshot limitado, não ao banco inteiro. Ele pode conter dados sensíveis de investigação. Os .bin podem conter HTML não confiável: examine como texto em ambiente apropriado, sem executar conteúdo.

### Conferência sem backend

```bash
python3 scripts/verify_evidence.py /caminho/bethunter-case-1-evidence.zip
```

O verificador não extrai nem executa arquivos. Rejeita excesso de tamanho, entradas inesperadas/duplicadas e hashes divergentes. Ele confere os arquivos listados contra o manifesto fornecido. **Não há assinatura digital:** alguém capaz de substituir arquivos e manifesto pode recalcular hashes. Integridade não comprova origem, autoria, veracidade ou cadeia de custódia certificada.

## Integridade do PDF preservado

Em **Relatórios**, use **Verificar integridade**. O sistema recalcula o SHA-256 dos bytes guardados no banco e compara ao registro. PDFs arquivados são identificados como indisponíveis para essa conferência. Essa ação não verifica um arquivo que já esteja no computador do usuário nem certifica o conteúdo jurídico do relatório.
