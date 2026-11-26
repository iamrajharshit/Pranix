// SPDX-License-Identifier: AGPL-3.0-only
// Insight stream (FR-DASH-06, FR-DASH-19): plan -> insight* -> done. Events for another chart are
// dropped; a dropped stream reconnects once after two seconds, asking only for missing modules.
import type { InsightCard } from "./types";

export interface StreamHandlers {
  plan(modules: string[]): void;
  card(card: InsightCard): void;
  done(degraded: boolean): void;
  failed(missing: string[], expired: boolean): void;
}

export function streamInsights(profileId: string, h: StreamHandlers, modules?: string[]): () => void {
  let es: EventSource | null = null;
  let closed = false;
  let retried = false;
  let planned: string[] = [];
  const got = new Set<string>();

  const open = (only?: string[]) => {
    const q = only && only.length ? `?modules=${only.join(",")}` : "";
    es = new EventSource(`/v1/profiles/${encodeURIComponent(profileId)}/insights${q}`);
    es.addEventListener("plan", (e) => {
      const d = JSON.parse((e as MessageEvent).data) as { modules: string[]; chart_ref: string };
      if (d.chart_ref !== profileId) return;
      if (!planned.length) { planned = d.modules; h.plan(d.modules); }
    });
    es.addEventListener("insight", (e) => {
      const c = JSON.parse((e as MessageEvent).data) as InsightCard;
      if (c.chart_ref !== profileId) return; // stale event from a previous chart
      got.add(c.module_id);
      h.card(c);
    });
    es.addEventListener("done", (e) => {
      const d = JSON.parse((e as MessageEvent).data) as { degraded: boolean };
      closed = true; es?.close(); h.done(d.degraded);
    });
    es.onerror = () => {
      if (closed) return;
      es?.close();
      const missing = (planned.length ? planned : modules ?? []).filter((m) => !got.has(m));
      if (!retried && (missing.length || !planned.length)) {
        retried = true;
        setTimeout(() => !closed && open(planned.length ? missing : modules), 2000);
      } else {
        closed = true;
        h.failed(missing, false);
      }
    };
  };
  open(modules);
  return () => { closed = true; es?.close(); };
}

export interface StreamGroup {
  start(h: StreamHandlers, modules?: string[]): void;
  closeAll(): void;
  size(): number;
}

/** Every stream one dashboard opens for one chart: the first, and one per card retry (bug bounty,
 *  26 Nov). closeAll() closes them all, and whatever they still deliver is dropped, so nothing from
 *  this chart can reach the next one. Finished streams leave the group. */
export function streamGroup(profileId: string): StreamGroup {
  const open = new Set<() => void>();
  let alive = true;
  const guard = (h: StreamHandlers, done: () => void): StreamHandlers => ({
    plan: (m) => { if (alive) h.plan(m); },
    card: (c) => { if (alive) h.card(c); },
    done: (d) => { done(); if (alive) h.done(d); },
    failed: (m, e) => { done(); if (alive) h.failed(m, e); },
  });
  return {
    start(h, modules) {
      if (!alive) return;
      let close: () => void = () => {};
      const leave = () => open.delete(close);
      close = streamInsights(profileId, guard(h, leave), modules);
      open.add(close);
    },
    closeAll() { alive = false; open.forEach((c) => c()); open.clear(); },
    size: () => open.size,
  };
}
