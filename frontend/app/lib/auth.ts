import { API_URL, ApiError } from "./api";

export const PASSWORD_MIN = 8;

export type AuthUser = { id: number; email: string; name: string };

// The session token lives in this browser only. It's a random string the server can revoke, not a password.
const TOKEN_KEY = "kompas:auth-token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {}
}

async function call<T>(path: string, init: { method?: string; body?: unknown; token?: string | null } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/auth${path}`, {
      method: init.method ?? (init.body === undefined ? "GET" : "POST"),
      headers: { "Content-Type": "application/json", ...(init.token ? { Authorization: `Bearer ${init.token}` } : {}) },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch {
    throw new ApiError(`Can't reach the Kompas server at ${API_URL}.`, 0);
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    throw new ApiError(typeof detail === "string" ? detail : "Check the details and try again.", res.status);
  }
  return data as T;
}

export type Session = { token: string; user: AuthUser };
export type Saved = { data: Record<string, unknown> | null; updated_at: string | null };

export const authApi = {
  signUp: (email: string, password: string, name: string) => call<Session>("/signup", { body: { email, password, name } }),
  signIn: (email: string, password: string) => call<Session>("/login", { body: { email, password } }),
  signOut: (token: string) => call<void>("/logout", { method: "POST", token }),
  me: (token: string) => call<{ user: AuthUser }>("/me", { token }),
  getProgress: (token: string) => call<Saved>("/progress", { token }),
  putProgress: (token: string, data: Record<string, unknown>) => call<{ updated_at: string }>("/progress", { method: "PUT", token, body: { data } }),
};
