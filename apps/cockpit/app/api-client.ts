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

/** Authenticated call -- for the one mutating action (send to paper
 * trading). Throws with the backend's own error message on failure rather
 * than failing silently. */
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
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail =
      typeof payload.detail === "string" ? payload.detail : response.statusText || "Request failed";
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export { apiBase };
