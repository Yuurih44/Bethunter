import { useEffect, useState } from "react";
import { api, errorMessage } from "./api";
import { AutomationHealth } from "./AutomationHealth";
type Policy = {
  enabled: boolean;
  recurring_hours: number;
  create_cases: boolean;
  prepare_reports: boolean;
  minimum_score: number;
};
type AutopilotStatus = {
  automatic_setup: boolean;
  enabled: boolean;
  last_reconciliation: {
    status: string;
    checked: string;
    queued?: number;
    retried?: number;
  } | null;
  daily_limit: number;
  delay_seconds: number;
};
type Run = {
  analysis_id: number;
  domain: string;
  case_id: number | null;
  report_id: number | null;
  details: {
    status: string;
    error?: string;
    reason?: string;
    report_job_id?: number;
  };
};
export function Workflow({
  revision,
  busy,
  act,
}: {
  revision: number;
  busy: boolean;
  act: (fn: () => Promise<void>) => Promise<void>;
}) {
  const [status, setStatus] = useState<AutopilotStatus | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null),
    [runs, setRuns] = useState<Run[]>([]),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true,
      pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      await Promise.all([
        api.get<Policy>("/automation/workflow"),
        api.get<Run[]>("/automation/history"),
        api.get<AutopilotStatus>("/automation/status"),
      ])
        .then(([p, r, s]) => {
          if (live) {
            setPolicy(p.data);
            setRuns(r.data);
            setStatus(s.data);
            setError("");
          }
        })
        .catch((e) => {
          if (live) setError(errorMessage(e));
        })
        .finally(() => {
          pending = false;
        });
    }
    void load();
    const timer = setInterval(() => void load(), 15000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [revision]);
  return (
    <section className="panel case-form">
      <AutomationHealth revision={revision} busy={busy} act={act} />
      <h2>Fluxo automático de investigação</h2>
      <p>
        Cada nova coleta pode agendar monitoramento e preparar um caso com PDF
        quando houver indicadores suficientes. Casos encerrados são respeitados.
        Não há conclusão jurídica nem envio automático.
      </p>
      {error && <p className="error">{error}</p>}
      {status && (
        <div className="verdict">
          <strong>
            {status.enabled ? "Automação habilitada" : "Automação pausada"}
          </strong>
          <p>
            Fontes públicas são configuradas automaticamente quando permitido
            pelo servidor. Novos domínios entram na fila e o inventário anterior
            recebe monitoramento.
          </p>
          <p>
            Última passagem do worker:{" "}
            {status.last_reconciliation
              ? new Date(status.last_reconciliation.checked).toLocaleString(
                  "pt-BR",
                )
              : "Ainda não registrada — aguardando worker"}
            .
          </p>
          <small>
            Cota compartilhada de {status.daily_limit} tentativas por dia;
            intervalo mínimo de {status.delay_seconds}s. Inicialização
            automática:{" "}
            {status.automatic_setup
              ? "habilitada"
              : "desabilitada pelo operador"}
            .
          </small>
        </div>
      )}
      {policy && (
        <form
          key={JSON.stringify(policy)}
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void act(async () => {
              await api.put("/automation/workflow", {
                enabled: f.has("enabled"),
                recurring_hours: Number(f.get("hours")),
                minimum_score: Number(f.get("score")),
                create_cases: f.has("cases"),
                prepare_reports: f.has("reports"),
              });
            });
          }}
        >
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="enabled"
              defaultChecked={policy.enabled}
            />
            Ativar toda a automação desta conta
          </label>
          <div className="form-grid">
            <label>
              Intervalo do monitoramento (horas)
              <input
                type="number"
                name="hours"
                min={1}
                max={8760}
                required
                defaultValue={policy.recurring_hours}
              />
            </label>
            <label>
              Score mínimo para abrir caso
              <input
                type="number"
                name="score"
                min={0}
                max={100}
                required
                defaultValue={policy.minimum_score}
              />
            </label>
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="cases"
              defaultChecked={policy.create_cases}
            />
            Abrir rascunhos de casos
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="reports"
              defaultChecked={policy.prepare_reports}
            />
            Preparar PDFs para revisão (requer casos)
          </label>
          <small>
            Possível incompatibilidade regulatória também pode abrir um caso.
            Desativar interrompe a descoberta, a fila e o monitoramento desta
            conta. Reativar preserva pausas individuais.
          </small>
          <button disabled={busy} className="primary">
            Salvar automação
          </button>
        </form>
      )}
      <h3>Últimas execuções</h3>
      {runs.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Domínio</th>
                <th>Análise</th>
                <th>Estado</th>
                <th>Artefatos</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.analysis_id}>
                  <td>{r.domain}</td>
                  <td>#{r.analysis_id}</td>
                  <td>
                    {(
                      {
                        applied: "Aplicado",
                        disabled: "Desativado",
                        failed: "Falha",
                        skipped_closed: "Caso encerrado — respeitado",
                      } as Record<string, string>
                    )[r.details.status] ?? r.details.status}
                    {r.details.error && <small>{r.details.error}</small>}
                    {r.details.reason && <small>{r.details.reason}</small>}
                  </td>
                  <td>
                    {r.case_id ? `Caso #${r.case_id}` : "Sem caso"} ·{" "}
                    {r.report_id ? (
                      <a href="/reports">{`PDF #${r.report_id}`}</a>
                    ) : r.details.report_job_id ? (
                      <a href="/reports">{`Tarefa PDF #${r.details.report_job_id}`}</a>
                    ) : (
                      "Sem PDF"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">Nenhuma execução registrada.</p>
      )}
    </section>
  );
}
