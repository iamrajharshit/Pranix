// SPDX-License-Identifier: AGPL-3.0-only
// Card visuals come from the Master JSON, never from text (QA-13): numbers on screen are engine output.
import type { Master } from "../api/types";
import { DeitySymbol, StarGlyph } from "../components/Art";
import { DOSHA_COLOR, ELEMENT_COLOR } from "./config";

const WEEK = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const CHAKRA_NAME: Record<string, string> = { muladhara: "Root", svadhisthana: "Sacral", manipura: "Navel", anahata: "Heart", vishuddha: "Throat", ajna: "Brow", sahasrara: "Crown" };

function Bars({ pct, colors }: { pct: Record<string, number>; colors: Record<string, string> }) {
  const order = Object.keys(pct).sort((a, b) => pct[b] - pct[a]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 7, width: "100%" }}>
      {order.map((k) => (
        <div key={k} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          <span style={{ width: 62, color: "#E2DEF7" }}>{k}</span>
          <div className="bar"><span style={{ width: `${pct[k]}%`, background: colors[k] }} /></div>
          <span style={{ width: 36, textAlign: "right", color: "#fff", fontWeight: 600 }}>{pct[k]}%</span>
        </div>
      ))}
    </div>
  );
}

export default function CardVisual({ id, m, name }: { id: string; m: Master; name: string }) {
  switch (id) {
    case "identity": {
      const trio = [["Rising", m.identity.lagna?.sign, 30], ["Moon", m.identity.moon?.sign, 38], ["Sun", m.identity.sun?.sign, 46]] as const;
      return (
        <div style={{ display: "flex", gap: 14, alignItems: "flex-end", justifyContent: "center", width: "100%" }}>
          {trio.map(([k, v, s]) => (
            <div key={k} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, minWidth: 78 }}>
              <span className="pulse" style={{ width: s, height: s, borderRadius: "50%", background: v ? (k === "Sun" ? "#F4A300" : k === "Moon" ? "#F5F3EC" : "#F4C566") : "transparent",
                border: v ? "none" : "1px dashed #B8B3D6", boxShadow: v ? "0 0 18px rgba(244,197,102,.5)" : "none" }} />
              <span style={{ fontSize: 12, color: "var(--muted)" }}>{k}</span>
              <span style={{ fontSize: 13, color: "#fff", fontWeight: 600 }}>{v ?? "needs time"}</span>
            </div>
          ))}
        </div>
      );
    }
    case "birthstar": {
      const n = m.nakshatra;
      const alt = m.flags.time_sensitive.find((t) => t.fact_id === "moon.nakshatra")?.values;
      return (
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          {n && <StarGlyph name={n.name} />}
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ font: "600 24px var(--serif)", color: "#fff" }}>{n ? n.name : alt?.join(" or ")}</span>
            <span style={{ fontSize: 13, color: "var(--text2)" }}>{n ? `${n.symbol} · ruled by ${n.lord}` : "The Moon changed star that day"}</span>
            {n && <span style={{ fontSize: 12, color: "var(--muted)" }}>Symbolic pattern</span>}
          </div>
        </div>
      );
    }
    case "nameletter": {
      const nm = m.naming;
      const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/aa/g, "a").replace(/ee/g, "i").replace(/oo/g, "u");
      const match = name ? nm.syllables.find((s) => norm(name).startsWith(norm(s.latin))) : undefined; // browser only (NFR-PRIV-07)
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "center" }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }} role="img" aria-label={`Syllables of ${nm.nakshatra}: ${nm.syllables.map((s) => s.latin).join(", ")}${nm.pada ? `; yours is ${nm.syllables[nm.pada - 1].latin}` : ""}`}>
            {nm.syllables.map((s) => {
              const mine = nm.pada === s.pada;
              return (
                <div key={s.pada} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                  <span style={{ width: 52, height: 52, borderRadius: "50%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", font: "600 18px/1 var(--serif)",
                    color: mine ? "#1A1226" : "#fff", background: mine ? "#F4C566" : "rgba(255,255,255,.06)", border: mine ? "none" : "1px solid rgba(255,255,255,.25)", boxShadow: mine ? "0 0 16px rgba(244,197,102,.7)" : "none" }}>
                    <span>{s.deva}</span><span style={{ fontSize: 11, fontFamily: "var(--sans)" }}>{s.latin}</span>
                  </span>
                </div>
              );
            })}
          </div>
          {match && <span style={{ fontSize: 12, color: "var(--gold-l)" }}>Your name begins with {match.latin}, a nice echo of the tradition.</span>}
        </div>
      );
    }
    case "elements": return m.elements ? <Bars pct={m.elements.percent} colors={ELEMENT_COLOR} /> : null;
    case "doshas": return m.doshas ? <Bars pct={m.doshas.percent} colors={DOSHA_COLOR} /> : null;
    case "chakras":
      return m.chakras ? (
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end", justifyContent: "center", width: "100%" }}>
          {m.chakras.map((c) => {
            const s = c.class === "dominant" ? 30 : c.class === "balanced" ? 22 : 16;
            return (
              <div key={c.id} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, width: 40 }}>
                <span style={{ width: s, height: s, borderRadius: "50%", background: c.class === "low_activity" ? "transparent" : "#6FD6C9",
                  border: c.class === "low_activity" ? "1px dashed #6FD6C9" : "none", boxShadow: c.class === "dominant" ? "0 0 14px #6FD6C9" : "none" }} />
                <span style={{ fontSize: 10, color: "var(--text2)", textAlign: "center" }}>{CHAKRA_NAME[c.id]}</span>
              </div>
            );
          })}
        </div>
      ) : null;
    case "motive": {
      const ak = m.purpose.atmakaraka, ax = m.purpose.rahu_ketu_axis;
      return (
        <svg width="240" height="88" viewBox="0 0 240 88" role="img" aria-label={`Soul planet ${ak ?? "unknown"}${ax ? `, Rahu in house ${ax.rahu_house}` : ""}`}>
          {ax && <><line x1="20" y1="72" x2="220" y2="16" stroke="#C9C0FF" strokeOpacity=".6" strokeDasharray="4 4" />
            <circle cx="20" cy="72" r="5" fill="#C9C0FF" /><text x="30" y="84" fill="#D5D0EE" fontSize="11" fontFamily="Inter">Ketu</text>
            <circle cx="220" cy="16" r="5" fill="#C9C0FF" /><text x="176" y="12" fill="#D5D0EE" fontSize="11" fontFamily="Inter">Rahu</text></>}
          <circle cx="120" cy="44" r="16" fill="#A99CFF" className="pulse" />
          <text x="120" y="80" textAnchor="middle" fill="#fff" fontSize="12" fontFamily="Inter" fontWeight="600">{ak}</text>
        </svg>
      );
    }
    case "season": {
      const ch = m.dasha.active_chain;
      if (!ch) return null;
      const now = Date.now();
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
          <span style={{ fontSize: 11, color: "var(--faint)", alignSelf: "flex-end" }}>As of {new Date(m.dasha.as_of).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</span>
          {ch.slice(0, 2).map((p) => {
            const s = new Date(p.start).getTime(), e = new Date(p.end).getTime();
            return (
              <div key={p.path} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}><span style={{ color: "#fff", fontWeight: 600 }}>{p.lord}</span>
                  <span style={{ color: "var(--muted)" }}>{new Date(p.start).getFullYear()} to {new Date(p.end).getFullYear()}</span></div>
                <div className="bar"><span style={{ width: `${Math.min(100, Math.max(0, ((now - s) / (e - s)) * 100))}%`, background: "#A99CFF" }} /></div>
              </div>
            );
          })}
        </div>
      );
    }
    case "growth":
      return <svg width="220" height="88" viewBox="0 0 220 88" aria-hidden="true"><path d="M10 78 Q 70 70 100 46 T 210 10" fill="none" stroke="#6FD6C9" strokeWidth="2" strokeDasharray="5 5" /><circle cx="10" cy="78" r="4" fill="#6FD6C9" /><circle cx="100" cy="46" r="5" fill="#6FD6C9" className="pulse" /><circle cx="210" cy="10" r="6" fill="#F4C566" className="tw" /></svg>;
    case "deity": return m.ishta_devta ? <DeitySymbol name={m.ishta_devta.main} /> : null;
    case "colors":
      return m.colors ? (
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          {m.colors.swatches.map((w) => (
            <div key={w.name} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <span style={{ width: 52, height: 52, borderRadius: "50%", background: w.hex, boxShadow: w.dark ? "none" : `0 0 18px ${w.hex}88`, border: w.dark ? "2px solid #D5D0EE" : "none" }} />
              <span style={{ fontSize: 13, color: "#fff", fontWeight: 600 }}>{w.name}</span>
              <span style={{ fontSize: 11, color: "var(--muted)" }}>{w.planets.join(", ")}</span>
            </div>
          ))}
        </div>
      ) : null;
    case "days": {
      const on = new Set((m.days?.items ?? []).map((d) => d.weekday));
      return (
        <div style={{ display: "flex", gap: 6 }} role="img" aria-label={`Supportive days: ${[...on].join(", ")}`}>
          {WEEK.map((d) => (
            <div key={d} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <span style={{ width: 34, height: 34, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", font: "600 12px var(--sans)",
                color: on.has(d) ? "#1A1226" : "var(--muted)", background: on.has(d) ? "#F2A6C0" : "transparent", border: on.has(d) ? "none" : "1px solid rgba(255,255,255,.2)",
                boxShadow: on.has(d) ? "0 0 12px #F2A6C0" : "none" }}>{d.slice(0, 2)}</span>
            </div>
          ))}
        </div>
      );
    }
    default: return null;
  }
}
