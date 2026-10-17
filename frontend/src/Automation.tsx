import { useEffect, useState } from "react";
import { Activity, Database, Pause, Play, RefreshCw } from "lucide-react";
import { api, errorMessage } from "./api";

type Action = (fn: () => Promise<void>) => Promise<void>;
interface CatalogSource {
  name: string;
  url: string;
  format: string;
  permission_reference: string;
  homepage: string;
  limitation: string;
}
interface Catalog {
  sources: CatalogSource[];
  allowed_hosts: string[];
  daily_limit: number;
  delay_seconds: number;
  queue_limit: number;
}
interface Feed {
  id: number;
  name: string;
  url: string;
  enabled: boolean;
  auto_analyze: boolean;
  batch_size: number;
  interval_hours: number;
  next_run: string;
  last_error: string;
}
interface Job {
  id: number;
  domain: string;
  status: string;
  attempts: number;
  error: string;
  analysis_id: number | null;
}
interface Queue {
  counts: Record<string, number>;
  used_today: number;
  daily_limit: number;
  jobs: Job[];
}
interface Run {
  id: number;
  feed: string;
  created: string;
  status: string;
  counts: Record<string, number>;
  error: string;
  sha256: string;
}
const statuses: Record<string, string> = {
  queued: "Na fila",
  paused: "Pausado",
  done: "Concluído",
  failed: "Falha",
};

export function Automation({
  revision,
  busy,
  act,
}: {
  revision: number;
  busy: boolean;
  act: Action;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true,
      pending = false;
    const controller = new AbortController();
    async function refresh() {
      if (pending) return;
      pending = true;
      try {
        const [c, f, q, r] = await Promise.all([
          api.get<Catalog>("/discovery/catalog", { signal: controller.signal }),
          api.get<Feed[]>("/discovery/feeds", { signal: controller.signal }),
          api.get<Queue>("/discovery/jobs", { signal: controller.signal }),
          api.get<Run[]>("/discovery/runs", { signal: controller.signal }),
        ]);
        if (live) {
          setCatalog(c.data);
          setFeeds(f.data);
          setQueue(q.data);
          setRuns(r.data);
          setError("");
        }
      } catch (e) {
        if (live) setError(errorMessage(e));
      } finally {
        pending = false;
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => {
      live = false;
      clearInterval(timer);
      controller.abort();
    };
  }, [revision]);
  return (
    <section className="panel automation-panel">
      <div className="panel-title">
        <div>
          <span className="eyebrow">DESCOBRIR → DEDUPLICAR → ANALISAR</span>
          <h2>Descoberta automática</h2>
          <p>
            Fontes públicas selecionadas, fila persistida e coleta com limites.
          </p>
        </div>
        <Activity size={21} />
      </div>
      <div className="automation-body">
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <div className="automation-metrics">
          <div>
            <span>Na fila</span>
            <strong>{queue ? (queue.counts.queued ?? 0) : "—"}</strong>
          </div>
          <div>
            <span>Concluídos</span>
            <strong>{queue ? (queue.counts.done ?? 0) : "—"}</strong>
          </div>
          <div>
            <span>Falhas</span>
            <strong>{queue ? (queue.counts.failed ?? 0) : "—"}</strong>
          </div>
          <div>
            <span>Tentativas hoje (UTC)</span>
            <strong>
              {queue?.used_today ?? "—"}
              <small> / {queue?.daily_limit ?? "—"}</small>
            </strong>
          </div>
        </div>
        <p className="muted">
          O worker consulta as fontes e analisa candidatos sem exigir cliques
          por domínio. Intervalo mínimo entre análises:{" "}
          {catalog?.delay_seconds ?? "—"}s. Atualização deste painel a cada 10s.
          A origem em lista comunitária não aumenta o score e não comprova
          irregularidade.
        </p>
        <div className="row-actions automation-actions">
          <button
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api.post("/discovery/queue");
              })
            }
          >
            <Play size={15} /> Enfileirar até 100 domínios sem análise
          </button>
          <button
            disabled={busy || !queue?.counts.queued}
            onClick={() =>
              act(async () => {
                await api.post("/discovery/queue/pause");
              })
            }
          >
            <Pause size={15} /> Pausar fila atual
          </button>
          <button
            disabled={busy || !queue?.counts.paused}
            onClick={() =>
              act(async () => {
                await api.post("/discovery/queue/resume");
              })
            }
          >
            <Play size={15} /> Retomar fila pausada
          </button>
        </div>
        {catalog?.sources.map((source) => {
          const active = feeds.some((f) => f.url === source.url);
          return (
            <article className="feed-suggestion" key={source.url}>
              <div>
                <span className="tag">FONTE PÚBLICA PESQUISADA</span>
                <h3>{source.name}</h3>
                <p>{source.limitation}</p>
                <a href={source.homepage} target="_blank" rel="noreferrer">
                  Consultar projeto e origem ↗
                </a>
                <details>
                  <summary>Licença e atribuição</summary>
                  <p>{source.permission_reference}</p>
                </details>
              </div>
              <button
                className="primary"
                disabled={busy || active}
                onClick={() =>
                  act(async () => {
                    await api.post("/discovery/feeds", {
                      ...source,
                      enabled: true,
                      auto_analyze: true,
                      batch_size: 50,
                      interval_hours: 24,
                    });
                  })
                }
              >
                <Database size={15} />
                {active ? "Fonte cadastrada" : "Ativar busca automática"}
              </button>
            </article>
          );
        })}
        <details className="custom-feed">
          <summary>Adicionar outra fonte autorizada</summary>
          <p className="muted">
            Hosts permitidos pelo operador:{" "}
            {catalog?.allowed_hosts.join(", ") || "nenhum"}. Até 10 fontes por
            usuário.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget;
              const f = new FormData(form);
              act(async () => {
                await api.post("/discovery/feeds", {
                  name: f.get("name"),
                  url: f.get("url"),
                  format: f.get("format"),
                  permission_reference: f.get("permission"),
                  interval_hours: Number(f.get("hours")),
                  batch_size: Number(f.get("batch")),
                  auto_analyze: f.has("analyze"),
                  enabled: true,
                });
                form.reset();
              });
            }}
          >
            <div className="form-grid">
              <label>
                Nome
                <input name="name" minLength={3} maxLength={150} required />
              </label>
              <label>
                URL HTTPS
                <input name="url" type="url" maxLength={2048} required />
              </label>
              <label>
                Formato
                <select name="format">
                  <option value="csv">CSV com coluna domain</option>
                  <option value="json">JSON: array de domínios</option>
                  <option value="domains">Um domínio por linha</option>
                  <option value="hosts">Hosts (0.0.0.0 domínio)</option>
                </select>
              </label>
              <label>
                Intervalo de consulta (horas)
                <input
                  name="hours"
                  type="number"
                  min={1}
                  max={8760}
                  defaultValue={24}
                  required
                />
              </label>
              <label>
                Candidatos por consulta
                <input
                  name="batch"
                  type="number"
                  min={1}
                  max={100}
                  defaultValue={50}
                  required
                />
              </label>
            </div>
            <label>
              Referência da licença ou autorização
              <textarea
                name="permission"
                minLength={15}
                maxLength={2000}
                required
              />
            </label>
            <label className="inline-check">
              <input type="checkbox" name="analyze" defaultChecked /> Analisar
              novos candidatos automaticamente
            </label>
            <button className="primary" disabled={busy}>
              Cadastrar fonte
            </button>
          </form>
        </details>
        {feeds.map((feed) => (
          <div className="feed-row" key={feed.id}>
            <div>
              <strong>{feed.name}</strong>
              <p>
                {feed.enabled ? "Ativa" : "Pausada"} · {feed.batch_size}{" "}
                candidatos por consulta · a cada {feed.interval_hours}h ·
                próxima: {new Date(feed.next_run).toLocaleString("pt-BR")}
              </p>
              {feed.last_error && <p className="warning">{feed.last_error}</p>}
            </div>
            <button
              disabled={busy}
              onClick={() =>
                act(async () => {
                  await api.patch(`/discovery/feeds/${feed.id}/state`, {
                    enabled: !feed.enabled,
                  });
                })
              }
            >
              {feed.enabled ? "Pausar fonte" : "Retomar fonte"}
            </button>
          </div>
        ))}
        <p className="muted">
          Pausar uma fonte interrompe novas importações. A fila atual é pausada
          separadamente; uma coleta já em andamento pode concluir.
        </p>
        <h3>
          Últimas tarefas <span className="muted">· até 100</span>
        </h3>
        {queue?.jobs.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>DOMÍNIO</th>
                  <th>ESTADO</th>
                  <th>TENTATIVAS</th>
                  <th>AÇÃO</th>
                </tr>
              </thead>
              <tbody>
                {queue.jobs.map((job) => (
                  <tr key={job.id}>
                    <td>
                      {job.domain}
                      {job.error && (
                        <small className="block warning">{job.error}</small>
                      )}
                    </td>
                    <td>
                      <span
                        className={
                          "badge " +
                          (job.status === "failed"
                            ? "high"
                            : job.status === "done"
                              ? "low"
                              : "medium")
                        }
                      >
                        {statuses[job.status] ?? job.status}
                      </span>
                    </td>
                    <td>{job.attempts}</td>
                    <td>
                      {job.status !== "done" && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            act(async () => {
                              await api.post(
                                `/discovery/jobs/${job.id}/action`,
                                {
                                  action:
                                    job.status === "queued"
                                      ? "pause"
                                      : job.status === "paused"
                                        ? "resume"
                                        : "retry",
                                },
                              );
                            })
                          }
                        >
                          <RefreshCw size={13} />
                          {job.status === "queued"
                            ? "Pausar"
                            : job.status === "paused"
                              ? "Retomar"
                              : "Tentar novamente"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">
            Nenhum domínio na fila. Ative uma fonte ou importe um CSV com
            análise automática.
          </p>
        )}
        <details className="custom-feed">
          <summary>Histórico das últimas consultas às fontes</summary>
          {runs.length ? (
            runs.map((run) => (
              <div className="rule-row" key={run.id}>
                <strong>
                  {run.feed} · {run.status}
                </strong>
                <p>{new Date(run.created).toLocaleString("pt-BR")}</p>
                <pre>{JSON.stringify(run.counts, null, 2)}</pre>
                {run.error && <p className="warning">{run.error}</p>}
                <small className="muted hash">
                  SHA-256: {run.sha256 || "Sem documento coletado"}
                </small>
              </div>
            ))
          ) : (
            <p className="muted">Nenhuma consulta executada pelo worker.</p>
          )}
        </details>
      </div>
    </section>
  );
}
