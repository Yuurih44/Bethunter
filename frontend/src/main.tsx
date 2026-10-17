import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  NavLink,
  Routes,
  Route,
  Navigate,
  useLocation,
} from "react-router-dom";
import {
  Shield,
  LayoutDashboard,
  Globe,
  Network,
  FolderSearch,
  FileText,
  Database,
  History,
  Search,
  ArrowUpRight,
  Plus,
  Download,
  LogOut,
  RefreshCw,
  ChevronRight,
  AlertTriangle,
  Activity,
  Menu,
  Upload,
  X,
} from "lucide-react";
import { api, csrf, download, errorMessage } from "./api";
import type {
  User,
  Domain,
  Analysis,
  Case,
  Report,
  Source,
  Audit,
  Graph,
  Rule,
} from "./types";
import "./style.css";
import { AccountActions } from "./AccountActions";
import { Pager } from "./Pager";
import { NotificationCenter, CaseChecklist } from "./InvestigationTools";
import { AutomationHealth } from "./AutomationHealth";
import { SecurityPage } from "./Security";
import { Workflow } from "./Workflow";
import { Automation } from "./Automation";
import { OperationsOverview as Overview } from "./OperationsOverview";
import "./operations.css";

const fmt = (s: string) => new Date(s).toLocaleString("pt-BR");
const scoreClass = (n: number) =>
  n >= 75 ? "critical" : n >= 50 ? "high" : n >= 25 ? "medium" : "low";
function Empty({ text = "Nenhum registro disponível." }: { text?: string }) {
  return (
    <div className="empty">
      <Search size={28} />
      <p>{text}</p>
      <small>Os resultados aparecem após suas primeiras coletas.</small>
    </div>
  );
}
function App() {
  const location = useLocation();
  const [user, setUser] = useState<User | null>(null),
    [checking, setChecking] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0),
    [menu, setMenu] = useState(false);
  const refresh = () => setRevision((x) => x + 1);
  useEffect(() => {
    api
      .get<User>("/auth/me")
      .then((r) => {
        setUser(r.data);
        csrf(r.data.csrf);
      })
      .catch((e) => {
        if (e.response?.status !== 401) setError(errorMessage(e));
      })
      .finally(() => setChecking(false));
  }, []);
  useEffect(() => {
    const expire = () => {
      setUser(null);
      csrf("");
      setError("Sessão expirada. Entre novamente.");
    };
    window.addEventListener("bethunter-session-expired", expire);
    return () =>
      window.removeEventListener("bethunter-session-expired", expire);
  }, []);
  useEffect(() => {
    if (!user) return;
    let last = 0;
    const activity = () => {
      if (Date.now() - last < 60000) return;
      last = Date.now();
      void api.post("/auth/activity").catch(() => {});
    };
    window.addEventListener("pointerdown", activity);
    window.addEventListener("keydown", activity);
    return () => {
      window.removeEventListener("pointerdown", activity);
      window.removeEventListener("keydown", activity);
    };
  }, [user?.id]);
  if (location.pathname === "/account") return <AccountActions />;
  const act = async (fn: () => Promise<void>) => {
    setError("");
    setBusy(true);
    try {
      await fn();
      refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  if (checking)
    return <div className="boot">Conectando ao centro de inteligência…</div>;
  if (!user)
    return (
      <Login
        error={error}
        busy={busy}
        onSubmit={(
          email,
          password,
          register,
          invitation,
          otp_code,
          recovery_code,
        ) =>
          act(async () => {
            const r = await api.post<User>(
              "/auth/" + (register ? "register" : "login"),
              {
                email,
                password,
                invitation,
                otp_code: otp_code || null,
                recovery_code: recovery_code || null,
              },
            );
            setUser(r.data);
            csrf(r.data.csrf);
          })
        }
      />
    );
  const nav = [
    ["/", "Visão geral", LayoutDashboard],
    ["/domains", "Domínios", Globe],
    ["/intelligence", "Threat intelligence", Network],
    ["/cases", "Investigações", FolderSearch],
    ["/reports", "Relatórios e denúncias", FileText],
    ["/notifications", "Notificações", Activity],
    ["/sources", "Fontes e regras", Database],
    ["/discovery", "Descoberta automática", Search],
    ["/audit", "Trilha de auditoria", History],
    ["/security", "Segurança da conta", Shield],
  ] as const;
  return (
    <div className="app">
      {menu && (
        <button
          className="sidebar-scrim"
          aria-label="Fechar navegação"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={menu ? "sidebar mobile-open" : "sidebar"}>
        <div className="brand">
          <span className="brand-icon">
            <Shield size={25} />
          </span>
          <div>
            BET<span>HUNTER</span>
            <small>INTELIGÊNCIA DE DOMÍNIOS</small>
          </div>
        </div>
        <div className="workspace">
          <Database size={14} /> Ambiente de investigação{" "}
          <span className="version">BR</span>
        </div>
        <nav aria-label="Navegação principal">
          {[
            {
              label: "MONITORAMENTO",
              paths: ["/", "/domains", "/discovery", "/intelligence"],
            },
            {
              label: "OPERAÇÕES",
              paths: ["/cases", "/reports", "/notifications"],
            },
            {
              label: "ADMINISTRAÇÃO",
              paths: ["/sources", "/audit", "/security"],
            },
          ].map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-label">{group.label}</span>
              {group.paths.map((path) => {
                const item = nav.find((n) => n[0] === path)!;
                const [to, label, Icon] = item;
                return (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === "/"}
                    onClick={() => setMenu(false)}
                  >
                    <Icon size={17} />
                    {label}
                    <ChevronRight className="nav-arrow" size={13} />
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-note">
          <Shield size={18} />
          <strong>Evidências antes de conclusões</strong>
          <p>Prioridade de investigação não é comprovação de irregularidade.</p>
        </div>
        <div className="profile">
          <span className="avatar">{user.email[0].toUpperCase()}</span>
          <div>
            <strong>{user.email}</strong>
            <small>{user.role}</small>
          </div>
          <button
            className="icon-button"
            title="Sair"
            onClick={() =>
              act(async () => {
                await api.post("/auth/logout");
                setUser(null);
                csrf("");
              })
            }
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="main">
        <header>
          <div className="breadcrumb">
            <button
              className="icon-button mobile-toggle"
              onClick={() => setMenu(!menu)}
              aria-label="Abrir navegação"
            >
              <Menu size={20} />
            </button>
            <Shield size={15} />
            <span>BetHunter</span>
            <ChevronRight size={13} />
            <b>
              {nav.find((n) => n[0] === location.pathname)?.[1] ??
                "Investigação"}
            </b>
          </div>
          <div className="header-right">
            <button
              className="header-refresh"
              disabled={busy}
              onClick={refresh}
            >
              <RefreshCw size={14} /> Atualizar dados
            </button>
            <span className="header-divider" />
            <span className="status-dot" />{" "}
            {user.role === "admin"
              ? "Administrador"
              : user.role === "viewer"
                ? "Leitura"
                : "Analista"}
            <span className="tag">BRASIL</span>
          </div>
        </header>
        <main>
          {error && (
            <div role="alert" className="error">
              <AlertTriangle size={18} />
              {error}
              <button
                className="icon-button"
                onClick={() => setError("")}
                aria-label="Fechar erro"
              >
                <X size={16} />
              </button>
            </div>
          )}
          {busy && (
            <div className="progress" role="status">
              Processando… a coleta pública pode levar até 60 segundos.
            </div>
          )}
          <Routes>
            <Route path="/" element={<Overview revision={revision} />} />
            <Route
              path="/domains"
              element={<Domains revision={revision} act={act} busy={busy} />}
            />
            <Route
              path="/intelligence"
              element={<Intelligence revision={revision} />}
            />
            <Route
              path="/cases"
              element={<Cases revision={revision} act={act} busy={busy} />}
            />
            <Route
              path="/reports"
              element={<Reports revision={revision} act={act} busy={busy} />}
            />
            <Route
              path="/sources"
              element={
                <Sources
                  revision={revision}
                  act={act}
                  busy={busy}
                  admin={user.role === "admin"}
                />
              }
            />
            <Route
              path="/discovery"
              element={<Discovery revision={revision} act={act} busy={busy} />}
            />
            <Route
              path="/security"
              element={
                <SecurityPage
                  user={user}
                  revision={revision}
                  act={act}
                  busy={busy}
                  onSession={(u) => {
                    setUser(u);
                    csrf(u.csrf);
                  }}
                  onLogout={() => {
                    setUser(null);
                    csrf("");
                  }}
                />
              }
            />
            <Route
              path="/notifications"
              element={
                <NotificationCenter revision={revision} act={act} busy={busy} />
              }
            />
            <Route path="/audit" element={<Audits revision={revision} />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
        <footer>
          <span>BetHunter / Inteligência baseada em evidências públicas</span>
          <span>Revisão humana obrigatória</span>
        </footer>
      </div>
    </div>
  );
}
function Login({
  error,
  busy,
  onSubmit,
}: {
  error: string;
  busy: boolean;
  onSubmit: (
    e: string,
    p: string,
    r: boolean,
    invitation: string,
    otp: string,
    recovery: string,
  ) => void;
}) {
  const [register, setRegister] = useState(false);
  const [policy, setPolicy] = useState<{ registration_mode: string } | null>(
    null,
  );
  useEffect(() => {
    api
      .get("/auth/policy")
      .then((r) => setPolicy(r.data))
      .catch(() => setPolicy(null));
  }, []);
  return (
    <div className="login">
      <div className="login-intro">
        <div className="brand">
          <Shield size={38} /> BET<span>HUNTER</span>
        </div>
        <span className="eyebrow">
          INTELIGÊNCIA • EVIDÊNCIAS • INVESTIGAÇÃO
        </span>
        <h1>
          Transforme sinais
          <br />
          em investigações
          <br />
          <em>fundamentadas.</em>
        </h1>
        <p>
          Uma central para analisar domínios, documentar evidências públicas e
          organizar a revisão humana.
        </p>
        <div className="login-grid">
          <span>
            <Globe /> Análise segura
          </span>
          <span>
            <FolderSearch /> Casos rastreáveis
          </span>
          <span>
            <FileText /> Relatórios técnicos
          </span>
        </div>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          onSubmit(
            String(f.get("email")),
            String(f.get("password")),
            register,
            String(f.get("invitation") || ""),
            String(f.get("otp_code") || ""),
            String(f.get("recovery_code") || ""),
          );
        }}
      >
        <span className="eyebrow">ACESSO AO WORKSPACE</span>
        <h2>{register ? "Criar sua conta" : "Bem-vindo ao BetHunter"}</h2>
        <p>Entre para acessar seus registros de investigação.</p>
        {error && (
          <div role="alert" className="error">
            {error}
          </div>
        )}
        <label>
          Email
          <input
            type="email"
            name="email"
            required
            autoComplete="email"
            maxLength={254}
          />
        </label>
        <label>
          Senha
          <input
            type="password"
            name="password"
            minLength={register ? 15 : 1}
            maxLength={128}
            required
            autoComplete={register ? "new-password" : "current-password"}
          />
          {register && (
            <small>Use uma frase exclusiva com pelo menos 15 caracteres.</small>
          )}
        </label>
        {register && policy?.registration_mode === "invite" && (
          <label>
            Código de convite
            <input
              name="invitation"
              required
              autoComplete="off"
              maxLength={100}
            />
            <small>
              Convite individual vinculado ao seu email. Não confirma posse da
              caixa postal.
            </small>
          </label>
        )}
        {!register && (
          <details>
            <summary>Autenticação em duas etapas (se ativada)</summary>
            <label>
              Código do aplicativo
              <input
                name="otp_code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
              />
            </label>
            <label>
              Ou código de recuperação
              <input name="recovery_code" maxLength={100} autoComplete="off" />
            </label>
          </details>
        )}
        <button className="primary" disabled={busy}>
          {busy
            ? "Processando…"
            : register
              ? "Criar conta"
              : "Entrar no workspace"}
          <ArrowUpRight size={17} />
        </button>
        {policy && policy.registration_mode !== "closed" && (
          <button
            type="button"
            className="text-button"
            onClick={() => setRegister(!register)}
          >
            {register
              ? "Já tenho uma conta"
              : policy?.registration_mode === "invite"
                ? "Tenho um convite"
                : "Criar uma nova conta"}
          </button>
        )}
        {!register && <a href="/account">Esqueci minha senha</a>}
        <small className="muted">
          Uso autorizado de informações públicas. Nenhuma denúncia é enviada
          automaticamente.
        </small>
      </form>
    </div>
  );
}
type Actions = {
  act: (fn: () => Promise<void>) => Promise<void>;
  busy: boolean;
};
function useData<T>(url: string, revision: number) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true,
      pending = false;
    const controller = new AbortController();
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const r = await api.get<T>(url, { signal: controller.signal });
        if (live) {
          setData(r.data);
          setError("");
        }
      } catch (e) {
        if (live) setError(errorMessage(e));
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = setInterval(() => void load(), 15000);
    return () => {
      live = false;
      clearInterval(timer);
      controller.abort();
    };
  }, [url, revision]);
  return { data, error };
}
function LoadError({ error }: { error: string }) {
  return error ? (
    <div className="error" role="alert">
      {error}
    </div>
  ) : null;
}
function PageTitle({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
function Domains({ revision, act, busy }: { revision: number } & Actions) {
  const [page, setPage] = useState(1),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all");
  const { data: inventory, error } = useData<{
    items: (Domain & { latest: Analysis | null })[];
    total: number;
  }>(
    `/inventory?page=${page}&q=${encodeURIComponent(query)}&priority=${filter}`,
    revision,
  );
  const domains = inventory?.items;
  const analyses = domains?.flatMap((d) => (d.latest ? [d.latest] : []));
  const [selected, setSelected] = useState<number[]>([]),
    [detail, setDetail] = useState<Analysis | null>(null),
    [format, setFormat] = useState("domains");
  const [historyPage, setHistoryPage] = useState(1);
  const { data: history } = useData<{ items: Analysis[]; total: number }>(
    `/pages/analyses?domain_id=${detail?.domain_id ?? 0}&page=${historyPage}`,
    revision,
  );
  const latest = (id: number) => analyses?.find((a) => a.domain_id === id);
  const location = useLocation();
  useEffect(() => {
    const analysisId = Number(
      new URLSearchParams(location.search).get("analysis"),
    );
    if (analysisId)
      void api
        .get<Analysis>(`/analyses/${analysisId}`)
        .then((r) => setDetail(r.data))
        .catch(() => {});
  }, [location.search]);
  return (
    <>
      <PageTitle
        eyebrow="SUPERFÍCIE DE INVESTIGAÇÃO"
        title="Domínios"
        description="Cadastre um domínio e colete informações públicas com rastreabilidade."
      />
      <LoadError error={error} />
      <form
        className="search-form panel"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const value = String(new FormData(form).get("domain"));
          act(async () => {
            const d = await api.post<Domain>("/domains", { value });
            form.reset();
            const a = await api.post<Analysis>(`/domains/${d.data.id}/analyze`);
            setDetail(a.data);
          });
        }}
      >
        <Globe size={20} />
        <input
          name="domain"
          placeholder="dominio.com.br ou https://dominio.com.br"
          required
          maxLength={2048}
          aria-label="Domínio para análise"
        />
        <button disabled={busy} className="primary">
          <Search size={16} /> Cadastrar e analisar
        </button>
      </form>
      <div className="toolbar">
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
          placeholder="Filtrar domínios…"
          aria-label="Filtrar domínios"
        />
        <select
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setPage(1);
          }}
          aria-label="Filtrar por prioridade"
        >
          <option value="all">Todas as prioridades</option>
          <option value="high">Score ≥ 50</option>
          <option value="pending">Sem análise</option>
        </select>
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          aria-label="Formato de bloqueio"
        >
          <option value="domains">Domínios</option>
          <option value="hosts">Hosts</option>
          <option value="adblock">Adblock</option>
        </select>
        <button
          disabled={busy || !selected.length}
          onClick={() =>
            act(() =>
              download("/blocklists", "bethunter-blocklist.txt", {
                domain_ids: selected,
                format,
              }),
            )
          }
        >
          <Download size={15} /> Bloqueio voluntário ({selected.length})
        </button>
      </div>
      <section className="panel">
        {domains?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>SELEÇÃO</th>
                  <th>DOMÍNIO</th>
                  <th>CLASSIFICAÇÃO</th>
                  <th>SCORE</th>
                  <th>AÇÕES</th>
                </tr>
              </thead>
              <tbody>
                {domains
                  .filter((d) => d.name.includes(query.toLowerCase()))
                  .filter(
                    (d) =>
                      filter === "all" ||
                      (filter === "pending"
                        ? !latest(d.id)
                        : (latest(d.id)?.score ?? 0) >= 50),
                  )
                  .map((d) => {
                    const a = latest(d.id);
                    return (
                      <tr key={d.id}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={"Selecionar " + d.name}
                            checked={selected.includes(d.id)}
                            onChange={(e) =>
                              setSelected(
                                e.target.checked
                                  ? [...selected, d.id]
                                  : selected.filter((x) => x !== d.id),
                              )
                            }
                          />
                        </td>
                        <td>
                          <strong>{d.name}</strong>
                          <small className="block muted">
                            Origem: {d.origin}
                          </small>
                        </td>
                        <td>
                          {a?.result.verdict?.label ??
                            a?.classification ??
                            "Aguardando análise"}
                        </td>
                        <td>
                          {a ? (
                            <span className={"badge " + scoreClass(a.score)}>
                              {a.score}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          <div className="row-actions">
                            <button
                              disabled={busy}
                              onClick={() =>
                                act(async () => {
                                  const r = await api.post<Analysis>(
                                    `/domains/${d.id}/analyze`,
                                  );
                                  setDetail(r.data);
                                })
                              }
                            >
                              <RefreshCw size={13} /> Coletar
                            </button>
                            {a && (
                              <button onClick={() => setDetail(a)}>
                                Detalhes
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty text="Cadastre seu primeiro domínio." />
        )}
      </section>
      <Pager page={page} total={inventory?.total ?? 0} onPage={setPage} />
      {detail && (
        <section className="panel analysis-detail">
          <div className="panel-title">
            <div>
              <span className="eyebrow">
                ANÁLISE #{detail.id} · {fmt(detail.created)}
              </span>
              <h2>
                {detail.domain ??
                  domains?.find((d) => d.id === detail.domain_id)?.name}
              </h2>
            </div>
            <button onClick={() => setDetail(null)} aria-label="Fechar análise">
              <X size={16} />
            </button>
          </div>
          <div className="detail-summary">
            <span className={"badge " + scoreClass(detail.score)}>
              {detail.score}/100
            </span>
            <strong>{detail.classification}</strong>
          </div>
          <p className="muted">Versão da regra: {detail.result.rule_version}</p>
          {detail.result.verdict && (
            <section className="verdict">
              <h3>{detail.result.verdict.label}</h3>
              <p>{detail.result.verdict.explanation}</p>
              <small>
                Resultado para investigação. Não determina crime. Revisão humana
                necessária.
              </small>
            </section>
          )}
          <h3>Fatores documentados</h3>
          {detail.result.factors.length ? (
            detail.result.factors.map((f) => (
              <p key={f.key}>
                +{f.weight} · {f.explanation}
              </p>
            ))
          ) : (
            <p>
              Nenhum fator de pontuação observado. Falhas de coleta devem ser
              consideradas.
            </p>
          )}
          <h3>Verificação regulatória: {detail.result.regulation.status}</h3>
          <p>{detail.result.regulation.reason}</p>
          {detail.result.regulation.url && (
            <a
              href={detail.result.regulation.url}
              target="_blank"
              rel="noreferrer"
            >
              Fonte oficial consultada ↗
            </a>
          )}
          {detail.result.discovery && (
            <>
              <h3>Origem da descoberta</h3>
              <pre>{JSON.stringify(detail.result.discovery, null, 2)}</pre>
            </>
          )}
          <h3>Informações técnicas</h3>
          <pre>{JSON.stringify(detail.result.technical, null, 2)}</pre>
          {detail.result.errors.map((e, i) => (
            <p className="warning" key={i}>
              {e}
            </p>
          ))}
          <h3>Limitações</h3>
          {detail.result.limitations.map((l) => (
            <p className="muted" key={l}>
              {l}
            </p>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const review = String(
                new FormData(e.currentTarget).get("review"),
              );
              act(async () => {
                const r = await api.patch<Analysis>(
                  `/analyses/${detail.id}/review`,
                  { review },
                );
                setDetail(r.data);
              });
            }}
          >
            <label>
              Revisão humana
              <textarea
                key={detail.id + "-" + detail.review}
                name="review"
                defaultValue={detail.review}
                required
                maxLength={10000}
              />
            </label>
            <button className="primary" disabled={busy}>
              Salvar revisão
            </button>
          </form>
          <h3>Documentos originais preservados</h3>
          {detail.result.raw_document_ids?.map((id) => (
            <button
              key={id}
              onClick={() =>
                act(() =>
                  download(`/evidence/documents/${id}`, `evidence-${id}.bin`),
                )
              }
            >
              Baixar documento #{id}
            </button>
          ))}
          <h3>Histórico deste domínio</h3>
          <Pager
            page={historyPage}
            total={history?.total ?? 0}
            onPage={setHistoryPage}
          />
          <div className="history-list">
            {history?.items.map((a) => (
              <button key={a.id} onClick={() => setDetail(a)}>
                #{a.id} · {fmt(a.created)} · {a.score}/100
              </button>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
function Cases({ revision, act, busy }: { revision: number } & Actions) {
  const [reportNotice, setReportNotice] = useState("");
  const [page, setPage] = useState(1);
  const { data: casePage, error } = useData<{ items: Case[]; total: number }>(
    `/pages/cases?page=${page}`,
    revision,
  );
  const cases = casePage?.items;
  const [domainPage, setDomainPage] = useState(1),
    [domainQuery, setDomainQuery] = useState(""),
    [caseDomainIds, setCaseDomainIds] = useState<number[]>([]);
  const { data: choices } = useData<{ items: Domain[]; total: number }>(
    `/pages/domains?page=${domainPage}&q=${encodeURIComponent(domainQuery)}`,
    revision,
  );
  const domains = choices?.items;
  const [editing, setEditing] = useState<Case | null>(null),
    [open, setOpen] = useState(false);
  return (
    <>
      <PageTitle
        eyebrow="CENTRAL DE INVESTIGAÇÕES"
        title="Casos"
        description="Organize evidências, registre decisões e acompanhe cada investigação."
      >
        <button
          className="primary"
          onClick={() => {
            setEditing(null);
            setCaseDomainIds([]);
            setOpen(true);
          }}
        >
          <Plus size={16} /> Abrir caso
        </button>
      </PageTitle>
      <LoadError error={error} />
      {reportNotice && (
        <p role="status" className="notice">
          {reportNotice} <a href="/reports">Abrir relatórios</a>
        </p>
      )}
      {open && (
        <form
          key={editing?.id ?? "new"}
          className="panel case-form"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            const body = {
              title: f.get("title"),
              notes: f.get("notes"),
              priority: f.get("priority"),
              status: f.get("status"),
              domain_ids: caseDomainIds,
            };
            act(async () => {
              await (editing
                ? api.put(`/cases/${editing.id}`, body)
                : api.post("/cases", body));
              setOpen(false);
            });
          }}
        >
          <div className="panel-title">
            <h2>
              {editing ? "Editar caso #" + editing.id : "Nova investigação"}
            </h2>
            <button type="button" onClick={() => setOpen(false)}>
              <X size={16} />
            </button>
          </div>
          <label>
            Título
            <input
              name="title"
              defaultValue={editing?.title}
              minLength={3}
              maxLength={200}
              required
            />
          </label>
          <div className="form-grid">
            <label>
              Prioridade
              <select
                name="priority"
                defaultValue={editing?.priority ?? "normal"}
              >
                <option value="low">Baixa</option>
                <option value="normal">Normal</option>
                <option value="high">Alta</option>
              </select>
            </label>
            <label>
              Status
              <select name="status" defaultValue={editing?.status ?? "open"}>
                <option value="open">Aberto / reaberto</option>
                <option value="investigating">Em investigação</option>
                <option value="closed">Encerrado</option>
              </select>
            </label>
          </div>
          <label>
            Observações, decisões e conclusão técnica
            <textarea
              name="notes"
              defaultValue={editing?.notes}
              maxLength={20000}
            />
          </label>
          <label>
            Buscar domínios para associar
            <input
              value={domainQuery}
              onChange={(e) => {
                setDomainQuery(e.target.value);
                setDomainPage(1);
              }}
            />
          </label>
          <Pager
            page={domainPage}
            total={choices?.total ?? 0}
            onPage={setDomainPage}
          />
          <label>
            Domínios associados ({caseDomainIds.length} selecionados)
          </label>
          <div className="checkbox-list">
            {domains?.map((d) => (
              <label key={d.id}>
                <input
                  type="checkbox"
                  name="domain"
                  value={d.id}
                  checked={caseDomainIds.includes(d.id)}
                  onChange={(e) =>
                    setCaseDomainIds(
                      e.target.checked
                        ? [...caseDomainIds, d.id]
                        : caseDomainIds.filter((id) => id !== d.id),
                    )
                  }
                />
                {d.name}
              </label>
            ))}
          </div>
          <button disabled={busy} className="primary">
            Salvar caso
          </button>
        </form>
      )}
      <div className="case-grid">
        {cases?.map((c) => (
          <section className="panel case-card" key={c.id}>
            <div className="panel-title">
              <span className="eyebrow">
                CASO #{String(c.id).padStart(4, "0")}
              </span>
              <span
                className={"badge " + (c.priority === "high" ? "high" : "low")}
              >
                {c.priority}
              </span>
            </div>
            <h2>{c.title}</h2>
            <p>{c.notes || "Sem observações registradas."}</p>
            <CaseChecklist id={c.id} revision={revision} />
            <div className="case-meta">
              <span>{c.domain_ids.length} domínios</span>
              <span>
                {c.status === "closed"
                  ? "Encerrado"
                  : c.status === "investigating"
                    ? "Em investigação"
                    : "Aberto"}
              </span>
            </div>
            <div className="row-actions">
              <button
                onClick={() => {
                  setEditing(c);
                  setCaseDomainIds(c.domain_ids);
                  setOpen(true);
                }}
              >
                Editar / revisar
              </button>
              <button
                disabled={busy || !c.domain_ids.length}
                onClick={() =>
                  act(async () => {
                    const queued = await api.post(`/cases/${c.id}/reports`);
                    const generated = await api.post(
                      `/report-jobs/${queued.data.job_id}/generate`,
                    );
                    if (generated.data.status === "failed")
                      throw new Error(
                        generated.data.error ||
                          "Falha ao gerar PDF; consulte Relatórios",
                      );
                    if (generated.data.report_id) {
                      await download(
                        `/reports/${generated.data.report_id}/pdf`,
                        `bethunter-${generated.data.report_id}.pdf`,
                      );
                      setReportNotice(
                        "PDF gerado. Download solicitado ao navegador; uma cópia permanece em Relatórios.",
                      );
                    } else
                      setReportNotice(
                        "Tarefa preservada na fila. Acompanhe em Relatórios.",
                      );
                  })
                }
              >
                <Download size={14} /> Gerar e baixar PDF
              </button>
            </div>
          </section>
        ))}
      </div>
      {!cases?.length && <Empty text="Nenhum caso aberto." />}
      <Pager page={page} total={casePage?.total ?? 0} onPage={setPage} />
    </>
  );
}
function Reports({ revision, act, busy }: { revision: number } & Actions) {
  const [page, setPage] = useState(1);
  const [jobPage, setJobPage] = useState(1);
  const { data: reportPage, error } = useData<{
    items: Report[];
    total: number;
  }>(`/pages/reports?page=${page}`, revision);
  const data = reportPage?.items;
  const { data: jobs } = useData<{
    items: { id: number; case_id: number; status: string; error: string }[];
    total: number;
  }>(`/pages/report-jobs?page=${jobPage}`, revision);
  const [confirm, setConfirm] = useState<number | null>(null);
  return (
    <>
      <PageTitle
        eyebrow="DOCUMENTAÇÃO TÉCNICA"
        title="Relatórios e denúncias"
        description="Exporte evidências e prepare o encaminhamento aos canais oficiais."
      />
      <section className="notice">
        <FileText size={24} />
        <p>
          Relatórios são gerados a partir dos casos. O envio é manual. Um
          protocolo informado pelo analista não é validado automaticamente pelo
          BetHunter.{" "}
          <a href="https://falabr.cgu.gov.br/" target="_blank" rel="noreferrer">
            Acessar Fala.BR ↗
          </a>
        </p>
      </section>
      <AutomationHealth revision={revision} busy={busy} act={act} />
      <LoadError error={error} />
      <section className="panel case-form">
        <h2>Fila de geração de PDFs</h2>
        {jobs?.items.map((j) => (
          <p key={j.id}>
            Tarefa #{j.id} · Caso #{j.case_id} · {j.status}
            {j.error && ` · ${j.error}`}
            {j.status === "queued" && (
              <button
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    const r = await api.post(`/report-jobs/${j.id}/generate`);
                    if (r.data.status === "failed")
                      throw new Error(r.data.error || "Falha ao gerar PDF");
                    if (r.data.report_id)
                      await download(
                        `/reports/${r.data.report_id}/pdf`,
                        `bethunter-${r.data.report_id}.pdf`,
                      );
                  })
                }
              >
                Gerar e baixar agora
              </button>
            )}
          </p>
        ))}
        <Pager page={jobPage} total={jobs?.total ?? 0} onPage={setJobPage} />
        {jobs?.items
          .filter((j) => j.status === "failed")
          .map((j) => (
            <div key={"actions-" + j.id}>
              <button
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    await api.post(`/report-jobs/${j.id}/retry`);
                  })
                }
              >
                Repetir tarefa #{j.id}
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    await api.post(`/report-jobs/${j.id}/discard`);
                  })
                }
              >
                Descartar snapshot falho #{j.id}
              </button>
            </div>
          ))}
        <p>
          Documentos idênticos são reutilizados. A renderização ocorre no worker
          com limites de memória, tempo e tamanho.
        </p>
      </section>
      <Pager page={page} total={reportPage?.total ?? 0} onPage={setPage} />
      {confirm && (
        <form
          className="panel case-form"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            act(async () => {
              await api.post(`/reports/${confirm}/confirmation`, {
                protocol: f.get("protocol"),
                confirmation: f.get("confirmation"),
              });
              setConfirm(null);
            });
          }}
        >
          <h2>Registrar confirmação recebida do canal oficial</h2>
          <label>
            Protocolo
            <input name="protocol" minLength={3} maxLength={200} required />
          </label>
          <label>
            Referência da confirmação, canal e data
            <textarea
              name="confirmation"
              minLength={10}
              maxLength={5000}
              required
            />
          </label>
          <div className="row-actions">
            <button className="primary" disabled={busy}>
              Registrar declaração do analista
            </button>
            <button type="button" onClick={() => setConfirm(null)}>
              Cancelar
            </button>
          </div>
        </form>
      )}
      <section className="panel">
        {data?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>RELATÓRIO</th>
                  <th>CASO</th>
                  <th>GERADO EM</th>
                  <th>SITUAÇÃO</th>
                  <th>AÇÕES</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.id}>
                    <td>
                      #{r.id}
                      <small className="block muted hash" title={r.sha256}>
                        SHA-256: {r.sha256.slice(0, 16)}…
                      </small>
                    </td>
                    <td>#{r.case_id}</td>
                    <td>{fmt(r.created)}</td>
                    <td>
                      {r.status === "prepared"
                        ? "Preparado"
                        : "Encaminhamento informado pelo analista"}
                      {r.protocol && (
                        <small className="block">Protocolo: {r.protocol}</small>
                      )}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          disabled={busy || r.archived}
                          onClick={() =>
                            act(() =>
                              download(
                                `/reports/${r.id}/pdf`,
                                `bethunter-${r.id}.pdf`,
                              ),
                            )
                          }
                        >
                          <Download size={14} />{" "}
                          {r.archived ? "PDF arquivado" : "PDF"}
                        </button>
                        <button
                          disabled={busy}
                          onClick={() => setConfirm(r.id)}
                        >
                          Registrar protocolo
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty text="Gere um relatório na central de casos." />
        )}
      </section>
    </>
  );
}
function Sources({
  revision,
  act,
  busy,
  admin,
}: { revision: number; admin: boolean } & Actions) {
  const { data, error } = useData<Source[]>("/sources", revision),
    { data: rules } = useData<Rule[]>("/rules", revision);
  const { data: context, error: contextError } = useData<{
    verified: boolean;
    reason: string;
    consulted?: string;
    url?: string;
    version?: string;
  }>("/regulatory/context", revision);
  return (
    <>
      <PageTitle
        eyebrow="VERIFICAÇÃO REGULATÓRIA"
        title="Fontes e regras"
        description="Registros públicos com origem, data e limites de validade."
      >
        {admin && (
          <button
            className="primary"
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api.post("/sources/sync");
              })
            }
          >
            <RefreshCw size={16} /> Consultar SPA/MF
          </button>
        )}
      </PageTitle>
      <section className="panel case-form">
        <h2>Contexto normativo atual</h2>
        <LoadError error={contextError} />
        <p>{context?.reason ?? "Aguardando consulta"}</p>
        {context?.consulted && (
          <p>
            Consulta: {fmt(context.consulted)} · Versão: {context.version}
          </p>
        )}
        {context?.url && (
          <a href={context.url} target="_blank" rel="noreferrer">
            Fonte normativa oficial ↗
          </a>
        )}
        {admin && (
          <button
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api.post("/regulatory/sync");
              })
            }
          >
            Atualizar contexto normativo
          </button>
        )}
        <p className="muted">
          O worker consulta as fontes a cada seis horas por padrão. Uma lista
          histórica não comprova autorização vigente. Formato desconhecido ou
          consulta vencida impede a verificação automática.
        </p>
      </section>
      <section className="notice">
        <Database size={22} />
        <p>
          Importação conservadora da tabela federal SPA/MF. Documentos sem data
          ou com atualização superior ao limite configurado não verificam
          situação atual. Estados, decisões judiciais e mudanças normativas
          exigem revisão humana.{" "}
          {admin
            ? ""
            : "A sincronização e a configuração de regras exigem perfil administrador."}
        </p>
      </section>
      <LoadError error={error} />
      {data?.map((s) => (
        <section className="panel source-card" key={s.id}>
          <div className="panel-title">
            <h2>SPA/MF · Consulta #{s.id}</h2>
            <span
              className={
                "badge " + (s.status === "imported" ? "low" : "medium")
              }
            >
              {s.status}
            </span>
          </div>
          <a href={s.url} target="_blank" rel="noreferrer">
            Documento oficial ↗
          </a>
          <p>
            Consultado: {fmt(s.consulted)} · Atualização do documento:{" "}
            {s.document_updated ? fmt(s.document_updated) : "Não identificada"}
          </p>
          <p>
            {s.entries.length} registros · SHA-256: {s.sha256 || "Indisponível"}
          </p>
          {s.error && <p className="warning">{s.error}</p>}
          <details>
            <summary>Empresas, domínios e atos identificados</summary>
            <pre>{JSON.stringify(s.entries, null, 2)}</pre>
          </details>
        </section>
      ))}
      {!data?.length && (
        <Empty text="Nenhuma fonte oficial consultada. Situação regulatória não verificada." />
      )}
      <section className="panel case-form">
        <h2>Regras versionadas</h2>
        <p className="muted">
          Padrão técnico v2: menções sem oferta confirmada +10; ações de
          operação com termos +25; redirecionamento entre domínios +15. A
          ausência em lista e a extensão do domínio não pontuam. Versões novas
          são imutáveis e a versão vigente mais recente prevalece.
        </p>
        {rules?.map((r) => (
          <div className="rule-row" key={r.version}>
            <strong>{r.version}</strong>
            <span>
              Vigência: {fmt(r.effective_from)}
              {r.effective_until ? " até " + fmt(r.effective_until) : ""}
            </span>
            <pre>{JSON.stringify(r.config, null, 2)}</pre>
          </div>
        ))}
        {admin && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              act(async () => {
                await api.post("/rules", {
                  version: f.get("version"),
                  effective_from: new Date(String(f.get("from"))).toISOString(),
                  effective_until: f.get("until")
                    ? new Date(String(f.get("until"))).toISOString()
                    : null,
                  weights: {
                    betting_content: Number(f.get("betting")),
                    betting_mentions: Number(f.get("mentions")),
                    cross_domain_redirect: Number(f.get("redirect")),
                  },
                  rationale: f.get("rationale"),
                });
              });
            }}
          >
            <label>
              Nova versão
              <input name="version" required maxLength={80} />
            </label>
            <div className="form-grid">
              <label>
                Vigente a partir de
                <input type="datetime-local" name="from" required />
              </label>
              <label>
                Até (opcional)
                <input type="datetime-local" name="until" />
              </label>
              <label>
                Peso: termos de apostas
                <input
                  type="number"
                  name="betting"
                  min={0}
                  max={100}
                  defaultValue={25}
                  required
                />
              </label>
              <label>
                Peso: menções sem operação
                <input
                  type="number"
                  name="mentions"
                  min={0}
                  max={100}
                  defaultValue={10}
                  required
                />
              </label>
              <label>
                Peso: redirecionamento
                <input
                  type="number"
                  name="redirect"
                  min={0}
                  max={100}
                  defaultValue={15}
                  required
                />
              </label>
            </div>
            <label>
              Justificativa, escopo e atos pertinentes
              <textarea
                name="rationale"
                minLength={10}
                maxLength={5000}
                required
              />
            </label>
            <button className="primary" disabled={busy}>
              Criar versão
            </button>
          </form>
        )}
      </section>
    </>
  );
}
function Discovery({ act, busy, revision }: Actions & { revision: number }) {
  const { data: domains } = useData<Domain[]>("/domains", revision);
  const { data: schedules, error: scheduleError } = useData<
    {
      id: number;
      domain_id: number;
      domain: string;
      interval_hours: number;
      enabled: boolean;
      next_run: string;
      last_run: string | null;
      last_error: string;
    }[]
  >("/schedules", revision);
  const [result, setResult] = useState<unknown>(null),
    [text, setText] = useState("domain\n");
  const [autoAnalyze, setAutoAnalyze] = useState(true);
  return (
    <>
      <PageTitle
        eyebrow="NOVOS CANDIDATOS"
        title="Descoberta"
        description="Importe domínios de conjuntos públicos ou listas obtidas com autorização."
      />
      <Workflow revision={revision} act={act} busy={busy} />
      <Automation revision={revision} act={act} busy={busy} />
      <section className="panel case-form">
        <h2>
          <Upload size={20} /> Importação CSV
        </h2>
        <p className="muted">
          Coluna obrigatória: domain. Até 1.000 linhas por importação.
          Duplicidades são eliminadas. Ative a opção abaixo para colocar os
          novos candidatos imediatamente na fila. Com a automação habilitada, o
          inventário também é enfileirado pelo worker.
        </p>
        <label>
          Arquivo CSV
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                if (file.size > 250000) {
                  setResult({ error: "Arquivo excede 250 KB" });
                  return;
                }
                file.text().then(setText);
              }
            }}
          />
        </label>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              const r = await api.post("/discovery/import", {
                csv: text,
                auto_analyze: autoAnalyze,
              });
              setResult(r.data);
            });
          }}
        >
          <label>
            Conteúdo
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={250000}
              required
            />
          </label>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={autoAnalyze}
              onChange={(e) => setAutoAnalyze(e.target.checked)}
            />{" "}
            Analisar novos candidatos automaticamente
          </label>
          <button className="primary" disabled={busy}>
            <Upload size={16} /> Importar candidatos
          </button>
        </form>
        {result !== null && <pre>{JSON.stringify(result, null, 2)}</pre>}
      </section>
      <section className="panel case-form">
        <h2>Monitoramento agendado</h2>
        <p className="muted">
          O worker do Docker Compose coleta um domínio por vez. Intervalo
          mínimo: 1 hora. Uma execução vencida roda uma vez, sem disparar
          coletas acumuladas.
        </p>
        <LoadError error={scheduleError} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            act(async () => {
              await api.post("/schedules", {
                domain_id: Number(f.get("domain")),
                interval_hours: Number(f.get("hours")),
                enabled: true,
              });
            });
          }}
        >
          <div className="form-grid">
            <label>
              Domínio
              <select name="domain" required>
                <option value="">Selecione</option>
                {domains?.map((d) => (
                  <option value={d.id} key={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Intervalo em horas
              <input
                type="number"
                name="hours"
                min={1}
                max={8760}
                defaultValue={24}
                required
              />
            </label>
          </div>
          <button className="primary" disabled={busy || !domains?.length}>
            Salvar agendamento
          </button>
        </form>
        {schedules?.map((s) => (
          <div className="rule-row" key={s.id}>
            <strong>
              {s.domain} · a cada {s.interval_hours}h ·{" "}
              {s.enabled ? "Ativo" : "Pausado"}
            </strong>
            <p>
              Próxima execução: {fmt(s.next_run)} · Última:{" "}
              {s.last_run ? fmt(s.last_run) : "Ainda não executado"}
            </p>
            {s.last_error && <p className="warning">{s.last_error}</p>}
            <button
              disabled={busy}
              onClick={() =>
                act(async () => {
                  await api.post("/schedules", {
                    domain_id: s.domain_id,
                    interval_hours: s.interval_hours,
                    enabled: !s.enabled,
                  });
                })
              }
            >
              {s.enabled ? "Pausar" : "Retomar"}
            </button>
          </div>
        ))}
      </section>
      <section className="notice">
        <AlertTriangle size={22} />
        <p>
          A descoberta automática consulta somente as fontes configuradas e
          mantém origem, data e hash. Não varre a internet inteira. Listas
          comunitárias não são listas oficiais de irregularidades.
        </p>
      </section>
    </>
  );
}
function Intelligence({ revision }: { revision: number }) {
  const { data, error } = useData<Graph>("/intelligence/graph", revision);
  const [selected, setSelected] = useState("");
  const nodes = data?.nodes.slice(0, 60) ?? [];
  const pos = (id: string) => {
    const i = nodes.findIndex((n) => n.id === id);
    const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
    return { x: 450 + 330 * Math.cos(angle), y: 240 + 175 * Math.sin(angle) };
  };
  return (
    <>
      <PageTitle
        eyebrow="INFRAESTRUTURA OBSERVADA"
        title="Threat intelligence"
        description="Explore relações técnicas e o histórico de observações públicas."
      />
      <LoadError error={error} />
      <section className="notice">
        <Network size={22} />
        <p>
          {data?.limitation ??
            "Relações técnicas não comprovam controle comum."}{" "}
          O enriquecimento ASN/organização anunciante usa RIPEstat quando
          ENRICH_ASN está habilitado. Não identifica necessariamente a
          hospedagem. Histórico anterior às coletas exige provedor adicional.
        </p>
      </section>
      <section className="panel graph-panel">
        <div className="panel-title">
          <h2>Domínios, endereços IP e ASN</h2>
          <span className="tag">ATÉ 60 NÓS</span>
        </div>
        {nodes.length ? (
          <>
            <svg
              viewBox="0 0 900 480"
              role="img"
              aria-label="Grafo interativo de relações de domínio e IP"
            >
              {data?.edges
                .filter(
                  (e) =>
                    nodes.some((n) => n.id === e.source) &&
                    nodes.some((n) => n.id === e.target),
                )
                .map((e) => {
                  const a = pos(e.source),
                    b = pos(e.target),
                    active =
                      !selected ||
                      e.source === selected ||
                      e.target === selected;
                  return (
                    <line
                      key={e.source + e.target}
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      stroke={active ? "#5376a0" : "#222b38"}
                      strokeWidth={active ? 2 : 1}
                    />
                  );
                })}
              {nodes.map((n) => {
                const p = pos(n.id);
                return (
                  <g
                    key={n.id}
                    role="button"
                    tabIndex={0}
                    aria-label={n.label}
                    onClick={() => setSelected(selected === n.id ? "" : n.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") setSelected(n.id);
                    }}
                    className="graph-node"
                  >
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={selected === n.id ? 12 : 8}
                      fill={n.kind === "domain" ? "#e0bd67" : "#80afff"}
                    />
                    <text
                      x={p.x}
                      y={p.y + 25}
                      textAnchor="middle"
                      fill="#b6c0ce"
                      fontSize="11"
                    >
                      {n.label.length > 25
                        ? n.label.slice(0, 25) + "…"
                        : n.label}
                    </text>
                  </g>
                );
              })}
            </svg>
            <label>
              Nó selecionado
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Todas as relações</option>
                {nodes.map((n) => (
                  <option value={n.id} key={n.id}>
                    {n.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>DOMÍNIO</th>
                    <th>INDICADOR</th>
                    <th>ÚLTIMA OBSERVAÇÃO</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.edges
                    .filter(
                      (e) =>
                        !selected ||
                        e.source === selected ||
                        e.target === selected,
                    )
                    .map((e) => (
                      <tr key={e.source + e.target}>
                        <td>
                          {data.nodes.find((n) => n.id === e.source)?.label}
                        </td>
                        <td>{e.target}</td>
                        <td>{fmt(e.observed)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <Empty text="Colete um domínio para iniciar o mapa de relações." />
        )}
      </section>
    </>
  );
}
function Audits({ revision }: { revision: number }) {
  const [page, setPage] = useState(1);
  const { data: auditPage, error } = useData<{ items: Audit[]; total: number }>(
    `/pages/audit?page=${page}`,
    revision,
  );
  const data = auditPage?.items;
  return (
    <>
      <PageTitle
        eyebrow="RASTREABILIDADE"
        title="Trilha de auditoria"
        description="Histórico paginado de mudanças e ações do seu usuário."
      />
      <LoadError error={error} />
      <Pager page={page} total={auditPage?.total ?? 0} onPage={setPage} />
      <section className="panel">
        {data?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>EVENTO</th>
                  <th>DATA</th>
                  <th>DETALHES</th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id}>
                    <td>{a.action}</td>
                    <td>{fmt(a.created)}</td>
                    <td>
                      <details>
                        <summary>Ver registro #{a.id}</summary>
                        <pre>{JSON.stringify(a.details, null, 2)}</pre>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty />
        )}
      </section>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
