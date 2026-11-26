// SPDX-License-Identifier: AGPL-3.0-only
import type { ReactNode } from "react";
import { navigate } from "../lib/router";

export function Link({ to, className, children, style }: { to: string; className?: string; children: ReactNode; style?: React.CSSProperties }) {
  return (
    <a href={to} className={className} style={style}
      onClick={(e) => { if (e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); navigate(to); }}>
      {children}
    </a>
  );
}

export function TopBar({ right }: { right?: ReactNode }) {
  return (
    <header className="wrap topbar">
      <Link to="/" className="brand">Pranix</Link>
      {right}
    </header>
  );
}

export function ErrIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" fill="none" stroke="#FFB4B4" strokeWidth="2" aria-hidden="true" style={{ flex: "none", marginTop: 2 }}>
      <circle cx="9" cy="9" r="7.5" /><path d="M9 5v5M9 12.5v.5" />
    </svg>
  );
}

export function SiteFooter() {
  return (
    <footer style={{ background: "#07071A", borderTop: "1px solid rgba(255,255,255,.08)" }}>
      <div className="wrap" style={{ display: "flex", flexWrap: "wrap", gap: 32, justifyContent: "space-between", fontSize: 14, lineHeight: 1.6, color: "var(--muted)", padding: "48px 32px" }}>
        <p style={{ margin: 0, maxWidth: 520 }}>For self-reflection only. Not medical, legal or financial advice, and not a prediction of events. Percentages such as elements and doshas are our own heuristics; see How we calculate.</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <Link to="/how">How we calculate</Link>
          <a href="https://github.com/iamrajharshit/Pranix" rel="noopener">Source code (AGPL-3.0)</a>
          <Link to="/legal">Terms and Privacy</Link>
        </div>
        <p style={{ margin: 0, maxWidth: 320 }}>Place data: GeoNames (CC BY 4.0). Planet positions: Swiss Ephemeris. Map: © OpenStreetMap contributors.</p>
      </div>
    </footer>
  );
}

// The toast moved to the UI kit (F4); re-exported so existing screens keep working.
export { Toast } from "../ui/Toast";
