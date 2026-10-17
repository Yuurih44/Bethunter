import axios from "axios";
export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
  timeout: 70000,
});
export function csrf(value: string) {
  api.defaults.headers.common["X-CSRF-Token"] = value;
}
export async function download(path: string, name: string, body?: unknown) {
  const res = body
    ? await api.post(path, body, { responseType: "blob" })
    : await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const d = error.response?.data?.detail;
    if (error.response?.status === 404 && d === "Not Found") {
      return "A API não reconhece esta rota. Reinicie o BetHunter no terminal para carregar a atualização.";
    }
    return typeof d === "string"
      ? d
      : Array.isArray(d)
        ? d.map((x) => x.msg).join("; ")
        : error.response
          ? `Falha HTTP ${error.response.status}`
          : "Não foi possível conectar ao backend";
  }
  return error instanceof Error ? error.message : "Falha inesperada";
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    if (
      error.response?.status === 401 &&
      (error.config?.method === "get" ||
        detail === "Sessão expirada" ||
        detail === "Autenticação necessária")
    ) {
      if (error.config?.url !== "/auth/me")
        window.dispatchEvent(new Event("bethunter-session-expired"));
    }
    return Promise.reject(error);
  },
);
