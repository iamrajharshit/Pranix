// SPDX-License-Identifier: AGPL-3.0-only
// Board 6: the dashboard. Charts first, then twelve cards in four constellations, streamed over
// SSE. Opening a card flips it into a full-page reading with its own history entry.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { streamInsights } from "../api/sse";
import type { InsightCard, Profile } from "../api/types";
import { Link, Toast, TopBar } from "../components/Shell";
import { navigate } from "../lib/router";
import { store, type Draft } from "../lib/storage";
import { toRequest } from "../lib/validate";
import { Resting } from "../screens/Oracle";
import CardVisual from "./CardVisual";
import ChartsSection, { type ChartTab } from "./ChartsSection";
import { GROUPS, ORDER, withName } from "./config";
import Reading from "./Reading";

const RETRY_COOLDOWN_MS = 10_000;
const RETRY_MAX = 3;
type Status = "streaming" | "ready" | "error" | "unavailable";

function readingFromHash(): string | null {
  const m = window.location.hash.match(/^#reading=([a-z]+)$/);
  return m ? m[1] : null;
}

export default function Dashboard({ profile, draft, onProfile }: { profile: Profile | null; draft: Draft | null; onProfile(p: Profile | null): void }) {
  const [cards, setCards] = useState<Record<string, InsightCard>>({});
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [plan, setPlan] = useState<string[]>([]);
  const [degraded, setDegraded] = useState(false);
  const [open, setOpen] = useState<string | null>(readingFromHash());
  const [flipping, setFlipping] = useState<string | null>(null);
  const [tab, setTab] = useState<ChartTab>("d1");
  const [selected, setSelected] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const [expired, setExpired] = useState(false);
  const [confirmStart, setConfirmStart] = useState(false);
  const [failed, setFailed] = useState(false);
  const retries = useRef<Record<string, { n: number; at: number }>>({});
  const stop = useRef<() => void>(() => {});
  const name = draft?.name.trim() ?? "";

  // Load or refresh the chart: memory -> GET by id -> silent re-POST from the draft (FR-DASH-19).
  const refresh = useCallback(async () => {
    if (!draft) { setExpired(true); return; }
    try {
      setToast("Refreshing your chart…");
      const p = await api.createProfile(toRequest(draft));
      store.setProfileId(p.profile_id); onProfile(p);
    } catch { setFailed(true); }
  }, [draft, onProfile]);

  useEffect(() => {
    if (profile) return;
    const id = store.profileId();
    if (!id && !draft) { navigate("/", true); return; }
    if (!id) { refresh(); return; }
    api.getProfile(id).then(onProfile).catch((e: ApiError) => (e.status === 410 ? refresh() : setFailed(true)));
  }, [profile, refresh, onProfile, draft]);

  const startStream = useCallback((only?: string[]) => {
    if (!profile) return;
    stop.current = streamInsights(profile.profile_id, {
      plan: (mods) => { setPlan(mods); setStatus((s) => ({ ...Object.fromEntries(mods.map((m) => [m, "streaming" as Status])), ...s })); },
      card: (c) => {
        setCards((x) => ({ ...x, [c.module_id]: c }));
        setStatus((s) => ({ ...s, [c.module_id]: c.state === "error" ? "error" : c.state === "unavailable" ? "unavailable" : "ready" }));
      },
      done: (d) => setDegraded((x) => x || d),
      failed: (missing) => setStatus((s) => ({ ...s, ...Object.fromEntries(missing.map((m) => [m, "error" as Status])) })),
    }, only);
  }, [profile]);

  useEffect(() => {
    if (!profile) return;
    setCards({}); setStatus({}); setPlan([]); setDegraded(false); retries.current = {};
    startStream();
    return () => stop.current();
  }, [profile, startStream]);

  // Reading history (FR-DASH-15): Back closes the reading.
  useEffect(() => {
    const on = () => setOpen(readingFromHash());
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  const openCard = (id: string) => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const show = () => { setFlipping(null); window.history.pushState(null, "", `#reading=${id}`); setOpen(id); };
    if (reduce || open) { if (open) window.history.replaceState(null, "", `#reading=${id}`); show(); return; }
    setFlipping(id); setTimeout(show, 650);
  };
  const closeCard = () => {
    const id = open;
    if (readingFromHash()) window.history.back(); else setOpen(null);
    setOpen(null);
    setTimeout(() => document.getElementById(`more-${id}`)?.focus(), 50);
  };

  const retry = (id: string) => {
    const r = retries.current[id] ?? { n: 0, at: 0 };
    if (r.n >= RETRY_MAX) { setToast("This card is not loading right now. Please try again later."); return; }
    if (Date.now() - r.at < RETRY_COOLDOWN_MS) { setToast("Give it a few seconds before trying again."); return; }
    retries.current[id] = { n: r.n + 1, at: Date.now() };
    setStatus((s) => ({ ...s, [id]: "streaming" }));
    startStream([id]);
  };

  const onChip = (factId: string) => {
    const f = profile?.master.facts[factId];
    if (!f) return;
    if (open) closeCard();
    if (f.target.kind === "dasha") setTab("dasha");
    else {
      if (f.target.chart === "d9") setTab("d9"); else if (tab === "dasha") setTab("d1");
      if (f.target.kind === "planet") setSelected(f.target.ref);
    }
    setTimeout(() => document.getElementById("charts")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  };

  const sparks = useMemo(() => Array.from({ length: 14 }, (_, i) => ({ x: 20 + (i * 47) % 60, y: 15 + (i * 31) % 70, dx: ((i * 53) % 160) - 80, dy: ((i * 71) % 160) - 80, d: (i % 5) * 0.04 })), []);

  if (expired) {
    return (
      <div><TopBar />
        <Resting>
          <p className="lead" style={{ maxWidth: 560 }}>This guest chart has expired. Guest charts are kept on the server for a day at most, and we have nothing to recalculate it from.</p>
          <button type="button" className="btn btn-gold" onClick={() => navigate("/details")}>Start again</button>
        </Resting>
      </div>
    );
  }
  if (failed) return <div><TopBar /><Resting onRetry={() => { setFailed(false); onProfile(null); }} /></div>;
  if (!profile) return <div><TopBar /><main className="wrap"><p className="lead" role="status">Opening your map…</p></main></div>;

  const m = profile.master;
  const known = m.meta.birth_time_known;
  const used: Record<string, { done: boolean }> = {}; // per-card name flag (rule 10)
  const readyIds = ORDER.map((o) => o.id).filter((id) => status[id] === "ready" && cards[id]);
  const arrived = plan.filter((id) => status[id] && status[id] !== "streaming").length;
  const reading = open && cards[open] && status[open] === "ready" ? cards[open] : null;
  const dob = draft ? new Date(+draft.yy, +draft.mm - 1, +draft.dd).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" }) : "";
  const where = draft ? (draft.manual ? `${draft.lat}, ${draft.lon}` : draft.place?.name ?? "") : "";

  return (
    <div style={{ position: "relative", background: "radial-gradient(1200px 600px at 80% -10%,rgba(139,124,246,.18),transparent 60%),radial-gradient(900px 500px at -10% 30%,rgba(244,197,102,.07),transparent 60%),#0A0A1E", minHeight: "100vh" }}>
      <div aria-hidden={reading ? true : undefined}>
      <TopBar right={<div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center" }}>
        <button type="button" className="lnk" onClick={() => setConfirmStart(true)}>Start over</button>
        <span className="hint" title="Accounts are coming soon">Saving charts needs an account (coming soon)</span>
      </div>} />
      <main className="wrap" style={{ display: "flex", flexDirection: "column", gap: 48, paddingBottom: 96 }}>
        <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="eyebrow" style={{ color: "var(--gold)" }}>Your cosmic map</div>
          <h1 className="h1m">{name ? `Namaste, ${name}` : "Your cosmic map"}</h1>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <span style={{ fontSize: 15, color: "var(--muted)" }}>{dob && `Born ${dob}`}{where && ` · ${where}`}</span>
            {!known && <span className="badge" style={{ background: "rgba(255,217,160,.14)", border: "1px solid #FFD9A0", color: "#FFD9A0" }}>Birth time unknown</span>}
          </div>
          <p className="lead" style={{ maxWidth: 720 }}>Twelve cards, grouped into four constellations. Each card is a reflection drawn from your birth chart, with the chart facts it rests on. Tap any card to read more.</p>
          <div role="status" aria-live="polite" style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center" }}>
            <div style={{ display: "flex", gap: 6 }} aria-hidden="true">
              {ORDER.map((o) => <span key={o.id} style={{ width: 10, height: 10, borderRadius: "50%", background: status[o.id] && status[o.id] !== "streaming" ? o.group.accent : "rgba(255,255,255,.15)", boxShadow: status[o.id] === "ready" ? `0 0 8px ${o.group.accent}` : "none" }} />)}
            </div>
            <span style={{ fontSize: 14, color: "var(--text2)" }}>{plan.length === 0 ? "Gathering your cards…" : arrived < plan.length ? `${arrived} of ${plan.length} cards have arrived` : "All your cards have arrived"}</span>
          </div>
          {!known && <div style={{ background: "rgba(255,217,160,.08)", border: "1px solid rgba(255,217,160,.5)", borderRadius: 16, padding: "16px 20px", maxWidth: 760, fontSize: 15, lineHeight: 1.6, color: "#FFE7C2" }}>Without a birth time we leave out your rising sign, the houses and both charts, and we only show what stayed true for your whole birth day. Cards that need a time say so.</div>}
          {degraded && <div role="status" style={{ background: "rgba(139,124,246,.1)", border: "1px solid rgba(169,156,255,.5)", borderRadius: 16, padding: "16px 20px", maxWidth: 760, fontSize: 15, lineHeight: 1.6, color: "#DCD6FF" }}>Our AI writer is resting right now, so some cards show our reviewed library text instead. Nothing about your chart changes.</div>}
          <nav aria-label="Sections" style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 8 }}>
            <a className="navpill" href="#charts"><span style={{ color: "var(--gold)" }}>✦</span>Your birth charts</a>
            {GROUPS.map((g) => <a key={g.id} className="navpill" href={`#${g.id}`}><span style={{ color: g.accent }}>{g.numeral}</span>{g.title}</a>)}
            <button type="button" className="navpill soon" aria-disabled="true" aria-describedby="veda-soon"
              onClick={() => setToast("VEDA, your guide to your own chart, arrives in Phase 2. You will be able to ask about any card.")}>
              <span aria-hidden="true">☾</span>Talk to VEDA<span className="soonbadge">Coming soon</span>
            </button>
            <span id="veda-soon" className="sr">Chat with VEDA arrives in Phase 2.</span>
          </nav>
        </section>

        <ChartsSection m={m} profileId={profile.profile_id} tab={tab} setTab={setTab} selected={selected} setSelected={setSelected}
          onExpired={refresh} onAddTime={() => { if (draft) store.setDraft({ ...draft, timeUnknown: false }); navigate("/details"); }} />

        {GROUPS.map((g) => (
          <section key={g.id} id={g.id} aria-labelledby={`${g.id}-h`} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
              <svg width="92" height="28" viewBox="0 0 92 28" aria-hidden="true"><polyline points="4,20 26,8 50,18 70,6 88,14" fill="none" stroke={g.accent} strokeOpacity=".6" /><circle cx="4" cy="20" r="2.5" fill={g.accent} /><circle cx="26" cy="8" r="3" fill={g.accent} className="tw" /><circle cx="50" cy="18" r="2.5" fill={g.accent} /><circle cx="70" cy="6" r="2" fill={g.accent} /><circle cx="88" cy="14" r="2.5" fill={g.accent} /></svg>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><div className="eyebrow" style={{ color: g.accent }}>Constellation {g.numeral}</div><h2 className="h2g" id={`${g.id}-h`}>{g.title}</h2></div>
              <p style={{ margin: 0, fontSize: 15, color: "var(--muted)", flexBasis: "100%", maxWidth: 640 }}>{g.blurb}</p>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 20 }}>
              {g.cards.map(({ id, label }) => {
                const c = cards[id], st = status[id] ?? "streaming";
                return (
                  <article key={id} className={`card ${flipping === id ? "flip" : ""}`} id={`card-${id}`} aria-labelledby={`t-${id}`} style={{ boxShadow: `inset 0 3px 0 ${g.accent}` }}>
                    {flipping === id && sparks.map((p, i) => <span key={i} className="spark" style={{ left: `${p.x}%`, top: `${p.y}%`, ["--dx" as string]: `${p.dx}px`, ["--dy" as string]: `${p.dy}px`, animationDelay: `${p.d}s` }} />)}
                    {st === "streaming" && (<>
                      <div className="vis" aria-hidden="true"><span className="tw" style={{ width: 8, height: 8, borderRadius: "50%", background: g.accent }} /></div>
                      <div className="eyebrow" style={{ color: g.accent }}>{label}</div>
                      <div style={{ fontSize: 15, color: "var(--text2)" }}>Reading this part of your sky…</div>
                      <div className="skel" style={{ width: "90%" }} /><div className="skel" style={{ width: "70%" }} />
                    </>)}
                    {st === "error" && (<>
                      <div className="eyebrow" style={{ color: g.accent }}>{label}</div>
                      <h3 className="ttl" id={`t-${id}`}>This card did not load</h3>
                      <p className="sum" role="alert">Something went wrong while reading this card. The rest of your map is fine.</p>
                      <div><button type="button" className="btn btn-ghost btn-sm" onClick={() => retry(id)}>Try this card again</button></div>
                    </>)}
                    {st === "unavailable" && c && (<>
                      <div className="eyebrow" style={{ color: g.accent }}>{label}</div>
                      <h3 className="ttl" id={`t-${id}`}>This card needs your birth time</h3>
                      <p className="sum">{c.summary}</p>
                      <div><button type="button" className="btn btn-ghost btn-sm" onClick={() => { if (draft) store.setDraft({ ...draft, timeUnknown: false }); navigate("/details"); }}>Add a birth time</button></div>
                    </>)}
                    {st === "ready" && c && (<>
                      <div className="vis"><CardVisual id={id} m={m} name={name} /></div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                        <div className="eyebrow" style={{ color: g.accent }}>{label}</div>
                        <span className={`badge ${c.badge === "ai" ? "b-ai" : "b-cur"}`}>{c.badge === "ai" ? "AI-phrased" : "Curated"}</span>
                      </div>
                      <h3 className="ttl" id={`t-${id}`}>{withName(c.headline, name, (used[id] = { done: false }))}</h3>
                      <p className="sum">{withName(c.summary, name, used[id])}</p>
                      {c.degraded && <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: "var(--lav)" }}>Showing our reviewed library text right now.</p>}
                      {c.fact_ids.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }} aria-label="Chart facts this card uses">
                        {c.fact_ids.filter((f) => m.facts[f]).slice(0, 3).map((f) => <button key={f} type="button" className="chipbtn" onClick={() => onChip(f)}>{m.facts[f].label}</button>)}
                      </div>}
                      <div style={{ marginTop: "auto" }}><button type="button" className="more" id={`more-${id}`} onClick={() => openCard(id)}>Read the full reading <span aria-hidden="true">✦</span></button></div>
                    </>)}
                  </article>
                );
              })}
            </div>
          </section>
        ))}

        <footer style={{ borderTop: "1px solid rgba(255,255,255,.12)", paddingTop: 24, display: "flex", flexDirection: "column", gap: 12 }}>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.65, color: "var(--muted)", maxWidth: 820 }}>Pranix offers reflections from traditional Vedic astrology and Ayurvedic ideas. It does not predict events and is not medical, financial or legal advice. Colours and days are traditional associations, not guarantees.</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 20 }}><Link to="/how" className="lnk">How we calculate</Link><a className="lnk" href="https://github.com/iamrajharshit/Pranix" rel="noopener">Source code (AGPL-3.0)</a><Link to="/legal" className="lnk">Terms and Privacy</Link></div>
          <p style={{ margin: 0, fontSize: 13, color: "var(--faint)" }}>Lahiri ayanamsa · whole-sign houses · mean node · 365.25-day Dasha year · {m.meta.ruleset.id}@{m.meta.ruleset.version}</p>
        </footer>
      </main>
      </div>

      {reading && <Reading card={reading} m={m} profileId={profile.profile_id} name={name} readyIds={readyIds} onClose={closeCard} onOpen={openCard} onChip={onChip} />}

      {confirmStart && (
        <div className="overlay">
          <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="so-t">
            <h2 id="so-t" style={{ margin: 0, font: "600 28px var(--serif)", color: "#fff" }}>Start over?</h2>
            <p style={{ margin: 0, fontSize: 16, lineHeight: 1.6, color: "var(--text2)" }}>This chart will be cleared from this page. Your details stay filled in on the form, so you can change anything and try again.</p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button type="button" className="btn btn-gold" autoFocus onClick={() => { api.deleteProfile(profile.profile_id).catch(() => {}); store.setProfileId(null); onProfile(null); navigate("/details"); }}>Yes, start over</button>
              <button type="button" className="btn btn-ghost" onClick={() => setConfirmStart(false)}>Keep my map</button>
            </div>
          </div>
        </div>
      )}
      {toast && <Toast text={toast} onDone={() => setToast("")} />}
    </div>
  );
}
