// SPDX-License-Identifier: AGPL-3.0-only
// Board 1: intro and entry, with the 18+ age gate before every entry button (FR-UI-11).
import { useState } from "react";
import { ErrIcon, Link, SiteFooter, TopBar } from "../components/Shell";
import { navigate } from "../lib/router";
import { store } from "../lib/storage";

const SPOKES = Array.from({ length: 12 }, (_, i) => {
  const a = (i * Math.PI) / 6, c = Math.cos(a), s = Math.sin(a);
  return [300 + 270 * c, 300 + 270 * s, 300 + 190 * c, 300 + 190 * s];
});

function Wheel() {
  return (
    <svg viewBox="0 0 600 600" width="100%" style={{ maxWidth: 560, height: "auto" }} aria-hidden="true">
      <circle cx="300" cy="300" r="290" fill="none" stroke="#8B7CF6" strokeOpacity=".25" />
      <circle cx="300" cy="300" r="120" fill="#F4C566" fillOpacity=".08" />
      <circle cx="300" cy="300" r="46" fill="#F4C566" />
      <circle cx="300" cy="300" r="62" fill="none" stroke="#F4C566" strokeOpacity=".4" />
      <g className="wheel" style={{ animationDuration: "240s" }}>
        <circle cx="300" cy="300" r="270" fill="none" stroke="#F4C566" strokeOpacity=".7" />
        <circle cx="300" cy="300" r="190" fill="none" stroke="#F4C566" strokeOpacity=".5" />
        <circle cx="300" cy="300" r="230" fill="none" stroke="#EEEAFB" strokeOpacity=".7" strokeWidth="5" strokeDasharray="2 46.87" />
        <g stroke="#F4C566" strokeOpacity=".5">{SPOKES.map((l, i) => <line key={i} x1={l[0]} y1={l[1]} x2={l[2]} y2={l[3]} />)}</g>
      </g>
      <g className="wheel" style={{ animationDuration: "40s" }}><circle cx="300" cy="300" r="150" fill="none" stroke="#8B7CF6" strokeOpacity=".4" /><circle cx="450" cy="300" r="9" fill="#8B7CF6" /><circle cx="150" cy="300" r="6" fill="#EEEAFB" /></g>
      <g className="wheel" style={{ animationDuration: "70s", animationDirection: "reverse" }}><circle cx="300" cy="300" r="170" fill="none" stroke="#8B7CF6" strokeOpacity=".25" /><circle cx="300" cy="130" r="7" fill="#F4C566" /></g>
      <g fill="#EEEAFB">{[[40, 80], [90, 520], [560, 70], [580, 460], [20, 330], [320, 14], [250, 590], [520, 560]].map(([x, y], i) => <circle key={i} className="tw" cx={x} cy={y} r="1.8" style={{ animationDelay: `${i * 0.6}s` }} />)}</g>
    </svg>
  );
}

const VALUES: [string, string, string][] = [
  ["Exact, not guessed", "Positions come from the Swiss Ephemeris, an astronomical engine. An AI only helps explain the result. It never does the maths.", "M20 2v8M20 30v8M2 20h8M30 20h8"],
  ["Reflection, not prediction", "You will read about tendencies and strengths to grow, never fear, doom or dates. This is not medical, legal or financial advice.", "M20 12v12M14 18h12"],
  ["Private by design", "As a guest, nothing about you is saved on our servers. Your name never leaves your browser and nothing personal is ever sent to an AI.", "M14 17v-4a6 6 0 0 1 12 0v4"],
];

export default function Entry() {
  const [ageOk, setAgeOk] = useState(store.ageOk());
  const [nudge, setNudge] = useState(false);
  const toggle = (v: boolean) => { store.setAge(v); setAgeOk(v); setNudge(false); };
  const needAge = () => { setNudge(true); document.getElementById("agegate")?.scrollIntoView({ block: "center" }); };

  return (
    <div style={{ overflow: "hidden" }}>
      <TopBar right={<nav style={{ display: "flex", gap: 28, fontSize: 15 }}><a href="#vision" style={{ color: "var(--muted)", textDecoration: "none" }}>Our vision</a><a href="#begin" style={{ color: "var(--muted)", textDecoration: "none" }}>Begin</a><Link to="/how" style={{ color: "var(--muted)", textDecoration: "none" }}>How we calculate</Link></nav>} />
      <section className="wrap" style={{ display: "flex", flexWrap: "wrap", gap: 48, alignItems: "center", minHeight: 600, paddingBottom: 96 }}>
        <div style={{ flex: "1 1 460px", minWidth: 0, display: "flex", flexDirection: "column", gap: 28 }}>
          <div className="eyebrow" style={{ color: "var(--muted)", fontWeight: 400, letterSpacing: ".22em" }}>Vedic birth chart · plain language</div>
          <h1 className="h1xl">Read the sky you were born under.</h1>
          <p className="lead" style={{ fontSize: 19, maxWidth: 540 }}>We calculate your Vedic chart from exact astronomy, then explain it as reflection, never prediction. Calm, private, and written in words you can actually use.</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}><a className="btn btn-gold" href="#begin">Begin your reading</a><a className="btn btn-ghost" href="#vision">Why we built this</a></div>
        </div>
        <div style={{ flex: "1 1 440px", minWidth: 0, display: "flex", justifyContent: "center" }}><Wheel /></div>
      </section>

      <section id="vision" style={{ background: "#10102B", borderTop: "1px solid rgba(255,255,255,.08)", borderBottom: "1px solid rgba(255,255,255,.08)" }}>
        <div className="wrap" style={{ padding: "96px 32px", display: "flex", flexDirection: "column", gap: 56 }}>
          <div style={{ maxWidth: 720, display: "flex", flexDirection: "column", gap: 20 }}>
            <div className="eyebrow" style={{ color: "var(--gold)" }}>Our vision</div>
            <h2 className="h2xl">Ancient maps, honest tools.</h2>
            <p className="lead" style={{ fontSize: 18 }}>Vedic astrology is a rich way to reflect on who you are. We want to give it a modern home: precise where maths is involved, gentle where words are involved, and clear about which is which.</p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 24 }}>
            {VALUES.map(([t, p, d]) => (
              <div key={t} style={{ background: "var(--panel)", border: "1px solid rgba(244,197,102,.25)", borderRadius: 20, padding: 32, display: "flex", flexDirection: "column", gap: 14 }}>
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none" stroke="#F4C566" strokeWidth="1.5" aria-hidden="true"><circle cx="20" cy="20" r="16" /><path d={d} /></svg>
                <h3 style={{ margin: 0, font: "600 28px var(--serif)", color: "#fff" }}>{t}</h3>
                <p style={{ margin: 0, fontSize: 16, lineHeight: 1.65, color: "var(--text2)" }}>{p}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="begin" className="wrap" style={{ padding: "112px 32px", display: "flex", flexDirection: "column", gap: 48, alignItems: "center", textAlign: "center" }}>
        <div style={{ maxWidth: 640, display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="eyebrow" style={{ color: "var(--gold)" }}>Begin</div>
          <h2 className="h2xl">How would you like to enter?</h2>
          <p className="lead">Try it as a guest in under a minute. Accounts for keeping profiles are coming soon.</p>
        </div>
        <div id="agegate" className={`gate ${nudge && !ageOk ? "nudge" : ""}`} style={{ width: "100%", maxWidth: 760, padding: "20px 24px", textAlign: "left", display: "flex", flexDirection: "column", gap: 10 }}>
          <label style={{ display: "flex", gap: 14, alignItems: "flex-start", fontSize: 16, lineHeight: 1.55, cursor: "pointer" }}>
            <input type="checkbox" checked={ageOk} onChange={(e) => toggle(e.target.checked)} aria-describedby="agehelp" style={{ width: 24, height: 24, marginTop: 2, accentColor: "#F4C566", flex: "none" }} />
            <span><strong>Step 1.</strong> I am 18 or older and agree to the <Link to="/legal?tab=terms">Terms</Link> and <Link to="/legal">Privacy notice</Link>.</span>
          </label>
          {nudge && !ageOk && <div className="err" id="agehelp" role="alert"><ErrIcon size={18} />Please tick this box first. Pranix is for adults only.</div>}
          {ageOk && <div id="agehelp" className="hint" style={{ fontSize: 14 }}>Thank you. Now choose how to enter.</div>}
        </div>
        <div style={{ width: "100%", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 24, textAlign: "left" }}>
          <div style={{ background: "linear-gradient(160deg,#241B52,#16163A)", border: "1px solid var(--gold)", borderRadius: 20, padding: 32, display: "flex", flexDirection: "column", gap: 16 }}>
            <h3 style={{ margin: 0, font: "600 30px var(--serif)", color: "#fff" }}>Continue as guest</h3>
            <p style={{ margin: 0, fontSize: 16, lineHeight: 1.6, color: "var(--text2)", flex: 1 }}>No account. Nothing is stored on our servers, and your chart disappears when you leave.</p>
            {ageOk ? <button type="button" className="btn btn-gold" onClick={() => navigate("/details")}>Start as guest</button>
              : <button type="button" className="btn btn-off" aria-disabled="true" onClick={needAge}>Start as guest</button>}
          </div>
          <div style={{ background: "#12122E", border: "1px dashed rgba(255,255,255,.25)", borderRadius: 20, padding: 32, display: "flex", flexDirection: "column", gap: 16 }}>
            <h3 style={{ margin: 0, font: "600 30px var(--serif)", color: "#C9C4E6" }}>Continue with Google</h3>
            <p style={{ margin: 0, fontSize: 16, lineHeight: 1.6, color: "var(--muted)", flex: 1 }}>Keep up to five profiles for yourself and family. Coming soon.</p>
            <span className="btn" style={{ border: "1px solid rgba(255,255,255,.25)", color: "var(--muted)" }} role="button" aria-disabled="true">Coming soon</span>
          </div>
          <div style={{ background: "#12122E", border: "1px dashed rgba(255,255,255,.25)", borderRadius: 20, padding: 32, display: "flex", flexDirection: "column", gap: 16 }}>
            <h3 style={{ margin: 0, font: "600 30px var(--serif)", color: "#C9C4E6" }}>Sign in with a passkey</h3>
            <p style={{ margin: 0, fontSize: 16, lineHeight: 1.6, color: "var(--muted)", flex: 1 }}>Use your fingerprint or face, no email needed. Coming soon.</p>
            <span className="btn" style={{ border: "1px solid rgba(255,255,255,.25)", color: "var(--muted)" }} role="button" aria-disabled="true">Coming soon</span>
          </div>
        </div>
      </section>
      <SiteFooter />
    </div>
  );
}
