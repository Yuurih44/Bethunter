import { useEffect, useState } from "react";
import { api, errorMessage } from "./api";
type Comparison = {
  available: boolean;
  reason?: string;
  previous?: { id: number; created: string };
  score_delta?: number;
  added_ips?: string[];
  removed_ips?: string[];
  notice?: string;
  changes: { field: string; before: unknown; after: unknown }[];
};
const names: Record<string, string> = {
  ips: "IPs públicos",
  tls: "Certificado TLS",
  http_hops: "Cadeia HTTP",
  content_sha256: "Hash do conteúdo",
  content_bytes: "Tamanho do conteúdo",
  asns: "ASNs",
  prefix: "Prefixo de rede",
  activity: "Contexto da atividade",
  terms: "Termos",
  operator_signals: "Sinais operacionais",
  collection: "Coleta",
  score: "Score",
  classification: "Classificação",
  rule_version: "Regra",
  factors: "Fatores",
  regulatory_status: "Estado regulatório",
  regulatory_document: "Documento regulatório",
  regulatory_version: "Versão regulatória",
};
function show(value: unknown) {
  return value == null
    ? "Não coletado"
    : typeof value === "object"
      ? JSON.stringify(value, null, 2)
      : String(value);
}
export function AnalysisComparison({
  id,
  revision,
}: {
  id: number;
  revision: number;
}) {
  const [open, setOpen] = useState(false),
    [data, setData] = useState<Comparison | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    let live = true;
    setData(null);
    setError("");
    api
      .get<Comparison>(`/analyses/${id}/compare`)
      .then((r) => {
        if (live) setData(r.data);
      })
      .catch((e) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [id, revision, open]);
  return (
    <section className="verdict">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Ocultar comparação" : "Comparar com análise anterior"}
      </button>
      {open && (
        <>
          {error && <p className="error">{error}</p>}
          {!data && !error && <p>Comparando registros…</p>}
          {data && !data.available && <p>{data.reason}</p>}
          {data?.available && (
            <>
              <h3>Mudanças desde a análise #{data.previous?.id}</h3>
              <p>
                Variação do score: {(data.score_delta ?? 0) >= 0 ? "+" : ""}
                {data.score_delta}. IPs adicionados:{" "}
                {data.added_ips?.join(", ") || "nenhum"}. IPs removidos:{" "}
                {data.removed_ips?.join(", ") || "nenhum"}.
              </p>
              {data.changes.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Indicador</th>
                        <th>Antes</th>
                        <th>Agora</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.changes.map((c) => (
                        <tr key={c.field}>
                          <td>{names[c.field] ?? c.field}</td>
                          <td>
                            <pre>{show(c.before)}</pre>
                          </td>
                          <td>
                            <pre>{show(c.after)}</pre>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p>Nenhuma mudança nos indicadores comparados.</p>
              )}
              <small>{data.notice}</small>
            </>
          )}
        </>
      )}
    </section>
  );
}
export function ReportIntegrity({
  id,
  revision,
}: {
  id: number;
  revision: number;
}) {
  const [data, setData] = useState<{
      status: string;
      verified: boolean;
      notice?: string;
      reason?: string;
    } | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    setData(null);
    setError("");
  }, [id, revision]);
  return (
    <div>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            const r = await api.get(`/reports/${id}/integrity`);
            setData(r.data);
          } catch (e) {
            setError(errorMessage(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Conferindo…" : "Verificar integridade"}
      </button>
      {error && <small className="error">{error}</small>}
      {data && (
        <p className={data.verified ? "muted" : "warning"}>
          {data.verified
            ? "SHA-256 dos bytes preservados confere."
            : data.reason || "Divergência de hash detectada."}
          <small className="block">{data.notice}</small>
        </p>
      )}
    </div>
  );
}
