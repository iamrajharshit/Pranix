// SPDX-License-Identifier: AGPL-3.0-only
import type { DashaPeriod, Nearest, Place, Problem, Profile } from "./types";

export class ApiError extends Error {
  constructor(public status: number, public problem: Problem | null) {
    super(problem?.code ?? `HTTP_${status}`);
  }
  get code(): string { return this.problem?.code ?? (this.status === 0 ? "NETWORK" : `HTTP_${this.status}`); }
}

const TIMEOUT_MS = 8000; // after this the loader becomes the waking time-wheel (HOST-05)

async function call<T>(path: string, init: RequestInit = {}, timeout = TIMEOUT_MS): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  let res: Response;
  try {
    res = await fetch(path, { ...init, signal: init.signal ?? ctl.signal,
      headers: { "content-type": "application/json", "x-requested-with": "pranix-spa", ...(init.headers ?? {}) } });
  } catch {
    throw new ApiError(0, null);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let problem: Problem | null = null;
    try { problem = (await res.json()) as Problem; } catch { /* not JSON */ }
    if (problem && res.headers.get("retry-after")) problem.retry_after = Number(res.headers.get("retry-after"));
    throw new ApiError(res.status, problem);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export interface BirthRequest {
  place: { place_id: string } | { lat: number; lon: number };
  local_datetime: string; birth_time_known: boolean;
  time_accuracy?: "exact" | "approx_5m" | "approx_30m" | "approx_1h";
  disambiguation?: "earlier" | "later";
}

export const api = {
  healthz: () => call<{ status: string }>("/healthz", {}, 60_000),
  version: () => call<{ ai_providers: string[]; feature_flags: Record<string, boolean>; ephemeris_mode: string }>("/version"),
  places: (q: string, signal?: AbortSignal) => call<Place[]>(`/v1/places?q=${encodeURIComponent(q)}&limit=8`, { signal }),
  nearest: (lat: number, lon: number) => call<Nearest>(`/v1/places/nearest?lat=${lat}&lon=${lon}`),
  createProfile: (body: BirthRequest) =>
    call<Profile>("/v1/profiles", { method: "POST", body: JSON.stringify(body), headers: { "x-age-confirmed": "true" } }),
  getProfile: (id: string) => call<Profile>(`/v1/profiles/${encodeURIComponent(id)}`),
  deleteProfile: (id: string) => call<void>(`/v1/profiles/${encodeURIComponent(id)}`, { method: "DELETE" }),
  dasha: (id: string, path?: string) =>
    call<DashaPeriod[]>(`/v1/profiles/${encodeURIComponent(id)}/dasha${path ? `?path=${encodeURIComponent(path)}` : ""}`),
  cardImageUrl: (id: string, module: string) => `/v1/profiles/${encodeURIComponent(id)}/cards/${module}.png`,
};
