const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "aegis_cockpit_token";

export type LoginResponse = {
  access_token: string;
  token_type: string;
  role: string;
  expires_in_minutes: number;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${apiBase}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Login failed");
  }
  return (await response.json()) as LoginResponse;
}

/** Plain read -- the cockpit's chart/signal endpoints are open reads, same as
 * the rest of the API (GET /api/v1/instruments etc.). No token required. */
export async function apiGet<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${apiBase}${path}`, { cache: "no-store" });
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

/** Authenticated call -- for mutating actions (approve/reject, run backtest,
 * send to paper trading, etc). Throws with the backend's own error message
 * on failure rather than failing silently. Every authenticated-endpoint
 * auth failure (missing/expired/invalid token) comes back as a bare 401 --
 * RequireAuth only checks whether a token is *present* in localStorage, not
 * whether it's still valid, so a stale token otherwise gets the user stuck
 * looking at a dead-end "Token has expired." banner with no way forward.
 * Clear it and bounce to /login instead, so re-authenticating is one click. */
export async function authPost<T>(path: string, body?: unknown): Promise<T> {
  const token = getToken();
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.assign("/login");
    }
    throw new Error("Your session has expired -- signing you out.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(extractErrorDetail(payload.detail) ?? response.statusText ?? "Request failed");
  }
  return (await response.json()) as T;
}

/** The backend returns `detail` as either a plain string or a structured
 * object (e.g. {"code": "..."} or {"state": ..., "label": ..., ...} for the
 * NO_REAL_HISTORICAL_DATA_CAPTURED family) -- surface whichever real text is
 * there rather than silently collapsing to a generic HTTP status phrase. */
function extractErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    const candidate = record.label ?? record.code ?? record.state;
    if (typeof candidate === "string") return candidate;
    return JSON.stringify(detail);
  }
  return null;
}

export { apiBase };
