import { useEffect, useState } from "react";
import { api, errorMessage } from "./api";
export function AccountActions() {
  const [action, setAction] = useState("request-reset"),
    [token, setToken] = useState(""),
    [notice, setNotice] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const verify = params.get("verify-email"),
      reset = params.get("reset-password");
    if (verify) {
      setAction("verify-email");
      setToken(verify);
    }
    if (reset) {
      setAction("reset-password");
      setToken(reset);
    }
    window.history.replaceState(null, "", window.location.pathname);
  }, []);
  return (
    <div className="login">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setBusy(true);
          setError("");
          void (async () => {
            try {
              let r;
              if (action === "request-reset")
                r = await api.post("/auth/password/request-reset", {
                  email: f.get("email"),
                });
              else if (action === "verify-email")
                r = await api.post("/auth/email/confirm", { token });
              else {
                if (f.get("new_password") !== f.get("confirm"))
                  throw new Error("Senhas diferentes");
                r = await api.post("/auth/password/reset", {
                  token,
                  new_password: f.get("new_password"),
                  otp_code: f.get("otp_code") || null,
                  recovery_code: f.get("recovery_code") || null,
                });
              }
              setNotice(r.data.notice);
            } catch (e) {
              setError(errorMessage(e));
            } finally {
              setBusy(false);
            }
          })();
        }}
      >
        <span className="eyebrow">BET HUNTER · ACESSO</span>
        <h1>
          {action === "verify-email"
            ? "Confirmar email"
            : action === "reset-password"
              ? "Definir nova senha"
              : "Recuperar acesso"}
        </h1>
        <p>
          Links expiram em 30 minutos e funcionam uma vez. MFA continua
          obrigatório quando ativado.
        </p>
        {notice && <p role="status">{notice}</p>}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {action === "request-reset" ? (
          <label>
            Email
            <input type="email" name="email" required maxLength={254} />
          </label>
        ) : (
          <label>
            Código privado do link
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="off"
              required
              minLength={20}
              maxLength={200}
            />
          </label>
        )}
        {action === "reset-password" && (
          <>
            <label>
              Nova senha
              <input
                name="new_password"
                type="password"
                autoComplete="new-password"
                required
                minLength={15}
                maxLength={128}
              />
            </label>
            <label>
              Confirme a senha
              <input
                name="confirm"
                type="password"
                autoComplete="new-password"
                required
                minLength={15}
                maxLength={128}
              />
            </label>
            <label>
              Código MFA (se ativo)
              <input
                name="otp_code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                autoComplete="one-time-code"
              />
            </label>
            <label>
              Ou código de recuperação
              <input name="recovery_code" maxLength={100} autoComplete="off" />
            </label>
          </>
        )}
        <button className="primary" disabled={busy}>
          {busy
            ? "Processando…"
            : action === "request-reset"
              ? "Solicitar mensagem"
              : "Confirmar"}
        </button>
        <a href="/">Voltar ao login</a>
        <small>
          Servidor local de email captura mensagens para testes e não entrega
          para a internet. Use a caixa local em Segurança ou ./iniciar.sh inbox.
        </small>
      </form>
    </div>
  );
}
