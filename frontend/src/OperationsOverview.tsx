import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  Database,
  FileText,
  Globe,
  Search,
  Shield,
  Workflow,
  AlertTriangle,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { api, errorMessage } from "./api";
import type { Dashboard } from "./types";

const COLORS = ["#3c92ec", "#e7bd54", "#ec8e57", "#df637b"];
const tooltip = {
  background: "#182332",
  border: "1px solid #405269",
  borderRadius: 3,
  color: "#e5eef9",
};
interface QueueSummary {
  counts: Record<string, number>;
  used_today: number;
  daily_limit: number;
}

export function OperationsOverview({ revision }: { revision: number }) {
  const [alerts, setAlerts] = useState<
    { code: string; level: string; message: string }[]
  >([]);
  const [data, setData] = useState<Dashboard | null>(null);
  const [queue, setQueue] = useState<QueueSummary | null>(null);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState("");
  const [query, setQuery] = useState("");
  const [period, setPeriod] = useState("all");
  const [tab, setTab] = useState("overview");
  useEffect(() => {
    let live = true,
      loading = false;
    const controller = new AbortController();
    async function fetch() {
      if (loading) return;
      loading = true;
      try {
        const [d, q, a] = await Promise.all([
          api.get<Dashboard>("/dashboard", { signal: controller.signal }),
          api.get<QueueSummary>("/discovery/jobs", {
            signal: controller.signal,
          }),
          api.get("/operations/alerts", { signal: controller.signal }),
        ]);
        if (live) {
          setData(d.data);
          setQueue(q.data);
          setAlerts(a.data.items);
          setError("");
          setUpdated(new Date().toLocaleTimeString("pt-BR"));
        }
      } catch (e) {
        if (live) setError(errorMessage(e));
      } finally {
        loading = false;
      }
    }
    void fetch();
    const timer = setInterval(() => void fetch(), 15000);
    return () => {
      live = false;
      clearInterval(timer);
      controller.abort();
    };
  }, [revision]);
  const cutoff = period === "all" ? 0 : Date.now() - Number(period) * 86400000;
  const history =
    data?.history.filter(
      (d) => new Date(d.date + "T23:59:59Z").getTime() >= cutoff,
    ) ?? [];
  const recent =
    data?.recent.filter(
      (a) =>
        new Date(a.created).getTime() >= cutoff &&
        ((a.domain ?? "") + " " + a.classification)
          .toLowerCase()
          .includes(query.toLowerCase()),
    ) ?? [];
  const distribution = data?.distribution ?? [];
  const metrics = data
    ? [
        {
          title: "Domínios no inventário",
          value: data.domains,
          subtitle: "Domínios únicos cadastrados",
          icon: Globe,
          tone: "blue",
        },
        {
          title: "Domínios analisados",
          value: data.analyzed,
          subtitle: "Com pelo menos uma coleta",
          icon: Activity,
          tone: "cyan",
        },
        {
          title: "Prioridade elevada",
          value: data.suspect,
          subtitle: "Último score igual ou superior a 50",
          icon: AlertTriangle,
          tone: "amber",
        },
        {
          title: "Aguardando análise",
          value: data.pending,
          subtitle: "Sem análise registrada",
          icon: Search,
          tone: "violet",
        },
      ]
    : [];
  return (
    <div className="operations-overview">
      {alerts.map((a) => (
        <div
          key={a.code}
          className={a.level === "error" ? "error" : "warning"}
          role="status"
        >
          {a.message}
        </div>
      ))}
      <div className="page-title">
        <div>
          <span className="eyebrow">INTELIGÊNCIA / MONITORAMENTO</span>
          <h1>Central de operações</h1>
          <p>
            Visibilidade dos domínios, das coletas e da fila de investigação.
          </p>
        </div>
        <NavLink className="primary" to="/domains">
          <Search size={16} /> Analisar domínio
        </NavLink>
      </div>
      <div
        className="operation-tabs"
        role="tablist"
        aria-label="Visualização do painel"
      >
        <button
          id="overview-tab"
          role="tab"
          aria-selected={tab === "overview"}
          aria-controls="overview-content"
          className={tab === "overview" ? "active" : ""}
          onClick={() => setTab("overview")}
        >
          Visão geral
        </button>
        <button
          id="events-tab"
          role="tab"
          aria-selected={tab === "events"}
          aria-controls="overview-content"
          className={tab === "events" ? "active" : ""}
          onClick={() => setTab("events")}
        >
          Últimas análises
        </button>
        <NavLink to="/discovery">
          Descoberta e automação <ArrowUpRight size={13} />
        </NavLink>
        <span className="updated-at">
          {updated ? "Atualizado às " + updated : "Consultando banco…"}
        </span>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!data ? (
        <div className="empty">
          <Database size={26} />
          <p>
            {error
              ? "Não foi possível carregar os dados."
              : "Carregando os registros do seu usuário…"}
          </p>
        </div>
      ) : (
        <div
          id="overview-content"
          role="tabpanel"
          aria-labelledby={tab === "overview" ? "overview-tab" : "events-tab"}
        >
          <div className="operations-metrics">
            {metrics.map((m) => (
              <article key={m.title} className={"operation-metric " + m.tone}>
                <div className="metric-label">
                  <span>{m.title}</span>
                  <m.icon size={19} />
                </div>
                <strong>{m.value.toLocaleString("pt-BR")}</strong>
                <p>{m.subtitle}</p>
              </article>
            ))}
          </div>
          <div className="inventory-caption">
            <Shield size={13} />
            <span>
              Inventário completo do seu usuário. Score indica prioridade, não
              comprovação de crime.
            </span>
          </div>
          <div className="operations-filter">
            <div className="filter-input">
              <Search size={16} />
              <input
                aria-label="Filtrar últimas análises"
                placeholder="Filtrar as últimas análises por domínio ou classificação…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <label>
              Período dos gráficos e das últimas análises
              <select
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
              >
                <option value="all">Todo o histórico</option>
                <option value="7">Últimos 7 dias</option>
                <option value="30">Últimos 30 dias</option>
              </select>
            </label>
          </div>
          {tab === "overview" && (
            <div className="operations-charts">
              <section className="panel">
                <div className="panel-title">
                  <div>
                    <h2>Evolução das coletas</h2>
                    <p>Análises registradas por dia · período selecionado</p>
                  </div>
                  <span className="tag">
                    {history.reduce((n, d) => n + d.analyses, 0)} COLETAS
                  </span>
                </div>
                {history.length ? (
                  <div className="chart">
                    <ResponsiveContainer width="100%" height={235}>
                      <AreaChart
                        data={history}
                        margin={{ top: 10, right: 8, bottom: 0, left: -20 }}
                      >
                        <defs>
                          <linearGradient
                            id="ops-area"
                            x1="0"
                            y1="0"
                            x2="0"
                            y2="1"
                          >
                            <stop
                              offset="0%"
                              stopColor="#3c92ec"
                              stopOpacity={0.28}
                            />
                            <stop
                              offset="100%"
                              stopColor="#3c92ec"
                              stopOpacity={0.02}
                            />
                          </linearGradient>
                        </defs>
                        <CartesianGrid
                          stroke="#304053"
                          vertical={false}
                          strokeDasharray="3 3"
                        />
                        <XAxis
                          dataKey="date"
                          stroke="#8398af"
                          fontSize={10}
                          tickLine={false}
                        />
                        <YAxis
                          stroke="#8398af"
                          fontSize={10}
                          allowDecimals={false}
                          axisLine={false}
                          tickLine={false}
                        />
                        <Tooltip contentStyle={tooltip} />
                        <Area
                          dataKey="analyses"
                          name="Coletas"
                          type="monotone"
                          fill="url(#ops-area)"
                          stroke="#4e9df1"
                          strokeWidth={2}
                          dot={{ r: 3 }}
                          activeDot={{ r: 4 }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="empty">
                    <Activity size={25} />
                    <p>Nenhuma coleta neste período.</p>
                    <small>
                      A evolução aparece conforme análises são registradas.
                    </small>
                  </div>
                )}
              </section>
              <section className="panel risk-distribution">
                <div className="panel-title">
                  <div>
                    <h2>Prioridade por domínio</h2>
                    <p>Última análise · inventário completo</p>
                  </div>
                </div>
                {data.analyzed ? (
                  <div className="risk-content">
                    <div className="donut">
                      <ResponsiveContainer width="100%" height={170}>
                        <PieChart>
                          <Pie
                            data={distribution}
                            dataKey="value"
                            nameKey="name"
                            innerRadius={54}
                            outerRadius={72}
                            paddingAngle={2}
                            stroke="none"
                          >
                            {distribution.map((d, i) => (
                              <Cell key={d.name} fill={COLORS[i]} />
                            ))}
                          </Pie>
                          <Tooltip contentStyle={tooltip} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="donut-total">
                        <strong>{data.analyzed}</strong>
                        <span>analisados</span>
                      </div>
                    </div>
                    <div className="risk-legend">
                      {distribution.map((d, i) => (
                        <div key={d.name}>
                          <span style={{ background: COLORS[i] }} />
                          <label>Score {d.name}</label>
                          <strong>{d.value}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="empty">
                    <Shield size={25} />
                    <p>Nenhuma classificação disponível.</p>
                  </div>
                )}
              </section>
            </div>
          )}
          <div
            className={
              tab === "overview" ? "operations-bottom" : "operations-events"
            }
          >
            <section className="panel">
              <div className="panel-title">
                <div>
                  <h2>
                    Últimas análises{" "}
                    <span className="count">{recent.length}</span>
                  </h2>
                  <p>
                    Até 8 observações mais recentes · detalhes e histórico no
                    inventário
                  </p>
                </div>
                <NavLink className="subtle-link" to="/domains">
                  Abrir inventário <ArrowUpRight size={14} />
                </NavLink>
              </div>
              {recent.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>DOMÍNIO</th>
                        <th>CLASSIFICAÇÃO</th>
                        <th>SCORE</th>
                        <th>COLETA</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {recent.map((a) => (
                        <tr key={a.id}>
                          <td>
                            <strong>{a.domain}</strong>
                            <small className="block muted">
                              Análise #{a.id}
                            </small>
                          </td>
                          <td>
                            <span className="classification-dot" />
                            {a.classification}
                          </td>
                          <td>
                            <span
                              className={
                                "badge " +
                                (a.score >= 75
                                  ? "critical"
                                  : a.score >= 50
                                    ? "high"
                                    : a.score >= 25
                                      ? "medium"
                                      : "low")
                              }
                            >
                              {a.score}/100
                            </span>
                          </td>
                          <td className="muted">
                            {new Date(a.created).toLocaleString("pt-BR")}
                          </td>
                          <td>
                            <NavLink
                              className="subtle-link"
                              to={"/domains?analysis=" + a.id}
                            >
                              Detalhes <ArrowUpRight size={13} />
                            </NavLink>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty">
                  <Search size={25} />
                  <p>
                    {query
                      ? "Nenhuma das últimas análises corresponde ao filtro."
                      : "Nenhuma análise registrada no período."}
                  </p>
                  <NavLink className="subtle-link" to="/discovery">
                    Configurar descoberta automática <ArrowUpRight size={13} />
                  </NavLink>
                </div>
              )}
            </section>
            {tab === "overview" && (
              <aside className="operation-side">
                <section className="panel queue-summary">
                  <div className="panel-title">
                    <div>
                      <h2>
                        <Workflow size={17} /> Fila automática
                      </h2>
                      <p>Candidatos de fontes e CSV autorizados</p>
                    </div>
                  </div>
                  <div className="queue-summary-body">
                    <div>
                      <span>Aguardando coleta</span>
                      <strong>{queue?.counts.queued ?? 0}</strong>
                    </div>
                    <div>
                      <span>Tentativas hoje (UTC)</span>
                      <strong>
                        {queue?.used_today ?? 0}
                        <small>/{queue?.daily_limit ?? "—"}</small>
                      </strong>
                    </div>
                    <div>
                      <span>Falhas para revisão</span>
                      <strong>{queue?.counts.failed ?? 0}</strong>
                    </div>
                    <NavLink className="primary" to="/discovery">
                      Gerenciar automação <ArrowUpRight size={14} />
                    </NavLink>
                  </div>
                </section>
                <section className="panel document-summary">
                  <div className="panel-title">
                    <h2>
                      <FileText size={17} /> Documentação
                    </h2>
                  </div>
                  <div>
                    <span>Relatórios preparados</span>
                    <strong>{data.prepared}</strong>
                  </div>
                  <div>
                    <span>Encaminhamentos informados</span>
                    <strong>{data.forwarded}</strong>
                  </div>
                  <p>
                    Protocolo declarado pelo analista; sem envio ou validação
                    automática.
                  </p>
                  <NavLink className="subtle-link" to="/reports">
                    Abrir relatórios <ArrowUpRight size={13} />
                  </NavLink>
                </section>
              </aside>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
