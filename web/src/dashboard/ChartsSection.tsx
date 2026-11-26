// SPDX-License-Identifier: AGPL-3.0-only
// Charts section (FR-DASH-22): D1 / D9 / Dasha tabs; North Indian chart with two-way highlight and
// a planet table. Unknown birth time (D56): no charts, only what held all day, both options shown.
import type { Master } from "../api/types";
import { ABBR, dm } from "../lib/format";
import DashaTimeline from "./DashaTimeline";
import NorthChart, { type ChartPlanet } from "./NorthChart";

export type ChartTab = "d1" | "d9" | "dasha";

export default function ChartsSection({ m, profileId, tab, setTab, selected, setSelected, onExpired, onAddTime }: {
  m: Master; profileId: string; tab: ChartTab; setTab(t: ChartTab): void; selected: string | null; setSelected(id: string | null): void;
  onExpired(): void; onAddTime(): void;
}) {
  const known = m.meta.birth_time_known;
  const pick = (id: string) => setSelected(selected === id ? null : id);
  const ts = Object.fromEntries(m.flags.time_sensitive.map((t) => [t.fact_id, t.values]));

  const d1Planets: ChartPlanet[] = known ? m.d1.planets.map((p) => ({
    id: p.id, house: p.house!, label: `${ABBR[p.id]} ${Math.floor(p.deg_in_sign!)}°${p.retrograde && p.id !== "Rahu" && p.id !== "Ketu" ? " ℞" : ""}`,
    aria: `${p.id} in ${p.sign}, house ${p.house}${p.retrograde && p.id !== "Rahu" && p.id !== "Ketu" ? ", retrograde" : ""}`,
  })) : [];
  const d9Planets: ChartPlanet[] = m.d9 ? m.d9.planets.map((p) => ({
    id: p.id, house: p.house, label: `${ABBR[p.id]}${p.retrograde && p.id !== "Rahu" && p.id !== "Ketu" ? " ℞" : ""}`, aria: `${p.id} in ${p.sign}, house ${p.house}`,
  })) : [];

  const notes: string[] = [];
  if (known && tab === "d9" && m.d9) {
    // D9 caption fix (plan §9, F4): on the D9 tab, describe the D9 chart, not the D1 rising sign.
    notes.push(`D9 rising sign ${m.d9.lagna.sign}. House one is the top centre diamond; houses run anticlockwise.`);
    const strong9 = m.d9.planets.filter((p) => p.dignity === "exalted" || p.dignity === "own").map((p) => `${p.id} (${p.dignity})`);
    if (strong9.length) notes.push(`Strong in D9: ${strong9.join(", ")}.`);
    const varg = m.d1.planets.filter((p) => p.vargottama).map((p) => p.id);
    if (varg.length) notes.push(`Same sign in D1 and D9 (vargottama): ${varg.join(", ")}.`);
    const near = m.flags.near_boundary.map((f) => f.split(".")[0]).map((k) => (k === "lagna" ? "the rising sign" : k[0].toUpperCase() + k.slice(1)));
    notes.push(near.length
      ? `The D9 depends on the exact birth minute. Near a boundary: ${near.join(", ")}; a few minutes' difference could move ${near.length > 1 ? "them" : "it"}.`
      : "The D9 depends on the exact birth minute, so it is only as precise as your birth time.");
  } else if (known && m.d1.lagna) {
    const lg = m.d1.lagna;
    notes.push(`Rising sign ${lg.sign} at ${dm(lg.deg_in_sign)}, in ${lg.nakshatra} pada ${lg.pada}. House one is the top centre diamond; houses run anticlockwise.`);
    const strong = m.d1.planets.filter((p) => p.dignity === "exalted" || p.dignity === "own").map((p) => `${p.id} (${p.dignity})`);
    if (strong.length) notes.push(`Strong placements: ${strong.join(", ")}.`);
    const varg = m.d1.planets.filter((p) => p.vargottama).map((p) => p.id);
    if (varg.length) notes.push(`Same sign in D1 and D9 (vargottama): ${varg.join(", ")}.`);
  }

  return (
    <section id="charts" aria-labelledby="charts-h" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <svg width="92" height="28" viewBox="0 0 92 28" aria-hidden="true"><rect x="30" y="2" width="24" height="24" fill="none" stroke="#F4C566" strokeOpacity=".7" transform="rotate(45 42 14)" /><circle cx="42" cy="14" r="3" fill="#F4C566" className="tw" /></svg>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><div className="eyebrow" style={{ color: "var(--gold)" }}>Your kundli</div><h2 className="h2g" id="charts-h">Your birth charts</h2></div>
        <p style={{ margin: 0, fontSize: 15, color: "var(--muted)", flexBasis: "100%", maxWidth: 700 }}>
          {known ? "Your D1 birth chart shows where each planet stood; the D9 navamsa chart refines it. Tap a planet to find it in both." : "Without a birth time we cannot draw your charts. Below is what stayed true for your whole birth day."}
        </p>
      </div>
      <div role="tablist" aria-label="Chart" style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        <button type="button" role="tab" className="tab" aria-selected={tab === "d1"} onClick={() => setTab("d1")}>{known ? "D1 · Birth chart" : "Signs and stars"}</button>
        {known && <button type="button" role="tab" className="tab" aria-selected={tab === "d9"} onClick={() => setTab("d9")}>D9 · Navamsa</button>}
        <button type="button" role="tab" className="tab" aria-selected={tab === "dasha"} onClick={() => setTab("dasha")}>Dasha timeline</button>
      </div>

      {tab === "dasha" ? <DashaTimeline profileId={profileId} onExpired={onExpired} /> : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 28, alignItems: "start", background: "radial-gradient(80% 60% at 0% 0%,rgba(244,197,102,.07),transparent 60%),#12123A", border: "1px solid rgba(255,255,255,.14)", borderRadius: 24, padding: 24 }}>
          {known && m.d1.lagna ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {tab === "d1"
                ? <NorthChart firstSign={m.d1.lagna.sign} planets={d1Planets} mark="ASC" selected={selected} onPick={pick} aria={`D1 birth chart, ${m.d1.lagna.sign} rising`} />
                : <NorthChart firstSign={m.d9!.lagna.sign} planets={d9Planets} mark="ASC" selected={selected} onPick={pick} aria={`D9 navamsa chart, ${m.d9!.lagna.sign} rising`} />}
              <p className="hint" style={{ margin: 0, fontSize: 12, textAlign: "center" }}>Numbers in the chart are sign numbers (1 Aries … 12 Pisces). ℞ retrograde.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14, alignItems: "flex-start", padding: "8px 4px" }}>
              <strong style={{ font: "600 26px var(--serif)", color: "#fff" }}>Your charts need your birth time</strong>
              <p style={{ margin: 0, fontSize: 15, lineHeight: 1.65, color: "var(--text2)" }}>A birth chart is built on the rising sign, which changes every couple of hours, and the D9 chart changes even faster. Without your birth time we would be guessing, so we do not draw them.</p>
              <button type="button" className="btn btn-ghost" onClick={onAddTime}>Add a birth time</button>
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
            <div style={{ overflowX: "auto" }} tabIndex={0} role="region" aria-label="Planet table">
              <table className="pt">
                <caption style={{ textAlign: "left", font: "600 20px var(--serif)", color: "#fff", paddingBottom: 8 }}>{tab === "d9" ? "Planets in your D9" : known ? "Planets in your D1" : "What held all day"}</caption>
                <thead><tr><th scope="col">Planet</th><th scope="col">Sign</th>{known && tab === "d1" && <th scope="col">Degree</th>}{known && <th scope="col">House</th>}{tab !== "d9" && <th scope="col">Star</th>}<th scope="col">Dignity</th></tr></thead>
                <tbody>
                  {(tab === "d9" && m.d9 ? m.d9.planets.map((p) => ({ id: p.id, sign: p.sign, deg: "", house: p.house, star: "", dignity: p.dignity, retro: p.retrograde }))
                    : m.d1.planets.map((p) => ({
                      id: p.id, sign: p.sign ?? (ts[`${p.id.toLowerCase()}.sign`] ?? []).join(" or "), deg: p.deg_in_sign !== null ? dm(p.deg_in_sign) : "",
                      house: p.house, star: p.nakshatra ? `${p.nakshatra}${p.pada ? ` ${p.pada}` : ""}` : (ts[`${p.id.toLowerCase()}.nakshatra`] ?? []).join(" or "),
                      dignity: p.dignity, retro: p.retrograde,
                    }))).map((r) => (
                    <tr key={r.id} className={`rowbtn ${selected === r.id ? "on" : ""}`} onClick={() => known && pick(r.id)}>
                      <td><strong style={{ color: "#fff" }}>{r.id}</strong> {r.retro && r.id !== "Rahu" && r.id !== "Ketu" ? "℞" : ""}</td>
                      <td>{r.sign}</td>{known && tab === "d1" && <td>{r.deg}</td>}{known && <td>{r.house}</td>}{tab !== "d9" && <td>{r.star}</td>}<td>{r.dignity ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {notes.length > 0 && <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6, fontSize: 14, lineHeight: 1.55, color: "var(--text2)" }}>{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
            <p className="hint" style={{ margin: 0, fontSize: 12 }}>Sidereal zodiac, Lahiri ayanamsa {dm(m.meta.ayanamsa_value)} · whole-sign houses · mean node · degrees truncated, never rounded.</p>
          </div>
        </div>
      )}
    </section>
  );
}
