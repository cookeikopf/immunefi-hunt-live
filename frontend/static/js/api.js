/* API-Client: JWT-Handling, Fehlerbehandlung, 401 → Login. */

const TOKEN_KEY = "kmuos_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export async function api(path, { method = "GET", body, headers = {} } = {}) {
  const h = { ...headers };
  let payload = body;
  if (payload !== undefined && !(payload instanceof FormData)) {
    h["Content-Type"] = "application/json";
    payload = JSON.stringify(payload);
  }
  const token = getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, { method, headers: h, body: payload });
  if (res.status === 401) {
    clearToken();
    if (!location.hash.startsWith("#/login")) location.hash = "#/login";
    throw new Error("Anmeldung erforderlich");
  }
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data.detail) message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch { /* Körper war kein JSON */ }
    throw new Error(message);
  }
  if (res.status === 204) return null;
  return res.json();
}
