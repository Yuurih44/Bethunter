"""Escaped, self-contained technical reports. No external HTML/CSS resources."""

import json
from html import escape
from weasyprint import HTML

TEMPLATE_VERSION = "technical-report-v2"


def deny_resources(url, *args, **kwargs):
    raise ValueError("Relatórios não carregam recursos externos")


def value(text):
    if text is None or text == "":
        return "Não coletado / não informado"
    if isinstance(text, (dict, list, tuple)):
        text = json.dumps(text, ensure_ascii=False, default=str)
    return escape(str(text))


def table(headers, rows):
    return (
        "<table><thead><tr>"
        + "".join("<th>" + value(h) + "</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + value(cell) + "</td>" for cell in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table>"
    )


def report_html(snapshot):
    raw_case = snapshot.get("Caso", {})
    case = raw_case if isinstance(raw_case, dict) else {}
    parts = [
        '<header><div class="brand">BETHUNTER / INTELIGÊNCIA DE FONTES PÚBLICAS</div><h1>Relatório técnico de investigação</h1><p>Documento de apoio à revisão humana • '
        + value(snapshot.get("Preparação"))
        + "</p></header>"
    ]
    parts += [
        "<h2>1. Identificação e escopo</h2>",
        table(
            ["Campo", "Registro"],
            [
                ("Identificador do caso", case.get("id")),
                ("Título", case.get("title")),
                (
                    "Estado / prioridade",
                    str(case.get("status", "")) + " / " + str(case.get("priority", "")),
                ),
                ("Preparação do snapshot", snapshot.get("Coleta do relatório")),
                ("Modelo", snapshot.get("Modelo do relatório", TEMPLATE_VERSION)),
            ],
        ),
        '<p class="notice">Prioridade de investigação não é probabilidade de crime. Este documento não determina ilegalidade nem comprova autoria ou controle comum de domínios.</p>',
        "<h2>2. Metodologia e preservação</h2><p>Coleta pontual em fontes públicas: resolução DNS, verificação TLS e HTTP com redirecionamentos limitados. Os resultados abaixo refletem os registros preservados; uma etapa ausente ou incompleta não é uma conclusão negativa. As datas das análises diferem da data de preparação deste documento.</p><p>SHA-256 permite conferir os bytes exportados, mas não comprova autoria, veracidade ou assinatura digital. Os arquivos brutos, quando disponíveis, podem ser exportados separadamente no pacote de evidências do caso.</p>",
    ]
    records = snapshot.get("Domínios e histórico", [])
    parts.append("<h2>3. Resumo das observações</h2>")
    rows = []
    for record in records:
        history = record.get("history", [])
        last = history[-1] if history else {}
        result = last.get("result", {})
        rows.append(
            (
                record.get("domain"),
                last.get("created"),
                str(last.get("score", "—")) + "/100",
                last.get("classification"),
                result.get("technical", {}).get("collection_status"),
                result.get("verdict", {}).get("label"),
            )
        )
    parts.append(
        table(["Domínio", "Última coleta", "Score", "Classificação", "Coleta", "Avaliação"], rows)
        if rows
        else "<p>Nenhum domínio incluído neste snapshot.</p>"
    )
    for number, record in enumerate(records, 1):
        history = record.get("history", [])
        last = history[-1] if history else {}
        result = last.get("result", {})
        tech = result.get("technical", {})
        regulation = result.get("regulation", {})
        context = regulation.get("normative_context", {})
        parts += [
            '<section class="domain"><h2>4.'
            + str(number)
            + ". Domínio: "
            + value(record.get("domain"))
            + "</h2>",
            "<p>Histórico incluído: "
            + value(record.get("history_included", len(history)))
            + " de "
            + value(record.get("history_count", len(history)))
            + " análises. Análises anteriores não incluídas permanecem no banco.</p>",
            "<h3>Dados de rede e conteúdo</h3>",
            table(
                ["Indicador", "Observação"],
                [
                    (
                        "Análise / data",
                        str(last.get("id", "—")) + " / " + str(last.get("created", "—")),
                    ),
                    ("IPs públicos", tech.get("ips")),
                    ("Situação da coleta", tech.get("collection_status")),
                    ("ASN / prefixo", tech.get("infrastructure")),
                    ("SHA-256 do conteúdo", tech.get("content_sha256")),
                    ("Tamanho coletado (bytes)", tech.get("bytes")),
                    ("Contexto de atividade", tech.get("activity_context")),
                    ("Termos observados", tech.get("matched_terms")),
                    ("Ações observadas", tech.get("operator_signals")),
                ],
            ),
            "<h3>Certificado TLS</h3>",
            table(["Campo", "Observação"], [(k, v) for k, v in tech.get("tls", {}).items()])
            if tech.get("tls")
            else "<h3>Certificado TLS</h3><p>Sem certificado preservado nesta análise. Consulte os erros de coleta.</p>",
            "<h3>Cadeia HTTP observada</h3>",
            table(
                ["URL", "IP validado", "HTTP"],
                [(h.get("url"), h.get("ip"), h.get("status")) for h in tech.get("hops", [])],
            )
            if tech.get("hops")
            else "<h3>Cadeia HTTP observada</h3><p>Sem saltos HTTP preservados.</p>",
            "<h3>Fatores da prioridade</h3>",
            table(
                ["Indicador", "Peso", "Justificativa"],
                [
                    (f.get("key"), f.get("weight"), f.get("explanation"))
                    for f in result.get("factors", [])
                ],
            )
            if result.get("factors")
            else "<h3>Fatores da prioridade</h3><p>Nenhum fator pontuado. Isso não substitui a verificação de completude.</p>",
            "<p>Regra aplicada: " + value(result.get("rule_version")) + "</p>",
            "<h3>Contexto regulatório e proveniência</h3>",
            table(
                ["Campo", "Registro"],
                [
                    ("Estado documental", regulation.get("status")),
                    ("Justificativa", regulation.get("reason")),
                    ("URL da fonte", regulation.get("url") or context.get("url")),
                    ("Consulta à fonte", regulation.get("consulted") or context.get("consulted")),
                    (
                        "Atualização / vigência registrada",
                        regulation.get("document_updated") or context.get("effective_from"),
                    ),
                    (
                        "SHA-256 documental",
                        regulation.get("document_sha256") or context.get("document_sha256"),
                    ),
                    ("Versão do contexto", context.get("version")),
                    ("Origem da descoberta", result.get("discovery")),
                ],
            ),
            "<p>" + value(result.get("verdict", {}).get("explanation")) + "</p>",
            '<h3>Revisão humana registrada</h3><p class="preserve">'
            + value(last.get("review"))
            + "</p>",
            "<h3>Erros e limitações da análise</h3>"
            + table(
                ["Tipo", "Descrição"],
                [("Erro", e) for e in result.get("errors", [])]
                + [("Limitação", e) for e in result.get("limitations", [])],
            ),
            "<h3>Histórico das verificações incluídas</h3>",
            table(
                ["Análise", "Data", "Score", "Classificação", "Parecer"],
                [
                    (
                        a.get("id"),
                        a.get("created"),
                        a.get("score"),
                        a.get("classification"),
                        a.get("review"),
                    )
                    for a in history
                ],
            ),
            "<h3>Registro de evidências</h3>",
            table(
                ["Coleta", "SHA-256 do registro"],
                [(e.get("collected"), e.get("sha256")) for e in record.get("evidence", [])],
            ),
            "<p>IDs dos documentos brutos referenciados na última análise: "
            + value(result.get("raw_document_ids"))
            + "</p></section>",
        ]
    parts += [
        '<h2>5. Notas e conclusão registrada</h2><p class="preserve">'
        + value(snapshot.get("Conclusão técnica"))
        + "</p>",
        "<h2>6. Pendências para revisão</h2><ul><li>Conferir completude e atualidade das coletas e fontes oficiais.</li><li>Verificar atividade efetiva, direcionamento territorial e exceções aplicáveis.</li><li>Revisar os fatores e registrar um parecer humano antes de encaminhamento.</li><li>Conferir o pacote de evidências e seus hashes; manter cópia protegida.</li></ul>",
        "<h2>7. Limitações e encaminhamento</h2><p>"
        + value(snapshot.get("Limitações"))
        + "</p><p>Infraestrutura compartilhada não comprova operador comum. Não houve exploração, acesso autenticado ao alvo ou envio automático de denúncia. Protocolo externo depende de confirmação humana.</p>",
    ]
    if not case and not records:
        parts.append("<h2>Dados complementares</h2><pre>" + value(snapshot) + "</pre>")
    css = """@page {size:A4;margin:19mm 16mm 20mm;@bottom-left {content:"BetHunter • documento técnico para revisão";font-size:8pt;color:#64748b}@bottom-right {content:counter(page) " / " counter(pages);font-size:8pt}} body{font-family:sans-serif;font-size:9pt;color:#182638;line-height:1.45} header{border-top:6px solid #eab308;padding-top:12px;border-bottom:1px solid #cbd5e1} .brand{font-size:8pt;letter-spacing:1px;color:#2563eb} h1{font-size:24pt;line-height:1.2} h2{font-size:13pt;color:#133b62;margin-top:22px;break-after:avoid} h3{font-size:10pt;margin-top:16px;break-after:avoid} table{width:100%;border-collapse:collapse;table-layout:fixed;margin:10px 0;font-size:8pt} th{background:#e8eef5;text-align:left} td,th{padding:6px;border:1px solid #cbd5e1;overflow-wrap:anywhere;vertical-align:top} thead{display:table-header-group} tr{break-inside:avoid} .notice{border-left:4px solid #eab308;background:#fff9e8;padding:10px} .domain{break-before:page} .preserve,pre{white-space:pre-wrap;overflow-wrap:anywhere} pre{font-size:8pt}"""
    return (
        '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>BetHunter | Relatório técnico</title><style>'
        + css
        + "</style><body>"
        + "".join(parts)
        + "</body></html>"
    )


def pdf(snapshot):
    return HTML(string=report_html(snapshot), url_fetcher=deny_resources).write_pdf(
        presentational_hints=False
    )
