// SPDX-License-Identifier: AGPL-3.0-only
// Inspector data (I1): one call per chart returns every target (plan §8). Kept in memory per
// "profile|chart" and revalidated with the ETag, so reopening is instant and a 304 costs nothing.
import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import type { components } from "../../api/schema.gen";
import type { ChartId } from "./urlState";

export type InspectionSet = components["schemas"]["InspectionSet"];
export type InspectionBundle = components["schemas"]["InspectionBundle"];

const cache = new Map<string, { etag: string; data: InspectionSet }>();
const inflight = new Map<string, Promise<InspectionSet>>();

export function clearInspectCache(): void { cache.clear(); inflight.clear(); }

export async function loadInspectSet(profileId: string, chart: ChartId): Promise<InspectionSet> {
  const key = `${profileId}|${chart}`;
  const pending = inflight.get(key);
  if (pending) return pending;               // a click during prefetch shares the same request
  const hit = cache.get(key);
  const p = (async () => {
    let res: Response;
    try {
      res = await fetch(`/v1/profiles/${encodeURIComponent(profileId)}/inspect/${chart}`, {
        headers: { "x-requested-with": "pranix-spa", ...(hit ? { "if-none-match": hit.etag } : {}) },
      });
    } catch { throw new ApiError(0, null); }
    if (res.status === 304 && hit) return hit.data;
    if (!res.ok) {
      let problem = null;
      try { problem = await res.json(); } catch { /* not JSON */ }
      throw new ApiError(res.status, problem);
    }
    const data = (await res.json()) as InspectionSet;
    cache.set(key, { etag: res.headers.get("etag") ?? "", data });
    return data;
  })().finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
}

/** Warm the cache when the dashboard is idle (plan §16.2). Errors are ignored: a click retries. */
export function prefetchInspect(profileId: string, chart: ChartId): void {
  loadInspectSet(profileId, chart).catch(() => {});
}

export type Load = { state: "idle" | "loading" } | { state: "ready"; data: InspectionSet } | { state: "error"; error: ApiError };

export function useInspectSet(profileId: string | null, chart: ChartId | null, retryKey = 0): Load {
  const [load, setLoad] = useState<Load>({ state: "idle" });
  useEffect(() => {
    if (!profileId || !chart) { setLoad({ state: "idle" }); return; }
    let live = true;                         // last request wins (stale responses are dropped)
    const hit = cache.get(`${profileId}|${chart}`);
    setLoad(hit ? { state: "ready", data: hit.data } : { state: "loading" });
    loadInspectSet(profileId, chart)
      .then((data) => { if (live) setLoad({ state: "ready", data }); })
      .catch((error: ApiError) => { if (live) setLoad({ state: "error", error }); });
    return () => { live = false; };
  }, [profileId, chart, retryKey]);
  return load;
}
