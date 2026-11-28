// SPDX-License-Identifier: AGPL-3.0-only
// Dasha timeline tab (FR-UI-4, D58): life bar of the Mahadashas with a "now" marker, and a tree
// that loads one level at a time; the current chain opens by default. D84: after 120 years the
// sequence starts again, so an older chart opens on the run that contains today, with the first
// run (from birth) one tap away.
import { useEffect, useState, type ReactElement } from "react";
import { api, ApiError } from "../api/client";
import type { DashaPeriod } from "../api/types";
import { ABBR, shortDate, span } from "../lib/format";
import { PLANET_COLOR } from "./config";

const LEVEL = ["", "Mahadasha", "Antardasha", "Pratyantar", "Sookshma", "Prana"];

export default function DashaTimeline({ profileId, onExpired }: { profileId: string; onExpired(): void }) {
  const [top, setTop] = useState<DashaPeriod[] | null>(null);
  const [kids, setKids] = useState<Record<string, DashaPeriod[]>>({});
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [err, setErr] = useState("");
  const [view, setView] = useState<number | undefined>(undefined); // undefined: the run containing today
  const [currentCycle, setCurrentCycle] = useState(1);

  const load = async (path?: string, cycle?: number): Promise<DashaPeriod[] | null> => {
    try { return await api.dasha(profileId, path, cycle); } catch (e) {
      const a = e as ApiError;
      if (a.status === 410) onExpired();
      else setErr(a.code === "BIRTH_TIME_REQUIRED" ? "The timeline needs your birth time, because your periods changed during your birth day." : "We could not load the timeline just now.");
      return null;
    }
  };

  useEffect(() => {
    (async () => {
      setTop(null); setKids({}); setOpen(new Set());
      const t = await load(undefined, view);
      if (!t) return;
      if (t.length === 0) { setErr("We could not load the timeline just now."); return; } // never from our server, but don't crash
      setTop(t);
      if (view === undefined) setCurrentCycle(t[0].cycle ?? 1);
      // Open the current chain, level by level.
      let level = t, opened = new Set<string>(), loaded: Record<string, DashaPeriod[]> = {};
      for (let depth = 0; depth < 3; depth++) {
        const now = level.find((p) => p.contains_now);
        if (!now || now.level >= 5) break;
        const c = await load(now.path, now.cycle);
        if (!c) break;
        opened = new Set(opened).add(now.path); loaded = { ...loaded, [now.path]: c }; level = c;
      }
      setKids(loaded); setOpen(opened);
    })();
  }, [profileId, view]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = async (p: DashaPeriod) => {
    const n = new Set(open);
    if (n.has(p.path)) { n.delete(p.path); setOpen(n); return; }
    if (!kids[p.path]) { const c = await load(p.path, p.cycle); if (!c) return; setKids((k) => ({ ...k, [p.path]: c })); }
    n.add(p.path); setOpen(n);
  };

  if (err) return <p className="lead">{err}</p>;
  if (!top) return <div className="skel" style={{ width: "60%" }} />;
  const shown = top[0].cycle ?? 1;
  const start = new Date(top[0].start).getTime(), end = new Date(top[8].end).getTime(), now = Date.now();
  const nowPct = Math.max(0, Math.min(100, ((now - start) / (end - start)) * 100));
  const chain: string[] = [];
  let level: DashaPeriod[] | undefined = top;
  while (level) {
    const cur: DashaPeriod | undefined = level.find((p) => p.contains_now);
    if (!cur) break;
    chain.push(cur.lord); level = kids[cur.path];
  }

  const rows: ReactElement[] = [];
  const walk = (list: DashaPeriod[], depth: number) => {
    for (const p of list) {
      const past = new Date(p.end).getTime() < now;
      const isOpen = open.has(p.path);
      rows.push(
        <div key={p.path} role="treeitem" aria-level={p.level} aria-expanded={p.level < 5 ? isOpen : undefined}
          className={`drow ${p.contains_now ? "now" : past ? "past" : ""}`} style={{ marginLeft: depth * 22 }}>
          <button type="button" className="chev" aria-disabled={p.level >= 5} aria-label={`${isOpen ? "Close" : "Open"} ${p.lord} ${LEVEL[p.level]}`}
            onClick={() => p.level < 5 && toggle(p)}>{isOpen ? "−" : "+"}</button>
          <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
            <span style={{ fontSize: 15, color: "#fff" }}><strong>{p.lord}</strong> <span style={{ color: "var(--muted)", fontSize: 13 }}>{LEVEL[p.level]}</span></span>
            <span style={{ fontSize: 13, color: "var(--muted)" }}>{shortDate(p.start)} to {shortDate(p.end)}{p.from_birth ? " (from birth)" : ""}</span>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 13, color: "var(--text2)" }}>{span(p.start, p.end)}</span>
            {p.contains_now && <span className="badge" style={{ background: "var(--gold)", color: "#1A1226" }}>Now</span>}
          </div>
        </div>,
      );
      if (isOpen && kids[p.path]) walk(kids[p.path], depth + 1);
    }
  };
  walk(top, 0);

  return (
    <div id="dasha" style={{ display: "flex", flexDirection: "column", gap: 20, background: "radial-gradient(80% 60% at 0% 0%,rgba(139,124,246,.1),transparent 60%),#12123A", border: "1px solid rgba(255,255,255,.14)", borderRadius: 24, padding: 24 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <strong style={{ font: "600 24px var(--serif)", color: "#fff" }}>Your life periods (Vimshottari Dasha)</strong>
        <span style={{ fontSize: 14, lineHeight: 1.55, color: "var(--muted)" }}>Nine planetary periods in a fixed order, starting from the Moon's position at your birth. Open a period to see the shorter periods inside it.</span>
      </div>
      {currentCycle > 1 && (
        <div role="note" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between", border: "1px solid rgba(244,197,102,.35)", borderRadius: 14, padding: "12px 16px" }}>
          <span style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text2)" }}>
            {shown === currentCycle
              ? `The nine periods last a hundred and twenty years in all. Your first run ended, so the sequence began again on ${shortDate(top[0].start)}. You are in its next run now.`
              : "This is your first run of the sequence, from your birth."}
          </span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setView(shown === currentCycle ? 1 : undefined)}>
            {shown === currentCycle ? "Show the first run, from birth" : "Show the current run"}
          </button>
        </div>
      )}
      <div className="lifebar" role="img" aria-label={`Life periods from ${top[0].lord} to ${top[8].lord}; now in ${chain[0] ?? "none"}`}>
        {top.map((p) => <span key={p.path} title={`${p.lord}: ${shortDate(p.start)} to ${shortDate(p.end)}`} style={{ width: `${((new Date(p.end).getTime() - new Date(p.start).getTime()) / (end - start)) * 100}%`, background: PLANET_COLOR[p.lord] }}>{ABBR[p.lord]}</span>)}
        <span className="nowmark" style={{ left: `${nowPct}%` }} aria-hidden="true" />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--faint)" }}><span>{shortDate(top[0].start)}</span><span>Now: {shortDate(new Date().toISOString())}</span><span>{shortDate(top[8].end)}</span></div>
      <div role="tree" aria-label="Dasha periods" style={{ display: "flex", flexDirection: "column", gap: 4 }}>{rows}</div>
      <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6, fontSize: 14, lineHeight: 1.55, color: "var(--text2)" }}>
        {chain.length > 0 && <li>Your current chain: {chain.join(" → ")}.</li>}
        <li>Periods describe themes to reflect on, not events. Dates use a year of 365.25 days.</li>
        <li>The shortest levels (Sookshma and Prana) last days or hours, so they depend on an exact birth minute.</li>
      </ul>
    </div>
  );
}
