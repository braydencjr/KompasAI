// The FastAPI backend. NEXT_PUBLIC_ values are visible in the browser, so this must never hold a secret.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** POSTs JSON and returns the parsed reply, or throws with the server's error message. */
export async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new ApiError(`Can't reach the Kompas server at ${API_URL}.`, 0);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(data?.detail ?? `Request failed (${res.status})`, res.status);
  return data as T;
}
