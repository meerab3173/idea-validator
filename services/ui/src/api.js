// All calls go to the gateway (M1). The address comes from /config.js at runtime.
const base = () => (window.__CONFIG__ && window.__CONFIG__.API_URL) || "/api";

let token = sessionStorage.getItem("token") || "";
export const setToken = (t) => { token = t; sessionStorage.setItem("token", t); };
export const getToken = () => token;

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(base() + path, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : `HTTP ${res.status}`);
  return data;
}

// Live progress (U3): Server-Sent Events from /runs/{id}/events.
export function streamRun(runId, onEvent, onEnd) {
  const es = new EventSource(`${base()}/runs/${runId}/events?token=${encodeURIComponent(token)}`);
  es.onmessage = (m) => onEvent(JSON.parse(m.data));
  es.addEventListener("end", (m) => { es.close(); onEnd(JSON.parse(m.data)); });
  es.onerror = () => { es.close(); onEnd({ state: "DISCONNECTED" }); };
  return () => es.close();
}
