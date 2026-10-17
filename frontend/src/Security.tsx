import { useEffect, useState } from "react";
import { api, errorMessage } from "./api";
import type { User } from "./types";
type Action = (fn: () => Promise<void>) => Promise<void>;
type State = {
  mfa_enabled: boolean;
  mfa_available: boolean;
  admin_mfa_required: boolean;
  session_idle_minutes: number;
  email_verified: boolean;
  smtp_mode: string;
};
type Session = {
  id: string;
  current: boolean;
  created: string;
  last_seen: string;
  expires: string;
};
type Invite = {
  id: number;
  email: string;
  role: string;
  expires: string;
  used_at: string | null;
  revoked: boolean;
};
const proof = (f: FormData) => ({
  password: String(f.get("password")),
  otp_code: f.get("otp_code") || null,
  recovery_code: f.get("recovery_code") || null,
});
function ProofFields({ mfa }: { mfa: boolean }) {
  return (
    <>
      <label>
        Senha atual
        <input
          name="password"
          type="password"
          required
          maxLength={128}
          autoComplete="current-password"
        />
      </label>
      {mfa && (
        <>
          <label>
            Código atual do autenticador
            <input
              name="otp_code"
              pattern="[0-9]{6}"
              inputMode="numeric"
              autoComplete="one-time-code"
            />
          </label>
          <label>
            Ou código de recuperação
            <input name="recovery_code" maxLength={100} autoComplete="off" />
          </label>
        </>
      )}
    </>
  );
}
export function SecurityPage({
  user,
  revision,
  busy,
  act,
  onSession,
  onLogout,
}: {
  user: User;
  revision: number;
  busy: boolean;
  act: Action;
  onSession: (u: User) => void;
  onLogout: () => void;
}) {
  const [state, setState] = useState<State | null>(null),
    [sessions, setSessions] = useState<Session[]>([]),
    [invites, setInvites] = useState<Invite[]>([]),
    [error, setError] = useState(""),
    [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null),
    [codes, setCodes] = useState<string[]>([]),
    [token, setToken] = useState(""),
    [notice, setNotice] = useState("");
  useEffect(() => {
    let live = true;
    async function load() {
      try {
        const [s, ss] = await Promise.all([
          api.get<State>("/auth/security"),
          api.get<Session[]>("/auth/sessions"),
        ]);
        if (!live) return;
        setState(s.data);
        setSessions(ss.data);
        if (
          user.role === "admin" &&
          (!s.data.admin_mfa_required || s.data.mfa_enabled)
        ) {
          const i = await api.get<Invite[]>("/security/invitations");
          if (live) setInvites(i.data);
        }
        setError("");
      } catch (e) {
        if (live) setError(errorMessage(e));
      }
    }
    void load();
    return () => {
      live = false;
    };
  }, [revision, user.role]);
  const [inbox, setInbox] = useState<{ subject: string; body: string }[]>([]);
  const mfa = state?.mfa_enabled ?? user.mfa_enabled;
  return (
    <>
      <div className="page-title">
        <div>
          <span className="eyebrow">IDENTIDADE E ACESSO</span>
          <h1>Segurança da conta</h1>
          <p>Proteja o acesso e revise as sessões autenticadas.</p>
        </div>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="warning">
          {notice}
        </p>
      )}
      <section className="panel case-form">
        <h2>Confirmação de email</h2>
        <p>
          {state?.email_verified
            ? "Confirmação registrada"
            : "Email ainda não confirmado"}{" "}
          · Modo: {state?.smtp_mode ?? "aguardando"}
        </p>
        <button
          disabled={busy}
          onClick={() =>
            act(async () => {
              const r = await api.post("/auth/email/request");
              setNotice(r.data.notice);
            })
          }
        >
          Solicitar confirmação
        </button>
        {state?.smtp_mode === "local" && (
          <>
            <p className="warning">
              Servidor LOCAL DE TESTE. Não envia mensagens para a internet e não
              comprova posse de uma caixa real.
            </p>
            <button
              onClick={() =>
                act(async () => {
                  const r = await api.get("/auth/email/local-inbox");
                  setInbox(r.data.items);
                })
              }
            >
              Abrir caixa local de teste
            </button>
            {inbox.map((m, i) => (
              <details key={i}>
                <summary>{m.subject}</summary>
                <pre>{m.body}</pre>
                <a href={m.body.match(/https?:\/\/[^\s]+/)?.[0] ?? "/account"}>
                  Abrir ação do email
                </a>
              </details>
            ))}
          </>
        )}
      </section>
      <section className="panel case-form">
        <h2>Autenticação em duas etapas</h2>
        <p>
          {mfa ? "Ativada" : "Ainda não ativada"}. Sessões expiram após{" "}
          {state?.session_idle_minutes ?? 30} minutos sem interação.
          Atualizações automáticas não renovam a sessão. Administradores
          precisam de MFA para administrar a instalação.
        </p>
        {!state?.mfa_available && (
          <p className="warning">
            O servidor precisa de AUTH_ENCRYPTION_KEY para configurar o
            autenticador. O inicializador local cria e preserva essa chave.
          </p>
        )}
        {!mfa && state?.mfa_available && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void act(async () => {
                setCodes([]);
                const r = await api.post("/auth/mfa/setup", proof(f));
                setSetup(r.data);
              });
            }}
          >
            <ProofFields mfa={false} />
            <button disabled={busy}>Configurar autenticador</button>
          </form>
        )}
        {setup && !mfa && (
          <div className="verdict">
            <h3>Adicione a chave ao seu aplicativo autenticador</h3>
            <p>Chave manual (privada, válida por 10 minutos):</p>
            <code className="secret">{setup.secret}</code>
            <details>
              <summary>URI para importação no autenticador</summary>
              <code className="secret">{setup.uri}</code>
            </details>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void act(async () => {
                  const r = await api.post("/auth/mfa/confirm", {
                    code: f.get("code"),
                  });
                  onSession(r.data.user);
                  setCodes(r.data.recovery_codes);
                  setSetup(null);
                });
              }}
            >
              <label>
                Código do aplicativo
                <input
                  name="code"
                  pattern="[0-9]{6}"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                />
              </label>
              <button disabled={busy} className="primary">
                Confirmar e ativar
              </button>
            </form>
          </div>
        )}
        {codes.length > 0 && (
          <div className="verdict">
            <h3>Guarde seus oito códigos de recuperação</h3>
            <p>
              Exibidos somente agora. Cada código funciona uma vez. Armazene em
              um gerenciador de senhas e evite compartilhar capturas de tela.
            </p>
            <pre>{codes.join("\n")}</pre>
            <button onClick={() => setCodes([])}>Já guardei os códigos</button>
          </div>
        )}
        {mfa && (
          <details>
            <summary>Desativar autenticação em duas etapas</summary>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void act(async () => {
                  await api.post("/auth/mfa/disable", proof(f));
                  onLogout();
                });
              }}
            >
              <ProofFields mfa={mfa} />
              <button disabled={busy}>Desativar e encerrar sessões</button>
            </form>
          </details>
        )}
        <p className="muted">
          Um código TOTP já utilizado não pode ser reutilizado. Aguarde o
          próximo código para outra operação sensível.
        </p>
      </section>
      <section className="panel case-form">
        <h2>Alterar senha</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget,
              f = new FormData(form);
            void act(async () => {
              if (f.get("new_password") !== f.get("confirm"))
                throw new Error("As novas senhas não coincidem");
              const r = await api.post<User>("/auth/password", {
                ...proof(f),
                new_password: f.get("new_password"),
              });
              onSession(r.data);
              form.reset();
              setNotice("Senha alterada. As outras sessões foram encerradas.");
            });
          }}
        >
          <ProofFields mfa={mfa} />
          <label>
            Nova senha
            <input
              type="password"
              name="new_password"
              minLength={15}
              maxLength={128}
              autoComplete="new-password"
              required
            />
          </label>
          <label>
            Confirme a nova senha
            <input
              type="password"
              name="confirm"
              minLength={15}
              maxLength={128}
              autoComplete="new-password"
              required
            />
          </label>
          <button disabled={busy}>Atualizar senha</button>
        </form>
      </section>
      <section className="panel case-form">
        <h2>Sessões da conta</h2>
        {sessions.map((s) => (
          <p key={s.id}>
            {s.current ? "Esta sessão" : "Outra sessão"} · Última atividade:{" "}
            {new Date(s.last_seen).toLocaleString("pt-BR")} · Expira:{" "}
            {new Date(s.expires).toLocaleString("pt-BR")}
          </p>
        ))}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void act(async () => {
              const r = await api.post(
                "/auth/sessions/revoke-others",
                proof(f),
              );
              setNotice(`${r.data.revoked} outra(s) sessão(ões) encerrada(s).`);
            });
          }}
        >
          <ProofFields mfa={mfa} />
          <button disabled={busy}>Encerrar outras sessões</button>
        </form>
      </section>
      {user.role === "admin" && (
        <section className="panel case-form">
          <h2>Convites de cadastro</h2>
          <p>
            Convites individuais vinculados ao email, de uso único e com
            expiração. O convite não verifica a posse da caixa postal. Envie o
            código por um canal privado.
          </p>
          {!mfa && state?.admin_mfa_required ? (
            <p className="warning">Ative MFA para emitir e revogar convites.</p>
          ) : (
            <>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  void act(async () => {
                    const r = await api.post("/security/invitations", {
                      ...proof(f),
                      email: f.get("email"),
                      role: f.get("role"),
                      hours: 24,
                    });
                    setToken(r.data.token);
                  });
                }}
              >
                <label>
                  Email do convidado
                  <input name="email" type="email" required maxLength={254} />
                </label>
                <label>
                  Permissão
                  <select name="role">
                    <option value="analyst">Analista</option>
                    <option value="viewer">Somente leitura</option>
                  </select>
                </label>
                <ProofFields mfa={mfa} />
                <button disabled={busy}>Gerar convite por 24 horas</button>
              </form>
              {token && (
                <div className="verdict">
                  <p>Código exibido somente nesta tela:</p>
                  <code className="secret">{token}</code>
                  <button onClick={() => setToken("")}>Ocultar código</button>
                </div>
              )}
              {invites.map((i) => (
                <details key={i.id}>
                  <summary>
                    {i.email} ·{" "}
                    {i.used_at
                      ? "Utilizado"
                      : i.revoked
                        ? "Revogado"
                        : new Date(i.expires) < new Date()
                          ? "Expirado"
                          : "Pendente"}
                  </summary>
                  <p>
                    Permissão: {i.role} · Expira:{" "}
                    {new Date(i.expires).toLocaleString("pt-BR")}
                  </p>
                  {!i.used_at && !i.revoked && (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        void act(async () => {
                          await api.post(
                            `/security/invitations/${i.id}/revoke`,
                            proof(f),
                          );
                        });
                      }}
                    >
                      <ProofFields mfa={mfa} />
                      <button disabled={busy}>Revogar convite</button>
                    </form>
                  )}
                </details>
              ))}
            </>
          )}
        </section>
      )}
    </>
  );
}
