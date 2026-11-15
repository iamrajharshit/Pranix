// SPDX-License-Identifier: AGPL-3.0-only
// Recovery screens (§14, §14.1, board 8): time-wheel with the crystal ball, and "the oracle is resting".
import { useEffect, useState, type ReactNode } from "react";

export function TimeWheel({ seconds, title, children, label }: { seconds: number | null; title: string; label?: string; children?: ReactNode }) {
  const [left, setLeft] = useState(seconds ?? 0);
  useEffect(() => { setLeft(seconds ?? 0); }, [seconds]);
  useEffect(() => {
    if (seconds === null) return;
    const t = setInterval(() => setLeft((l) => Math.max(0, l - 1)), 1000);
    return () => clearInterval(t);
  }, [seconds]);
  const total = seconds || 1;
  const offset = seconds === null ? 0 : Math.round(679 * (1 - left / total));
  const coarse = seconds === null ? "" : left > 60 ? `${Math.ceil(left / 60)} minutes` : `${Math.ceil(left / 10) * 10} seconds`;
  const shown = seconds === null ? (label ?? "a little while") : left >= 60 ? `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` : `${left}s`;
  return (
    <main role="status" style={{ maxWidth: 720, margin: "0 auto", padding: "24px 32px 72px", display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 20 }}>
      <svg width="240" height="240" viewBox="0 0 240 240" aria-hidden="true">
        <defs><radialGradient id="wb" cx="40%" cy="35%" r="70%"><stop offset="0" stopColor="#E9E3FF" /><stop offset=".5" stopColor="#8B7CF6" stopOpacity=".75" /><stop offset="1" stopColor="#2A2470" stopOpacity=".9" /></radialGradient></defs>
        <circle cx="120" cy="120" r="108" fill="none" stroke="rgba(255,255,255,.12)" strokeWidth="6" />
        <circle cx="120" cy="120" r="108" fill="none" stroke="#F4C566" strokeWidth="6" strokeLinecap="round" strokeDasharray="679" style={{ strokeDashoffset: offset, transition: "stroke-dashoffset 1s linear" }} transform="rotate(-90 120 120)" />
        <circle cx="120" cy="104" r="70" fill="#8B7CF6" opacity=".12" className="pulse" />
        <circle cx="120" cy="100" r="54" fill="url(#wb)" className="pulse" />
        <circle cx="104" cy="82" r="9" fill="#FFF" opacity=".55" />
        <circle cx="138" cy="112" r="2" fill="#FFF" className="tw" />
        <path d="M78 150 C 86 170, 104 176, 120 176 C 136 176, 154 170, 162 150 C 150 158, 136 161, 120 161 C 104 161, 90 158, 78 150 Z" fill="#F4C566" fillOpacity=".85" />
        <text x="120" y="208" textAnchor="middle" fontFamily="Cormorant Garamond,serif" fontSize="26" fontWeight="600" fill="#FFF">{shown}</text>
      </svg>
      <span className="sr" aria-live="polite">{coarse ? `About ${coarse} left` : ""}</span>
      <h1 style={{ margin: 0, font: "500 clamp(32px,5vw,44px)/1.1 var(--serif)", color: "#fff" }}>{title}</h1>
      {children}
    </main>
  );
}

export function Resting({ onRetry, requestId, children }: { onRetry?: () => void; requestId?: string; children?: ReactNode }) {
  return (
    <main role="alert" style={{ maxWidth: 720, margin: "0 auto", padding: "24px 32px 72px", display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 20 }}>
      <svg width="220" height="200" viewBox="0 0 220 200" aria-hidden="true">
        <defs><radialGradient id="cb" cx="40%" cy="35%" r="70%"><stop offset="0" stopColor="#E9E3FF" /><stop offset=".5" stopColor="#8B7CF6" stopOpacity=".75" /><stop offset="1" stopColor="#2A2470" stopOpacity=".9" /></radialGradient></defs>
        <circle cx="110" cy="84" r="64" fill="#8B7CF6" opacity=".12" className="pulse" />
        <circle cx="110" cy="80" r="50" fill="url(#cb)" className="pulse" />
        <circle cx="94" cy="62" r="8" fill="#FFF" opacity=".55" />
        <path d="M50 128 C 60 156, 84 166, 110 166 C 136 166, 160 156, 170 128 C 154 140, 134 146, 110 146 C 86 146, 66 140, 50 128 Z" fill="#F4C566" fillOpacity=".85" />
      </svg>
      <h1 style={{ margin: 0, font: "500 clamp(32px,5vw,44px)/1.1 var(--serif)", color: "#fff" }}>The oracle is resting</h1>
      {children ?? <p className="lead" style={{ maxWidth: 560 }}>Something went wrong on our side. Your details are kept, so nothing needs retyping.</p>}
      {onRetry && <button type="button" className="btn btn-gold" onClick={onRetry}>Try again</button>}
      {requestId && <p className="hint">Reference: {requestId}</p>}
    </main>
  );
}
