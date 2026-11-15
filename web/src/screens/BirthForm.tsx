// SPDX-License-Identifier: AGPL-3.0-only
// Board 2: guest birth form (FR-UI-12) and the whole submit flow: loader, server errors mapped back
// to fields, the DST dialog, the busy banner, and the waking time-wheel for a sleeping server.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Problem, Profile } from "../api/types";
import PlaceField from "../components/PlaceField";
import { ErrIcon, Link, TopBar } from "../components/Shell";
import { navigate } from "../lib/router";
import { emptyDraft, store, type Draft } from "../lib/storage";
import { toRequest, validate, type FormErrors } from "../lib/validate";
import Loader from "./Loader";
import { Resting, TimeWheel } from "./Oracle";

type Phase = "form" | "loading" | "waking" | "resting";
const WAKE_SECONDS = 60;
const FIELD_OF: Record<string, keyof FormErrors> = {
  OUT_OF_RANGE: "dob", UNDER_AGE_PROFILE: "dob", NONEXISTENT_LOCAL_TIME: "time", INVALID_PLACE: "place",
};

function field(label: string, id: string, value: string, set: (v: string) => void, max: number, bad: boolean, placeholder: string, disabled = false) {
  return (
    <div style={{ flex: id === "yy" ? 1.4 : 1, display: "flex", flexDirection: "column", gap: 6 }}>
      <label className="hint" htmlFor={id}>{label}</label>
      <input className={`f ${bad ? "bad" : ""}`} id={id} inputMode="numeric" maxLength={max} placeholder={placeholder} value={value} disabled={disabled}
        aria-invalid={bad} onChange={(e) => set(e.target.value.replace(/[^0-9]/g, "").slice(0, max))} />
    </div>
  );
}

export default function BirthForm({ onReady }: { onReady(p: Profile, d: Draft): void }) {
  const [d, setD] = useState<Draft>(() => store.draft() ?? emptyDraft);
  const [submitted, setSubmitted] = useState(false);
  const [server, setServer] = useState<FormErrors>({});
  const [phase, setPhase] = useState<Phase>("form");
  const [busy, setBusy] = useState<number | null>(null);
  const [dst, setDst] = useState<Problem["options"] | null>(null);
  const [ageOk, setAgeOk] = useState(store.ageOk());
  const [problem, setProblem] = useState<Problem | null>(null);
  const [result, setResult] = useState<Profile | null>(null);
  const summary = useRef<HTMLDivElement>(null);

  const set = (p: Partial<Draft>) => { setD((s) => { const n = { ...s, ...p }; store.setDraft(n); return n; }); setServer({}); };
  const errs = { ...validate(d), ...server };
  const shown: FormErrors = submitted ? errs : {};
  const list = (Object.entries(shown) as [keyof FormErrors, string][]).filter(([, v]) => v);

  const submit = useCallback(async (draft: Draft) => {
    setPhase("loading"); setResult(null); setProblem(null);
    try {
      const p = await api.createProfile(toRequest(draft));
      setResult(p);
    } catch (e) {
      const err = e as ApiError;
      const code = err.code;
      if (err.status === 412) { store.setAge(false); setAgeOk(false); setPhase("form"); return; }
      if (code === "AMBIGUOUS_LOCAL_TIME") { setDst(err.problem?.options ?? []); setPhase("form"); return; }
      if (FIELD_OF[code]) { setServer({ [FIELD_OF[code]]: err.problem?.message ?? "Please check this." }); setPhase("form"); return; }
      if (err.status === 429) { setBusy(err.problem?.retry_after ?? 20); setPhase("form"); return; }
      if (err.status === 0 || err.status === 503) { setPhase("waking"); return; }
      setProblem(err.problem); setPhase("resting");
    }
  }, []);

  // A sleeping free server (HOST-05): poll /healthz, then send the same details again by itself.
  useEffect(() => {
    if (phase !== "waking") return;
    let stop = false;
    const tick = async () => {
      while (!stop) {
        try { await api.healthz(); if (!stop) submit(d); return; } catch { await new Promise((r) => setTimeout(r, 5000)); }
      }
    };
    tick();
    return () => { stop = true; };
  }, [phase, d, submit]);

  useEffect(() => { if (busy === null) return; const t = setTimeout(() => setBusy(null), busy * 1000); return () => clearTimeout(t); }, [busy]);
  useEffect(() => { if (submitted && list.length) summary.current?.focus(); }, [submitted]); // eslint-disable-line react-hooks/exhaustive-deps

  const reveal = () => {
    setSubmitted(true);
    if (!ageOk) return;
    if (Object.keys(validate(d)).length === 0 && busy === null) submit(d);
  };

  if (phase === "loading" || (phase === "form" && result)) {
    return <Loader draft={d} done={!!result} onFinish={() => { if (result) { onReady(result, d); navigate("/dashboard"); } }} />;
  }
  if (phase === "waking") {
    return (
      <div><TopBar />
        <TimeWheel seconds={WAKE_SECONDS} title="The oracle is waking up">
          <p className="lead" style={{ maxWidth: 560 }}>Pranix runs on a free server that sleeps when nobody is using it. Waking usually takes about a minute. Your details are kept, and your chart will continue on its own.</p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "center" }}>
            <button type="button" className="btn btn-ghost" onClick={() => submit(d)}>Try again now</button>
            <button type="button" className="lnk" onClick={() => setPhase("form")}>Edit my details</button>
          </div>
        </TimeWheel>
      </div>
    );
  }
  if (phase === "resting") {
    return <div><TopBar /><Resting onRetry={() => submit(d)} requestId={problem?.request_id} /></div>;
  }

  const unknown = d.timeUnknown;
  return (
    <div style={{ position: "relative" }}>
      <TopBar right={<Link to="/" style={{ fontSize: 15, color: "var(--text2)" }}>Back to start</Link>} />
      <main className="wrap" style={{ display: "flex", flexWrap: "wrap", gap: 48, alignItems: "flex-start", paddingBottom: 96 }}>
        <section style={{ flex: "1 1 560px", minWidth: 0, display: "flex", flexDirection: "column", gap: 32 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="eyebrow" style={{ color: "var(--gold)" }}>Your birth details</div>
            <h1 className="h1m">Tell us when and where you arrived.</h1>
            <p className="lead" style={{ maxWidth: 560 }}>The more exact the birth time, the more precise the chart. Everything here is used only to calculate the sky.</p>
          </div>

          {!ageOk && (
            <div role="alert" style={{ background: "#241B52", border: "2px solid var(--gold)", borderRadius: 16, padding: "20px 24px", display: "flex", flexDirection: "column", gap: 12 }}>
              <strong style={{ fontSize: 17 }}>One quick step first</strong>
              <span style={{ fontSize: 15, lineHeight: 1.55, color: "var(--text2)" }}>Please confirm your age to continue.</span>
              <label style={{ display: "flex", gap: 14, alignItems: "flex-start", fontSize: 16, lineHeight: 1.55, cursor: "pointer" }}>
                <input type="checkbox" checked={ageOk} onChange={(e) => { store.setAge(e.target.checked); setAgeOk(e.target.checked); }} style={{ width: 24, height: 24, accentColor: "#F4C566", flex: "none", marginTop: 2 }} />
                <span>I am 18 or older and agree to the <Link to="/legal?tab=terms">Terms</Link> and <Link to="/legal">Privacy notice</Link>.</span>
              </label>
            </div>
          )}

          {busy !== null && (
            <div role="alert" className="err" style={{ background: "#2A1B3A", border: "1px solid #FF9D9D", borderRadius: 16, padding: "16px 20px" }}>
              <ErrIcon size={20} /><span>Many people are asking at once. Please wait about {busy} seconds and press Reveal again. Nothing you typed is lost.</span>
            </div>
          )}

          {list.length > 0 && (
            <div ref={summary} role="alert" tabIndex={-1} style={{ background: "#2A1B3A", border: "2px solid #FF9D9D", borderRadius: 16, padding: "20px 24px", display: "flex", flexDirection: "column", gap: 10 }}>
              <strong style={{ fontSize: 17 }}>{list.length === 1 ? "One thing to check before we calculate:" : `${list.length} things to check before we calculate:`}</strong>
              <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6, fontSize: 15, lineHeight: 1.5 }}>
                {list.map(([k, v]) => <li key={k}><a href={`#${k === "dob" ? "dd" : k === "time" ? "hh" : k === "place" ? (d.manual ? "lat" : "place") : "name"}`} style={{ color: "var(--err)" }}>{v}</a></li>)}
              </ul>
            </div>
          )}

          <form className="panel" style={{ display: "flex", flexDirection: "column", gap: 28 }} noValidate onSubmit={(e) => { e.preventDefault(); reveal(); }}>
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: "var(--muted)" }}>As a guest you can read your own chart. Keeping charts for family or friends will need an account, coming soon.</p>

            <div style={{ display: "flex", flexWrap: "wrap", gap: 20 }}>
              <div style={{ flex: "1 1 240px", display: "flex", flexDirection: "column", gap: 8 }}>
                <label className="lbl" htmlFor="name">What should we call you? <span style={{ color: "var(--muted)" }}>(optional)</span></label>
                <input className={`f ${shown.name ? "bad" : ""}`} id="name" type="text" maxLength={40} placeholder="Your name or nickname" autoComplete="off" value={d.name}
                  aria-invalid={!!shown.name} onChange={(e) => set({ name: e.target.value.slice(0, 40) })} />
                <span className="hint">Stays in your browser and personalises the reading. Never sent to our server or an AI.</span>
                {shown.name && <div className="err" role="alert"><ErrIcon /><span>{shown.name}</span></div>}
              </div>
              <div style={{ flex: "1 1 240px", display: "flex", flexDirection: "column", gap: 8 }}>
                <label className="lbl" htmlFor="pronouns">Pronouns <span style={{ color: "var(--muted)" }}>(optional)</span></label>
                <select className="f" id="pronouns" value={d.pronouns} onChange={(e) => set({ pronouns: e.target.value as Draft["pronouns"] })}>
                  <option value="none">Prefer not to say</option><option value="she_her">she / her</option><option value="he_him">he / him</option><option value="they_them">they / them</option>
                </select>
                <span className="hint">Only used for wording on screen. It does not change the chart.</span>
              </div>
            </div>

            <fieldset style={{ border: 0, margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
              <legend className="lbl" style={{ padding: 0, marginBottom: 8 }}>Date of birth</legend>
              <div style={{ display: "flex", gap: 12 }}>
                {field("Day", "dd", d.dd, (v) => set({ dd: v }), 2, !!shown.dob, "DD")}
                {field("Month", "mm", d.mm, (v) => set({ mm: v }), 2, !!shown.dob, "MM")}
                {field("Year", "yy", d.yy, (v) => set({ yy: v }), 4, !!shown.dob, "YYYY")}
              </div>
              <span className="hint">Charts are made for people aged 18 or over.</span>
              {shown.dob && <div className="err" role="alert"><ErrIcon /><span>{shown.dob}</span></div>}
            </fieldset>

            <fieldset style={{ border: 0, margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
              <legend className="lbl" style={{ padding: 0, marginBottom: 8 }}>Time of birth</legend>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, opacity: unknown ? 0.45 : 1 }}>
                <div style={{ display: "flex", gap: 12 }}>
                  {field("Hour", "hh", d.hh, (v) => set({ hh: v }), 2, !unknown && !!shown.time, "HH", unknown)}
                  {field("Minute", "mi", d.mi, (v) => set({ mi: v }), 2, !unknown && !!shown.time, "MM", unknown)}
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}><label className="hint" htmlFor="ap">AM / PM</label>
                    <select className="f" id="ap" value={d.ap} disabled={unknown} onChange={(e) => set({ ap: e.target.value as Draft["ap"] })}><option value="AM">AM</option><option value="PM">PM</option></select></div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}><label className="hint" htmlFor="acc">How sure are you of the time?</label>
                  <select className="f" id="acc" value={d.acc} disabled={unknown} onChange={(e) => set({ acc: e.target.value as Draft["acc"] })}>
                    <option value="exact">Exact, from a certificate</option><option value="approx_5m">Within 5 minutes</option><option value="approx_30m">Within 30 minutes</option><option value="approx_1h">Within an hour</option>
                  </select></div>
              </div>
              {!unknown && shown.time && <div className="err" role="alert"><ErrIcon /><span>{shown.time}</span></div>}
              <label style={{ display: "flex", gap: 12, alignItems: "flex-start", fontSize: 15, lineHeight: 1.5, color: "var(--text2)", cursor: "pointer", marginTop: 4, minHeight: 44 }}>
                <input type="checkbox" checked={unknown} onChange={(e) => set({ timeUnknown: e.target.checked, disambiguation: undefined })} style={{ width: 24, height: 24, accentColor: "#F4C566", flex: "none", marginTop: 1 }} />
                <span>I do not know the birth time.</span>
              </label>
              {unknown && <div style={{ background: "#10102B", border: "1px solid rgba(244,197,102,.35)", borderRadius: 12, padding: "14px 16px", fontSize: 14, lineHeight: 1.55, color: "var(--text2)" }}>That is fine. We only show what stays true for the whole of your birth day: no rising sign, houses or charts, and cards that need a birth time say so. If you find the time later, you can add it.</div>}
            </fieldset>

            <PlaceField draft={d} error={shown.place} set={set} />

            <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center", justifyContent: "space-between", paddingTop: 8, borderTop: "1px solid rgba(255,255,255,.12)" }}>
              <span className="hint" style={{ maxWidth: 340 }}>If the birth time falls in a daylight-saving change, we will ask which one you mean.</span>
              <button type="submit" className="btn btn-gold" aria-disabled={busy !== null}>Reveal my chart</button>
            </div>
          </form>
        </section>

        <aside style={{ flex: "1 1 320px", minWidth: 0, display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ background: "#10102B", border: "1px solid rgba(244,197,102,.25)", borderRadius: 20, padding: 28, display: "flex", flexDirection: "column", gap: 18 }}>
            <h2 style={{ margin: 0, font: "600 28px var(--serif)", color: "#fff" }}>What happens next</h2>
            <ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 8, fontSize: 15, lineHeight: 1.5, color: "var(--text2)" }}>
              <li>Locating the birthplace</li><li>Reading the clock of the sky</li><li>Placing the planets</li><li>Casting the charts</li><li>Unfolding the timeline</li><li>Weaving the insights</li>
            </ol>
            <p className="hint" style={{ margin: 0 }}>Takes a few seconds. You can skip the animation.</p>
          </div>
          <div style={{ background: "#10102B", border: "1px solid rgba(255,255,255,.14)", borderRadius: 20, padding: 28, display: "flex", flexDirection: "column", gap: 12 }}>
            <h2 style={{ margin: 0, font: "600 24px var(--serif)", color: "#fff" }}>Privacy</h2>
            <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 8, fontSize: 15, lineHeight: 1.5, color: "var(--text2)" }}>
              <li>As a guest, your details are not stored on our servers.</li>
              <li>Your name and pronouns stay in your browser.</li>
              <li>No name, pronouns, date, time or place is ever sent to an AI provider.</li>
            </ul>
          </div>
        </aside>
      </main>

      {dst && (
        <div className="overlay">
          <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dst-t">
            <h2 id="dst-t" style={{ margin: 0, font: "600 30px var(--serif)", color: "#fff" }}>That time happened twice</h2>
            <p style={{ margin: 0, fontSize: 16, lineHeight: 1.6, color: "var(--text2)" }}>The clocks went back that night, so {+d.hh}:{d.mi.padStart(2, "0")} {d.ap} came round two times. Which one was yours?</p>
            <button type="button" className="btn btn-gold" autoFocus onClick={() => { const n = { ...d, disambiguation: "earlier" as const }; setDst(null); set(n); submit(n); }}>The first one, before the clocks went back</button>
            <button type="button" className="btn btn-ghost" onClick={() => { const n = { ...d, disambiguation: "later" as const }; setDst(null); set(n); submit(n); }}>The second one, after the clocks went back</button>
            <button type="button" className="lnk" style={{ color: "var(--gold)" }} onClick={() => { const n = { ...d, timeUnknown: true, disambiguation: undefined }; setDst(null); set(n); submit(n); }}>I am not sure. Treat my birth time as unknown.</button>
            <button type="button" className="lnk" onClick={() => setDst(null)}>Go back and edit my details</button>
          </div>
        </div>
      )}
    </div>
  );
}
