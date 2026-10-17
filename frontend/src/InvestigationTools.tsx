import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { api, errorMessage } from "./api";
type Actions = {
  revision: number;
  busy: boolean;
  act: (fn: () => Promise<void>) => Promise<void>;
};
type Notice = {
  id: string;
  code: string;
  level: string;
  message: string;
  link: string;
  acknowledged: boolean;
};
export function NotificationCenter({ revision, busy, act }: Actions) {
  const [data, setData] = useState<{
      unread: number;
      items: Notice[];
      notice: string;
    } | null>(null),
    [error, setError] = useState(""),
    [showRead, setShowRead] = useState(false);
  useEffect(() => {
    let live = true,
      pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const r = await api.get("/notifications");
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
    };
  }, [revision]);
  return (
    <>
      <div className="page-title">
        <div>
          <span className="eyebrow">ACOMPANHAMENTO</span>
          <h1>Central de notificações</h1>
          <p>
            Avisos operacionais e PDFs disponíveis, derivados do banco da sua
            conta.
          </p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {data && (
        <>
          <section className="panel case-form">
            <h2>{data.unread} avisos não reconhecidos</h2>
            <label>
              <input
                type="checkbox"
                checked={showRead}
                onChange={(e) => setShowRead(e.target.checked)}
              />{" "}
              Mostrar reconhecidos
            </label>
            <p>{data.notice}</p>
          </section>
          {data.items
            .filter((n) => showRead || !n.acknowledged)
            .map((n) => (
              <section className="panel case-form" key={n.id}>
                <strong
                  className={
                    n.level === "error"
                      ? "error"
                      : n.level === "warning"
                        ? "warning"
                        : ""
                  }
                >
                  {n.message}
                </strong>
                <div className="row-actions">
                  <NavLink to={n.link}>Abrir módulo</NavLink>
                  {!n.acknowledged && (
                    <button
                      disabled={busy}
                      onClick={() =>
                        act(async () => {
                          await api.post("/notifications/acknowledge", {
                            notification_id: n.id,
                          });
                        })
                      }
                    >
                      Marcar como visto
                    </button>
                  )}
                  {n.acknowledged && <span>Reconhecido</span>}
                </div>
              </section>
            ))}
          {!data.items.some((n) => showRead || !n.acknowledged) && (
            <p>Nenhum aviso nesta seleção.</p>
          )}
        </>
      )}
    </>
  );
}
type Checklist = {
  pending: number;
  checks: { key: string; label: string; passed: boolean }[];
  domains: {
    id: number;
    domain: string;
    analyzed: boolean;
    collection_complete: boolean;
    recent_24h: boolean;
    human_review_recorded: boolean;
  }[];
  limitations: string;
};
export function CaseChecklist({
  id,
  revision,
}: {
  id: number;
  revision: number;
}) {
  const [open, setOpen] = useState(false),
    [data, setData] = useState<Checklist | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    let live = true;
    setData(null);
    api
      .get<Checklist>(`/cases/${id}/checklist`)
      .then((r) => {
        if (live) {
          setData(r.data);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [id, revision, open]);
  return (
    <div>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Ocultar checklist" : "Ver checklist de revisão"}
      </button>
      {open && (
        <div>
          {error && <p className="error">{error}</p>}
          {!data && !error && <p>Conferindo registros…</p>}
          {data && (
            <>
              <h3>{data.pending} verificações pendentes</h3>
              <ul>
                {data.checks.map((c) => (
                  <li key={c.key}>
                    {c.passed ? "✓" : "Pendente:"} {c.label}
                  </li>
                ))}
              </ul>
              {data.domains.map((d) => (
                <p key={d.id}>
                  {d.domain}:{" "}
                  {!d.analyzed
                    ? "sem análise"
                    : !d.collection_complete
                      ? "coleta incompleta"
                      : !d.recent_24h
                        ? "análise com mais de 24h"
                        : !d.human_review_recorded
                          ? "aguardando parecer humano"
                          : "coleta recente e parecer registrado"}
                </p>
              ))}
              <small>{data.limitations}</small>
            </>
          )}
        </div>
      )}
    </div>
  );
}
