// SPDX-License-Identifier: AGPL-3.0-only
// Cosmic loader (FR-UI-16, board 7): six stages echoing the person's own details; ready about
// three seconds after the chart arrives; "Skip to my dashboard" always available.
import { useEffect, useState } from "react";
import type { Draft } from "../lib/storage";

const STEP = 420;
const SIGN_GLYPHS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function Loader({ draft, done, onFinish }: { draft: Draft; done: boolean; onFinish(): void }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep((s) => Math.min(6, s + 1)), STEP);
    return () => clearInterval(t);
  }, []);
  const ready = done && step >= 6;
  useEffect(() => { if (ready) { const t = setTimeout(onFinish, 700); return () => clearTimeout(t); } }, [ready, onFinish]);

  const unknown = draft.timeUnknown;
  const place = draft.manual ? `${draft.lat}, ${draft.lon}` : draft.place ? `${draft.place.name}${draft.place.where ? `, ${draft.place.where.split(" · ")[0]}` : ""}` : "";
  const date = `${+draft.dd} ${MONTHS[+draft.mm - 1]} ${draft.yy}`;
  const time = unknown ? "time unknown" : `${+draft.hh}:${draft.mi.padStart(2, "0")} ${draft.ap.toLowerCase()}`;
  const stages: [string, string][] = [
    ["Locating your birthplace", place + (draft.place?.tz ? ` · time zone ${draft.place.tz}` : "")],
    ["Reading the clock of the sky", unknown ? "Birth time unknown, so we check the whole birth day" : `Converting ${time} local time to universal time`],
    ["Placing the planets", "Nine planets on the sidereal zodiac (Lahiri)"],
    ["Casting your charts", unknown ? "Signs and stars that held all day; charts need a birth time" : "Your D1 birth chart and D9 navamsa"],
    ["Unfolding your timeline", unknown ? "Checking whether your life periods depend on the hour" : "Vimshottari Dasha from the Moon at your birth"],
    ["Weaving insights", "Twelve cards start arriving on your dashboard"],
  ];
  return (
    <div style={{ minHeight: "100vh", background: "radial-gradient(900px 600px at 50% 30%,rgba(139,124,246,.22),transparent 60%),#0A0A1E" }}>
      <div className="wrap topbar"><span className="brand">Pranix</span>{done && <button type="button" className="lnk" onClick={onFinish}>Skip to my dashboard</button>}</div>
      <main className="wrap" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 40, alignItems: "center", paddingBottom: 72 }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
          <svg width="100%" style={{ maxWidth: 400 }} viewBox="0 0 400 400" role="img" aria-label="A turning zodiac wheel">
            <g className="wheel">
              <circle cx="200" cy="200" r="170" fill="none" stroke="#F4C566" strokeOpacity=".5" />
              <circle cx="200" cy="200" r="140" fill="none" stroke="#F4C566" strokeOpacity=".25" />
              {SIGN_GLYPHS.map((g, i) => (
                <g key={g}><line x1="200" y1="30" x2="200" y2="60" stroke="#F4C566" strokeOpacity=".55" transform={`rotate(${i * 30} 200 200)`} />
                  <text x="200" y="52" textAnchor="middle" fontSize="15" fill="#F4C566" transform={`rotate(${i * 30 + 15} 200 200)`}>{g}</text></g>
              ))}
            </g>
            <g className="wheel" style={{ animationDuration: "6s" }}><circle cx="200" cy="95" r="5" fill="#FFE3A3" /></g>
            <g className="wheel" style={{ animationDuration: "9s", animationDirection: "reverse" }}><circle cx="305" cy="200" r="4" fill="#C9C0FF" /></g>
            <circle className="pulse" cx="200" cy="200" r="58" fill="#14143A" stroke="#F4C566" strokeOpacity=".7" />
            <text x="200" y="196" textAnchor="middle" fontFamily="Cormorant Garamond,serif" fontSize="20" fill="#FFF">{date}</text>
            <text x="200" y="218" textAnchor="middle" fontFamily="Inter" fontSize="12" fill="#D5D0EE">{time}</text>
          </svg>
          <p className="hint" style={{ fontSize: 14, textAlign: "center" }}>{place}</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }} aria-live="polite">
          <div className="eyebrow" style={{ color: "var(--gold)" }}>Casting your chart</div>
          <h1 style={{ margin: 0, font: "500 clamp(34px,5vw,48px)/1.08 var(--serif)", color: "#fff" }}>{unknown ? "Reading the sky of your birth day" : "Reading the sky you were born under"}</h1>
          <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 14 }}>
            {stages.map(([n, d], i) => {
              const on = i < step;
              return (
                <li key={n} style={{ display: "flex", gap: 14, alignItems: "flex-start", opacity: on ? 1 : 0.35, transition: "opacity .4s" }}>
                  <span aria-hidden="true" style={{ flex: "none", width: 28, height: 28, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", font: "600 13px var(--sans)", color: "#1A1226",
                    border: `1.5px solid ${on ? "#F4C566" : "rgba(255,255,255,.35)"}`, background: on ? "#F4C566" : "transparent", boxShadow: on ? "0 0 14px rgba(244,197,102,.8)" : "none" }}>✓</span>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}><strong style={{ fontSize: 16, color: "#fff" }}>{n}</strong><span style={{ fontSize: 14, lineHeight: 1.5, color: "var(--muted)" }}>{d}</span></div>
                </li>
              );
            })}
          </ol>
          {ready && <div style={{ borderTop: "1px solid rgba(255,255,255,.12)", paddingTop: 18 }}><strong style={{ font: "600 24px var(--serif)", color: "#fff" }}>Your sky is ready.</strong></div>}
        </div>
      </main>
    </div>
  );
}
