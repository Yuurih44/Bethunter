import json
from html import escape
from weasyprint import HTML

def deny_resources(url, *args, **kwargs):
    raise ValueError("Relatórios não carregam recursos externos")

def pdf(snapshot):
    parts = ["<h1>BetHunter | Relatório técnico</h1>"]
    for title, value in snapshot.items():
        text = json.dumps(value,ensure_ascii=False,indent=2,default=str) if not isinstance(value,str) else value
        parts.append("<h2>"+escape(title)+"</h2><pre>"+escape(text)+"</pre>")
    css = "@page {size:A4; margin:20mm; @bottom-center {content:counter(page)}} body {font-family:sans-serif; font-size:10pt;color:#172130} h1 {font-size:20pt} h2 {font-size:12pt;break-after:avoid} pre {white-space:pre-wrap;overflow-wrap:anywhere;font-family:sans-serif;font-size:9pt}"
    return HTML(string="<!doctype html><html lang='pt-BR'><meta charset='utf-8'><style>"+css+"</style>"+"".join(parts)+"</html>",url_fetcher=deny_resources).write_pdf()
