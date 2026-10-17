import { useEffect, useState } from "react";
import { api, errorMessage } from "./api";
type Diagnostics = {
  worker_healthy: boolean;
  worker_stage: string | null;
  enabled: boolean;
  minimum_score: number;
  daily_used: number;
  daily_limit: number;
  next_collection: string | null;
  queue_pending: number;
  feeds: {
    id: number;
    name: string;
    enabled: boolean;
    next_run: string;
    error: string;
    interval_hours: number;
    batch_size: number;
  }[];
};
export function AutomationHealth({
  revision,
  busy,
  act,
}: {
  revision: number;
  busy: boolean;
  act: (fn: () => Promise<void>) => Promise<void>;
}) {
  const [data, setData] = useState<Diagnostics | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  useEffect(() => {
    let live = true,
      pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const r = await api.get<Diagnostics>("/automation/diagnostics");
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
    <section className="panel case-form">
      <h2>Diagnóstico da automação</h2>
      {error && <p className="error">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {data && (
        <>
          <p>
            <strong>
              {data.worker_healthy
                ? "Worker com sinal recente"
                : "Worker sem sinal recente"}
            </strong>{" "}
            · {data.enabled ? "Automação habilitada" : "Automação pausada"}
          </p>
          {!data.worker_healthy && (
            <p className="error">
              A descoberta automática e os PDFs precisam do worker. Reinicie
              pelo terminal com ./iniciar.sh. PDFs manuais também podem ser
              processados em Relatórios.
            </p>
          )}
          <p>
            {data.queue_pending} candidatos aguardando · {data.daily_used}/
            {data.daily_limit} tentativas hoje · PDF automático a partir de
            score {data.minimum_score}.
          </p>
          {data.daily_used >= data.daily_limit && (
            <p>
              Cota diária atingida. A fila poderá continuar após a virada do dia
              UTC; a descoberta de fontes mantém seu agendamento.
            </p>
          )}
          {data.minimum_score > 40 && (
            <p>
              O limite de PDF está acima dos fatores técnicos padrão. Isso pode
              deixar análises sem casos ou relatórios automáticos. O perfil
              abaixo usa score 25 para revisão humana.
            </p>
          )}
          {data.feeds.map((f) => (
            <p key={f.id}>
              {f.name}: {f.enabled ? "ativa" : "pausada"}, até {f.batch_size}{" "}
              candidatos a cada {f.interval_hours}h. Próxima consulta:{" "}
              {new Date(f.next_run).toLocaleString("pt-BR")}.
              {f.error && <span className="error"> Falha: {f.error}</span>}
            </p>
          ))}
          {!data.feeds.length && (
            <p>Nenhuma fonte configurada para esta conta.</p>
          )}
        </>
      )}
      <button
        disabled={busy}
        onClick={() =>
          act(async () => {
            const r = await api.post("/automation/continuous");
            setNotice(r.data.notice);
          })
        }
      >
        Ativar descoberta horária e PDFs de revisão
      </button>
      <p>
        Ativa a fonte padrão com até 100 candidatos por consulta, respeitando
        cotas e destinos públicos seguros. Não verifica toda a internet e não
        declara ilegalidade. Monitoramentos individuais são preservados.
      </p>
    </section>
  );
}
