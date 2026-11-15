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
