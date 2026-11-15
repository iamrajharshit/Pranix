// SPDX-License-Identifier: AGPL-3.0-only
// Place search (FR-GEO-01) as an accessible combobox, with coordinates and an optional map.
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Place } from "../api/types";
import type { Draft } from "../lib/storage";
import { ErrIcon } from "./Shell";

const MapPicker = lazy(() => import("./MapPicker"));

type Chosen = NonNullable<Draft["place"]>;
interface Props {
  draft: Draft; error?: string;
  set(p: Partial<Draft>): void;
}

export function placeLabel(p: Place): Chosen {
  return { place_id: p.place_id, name: p.name, where: [p.admin1, p.country].filter(Boolean).join(", "), tz: p.tz, lat: p.lat, lon: p.lon };
}

export default function PlaceField({ draft, error, set }: Props) {
  const [q, setQ] = useState("");
  const [matches, setMatches] = useState<Place[]>([]);
  const [searched, setSearched] = useState(false);
  const [active, setActive] = useState(-1);
  const [mapOpen, setMapOpen] = useState(false);
  const [searchErr, setSearchErr] = useState("");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (q.trim().length < 2) { setMatches([]); setSearched(false); return; }
    const ctl = new AbortController();
    timer.current = window.setTimeout(() => {
      api.places(q.trim(), ctl.signal)
        .then((r) => { setMatches(r); setSearched(true); setActive(-1); setSearchErr(""); })
        .catch((e) => { if (e?.status === 429) setSearchErr("Searching too fast. Pause for a moment."); else if (e?.status !== 0) setSearchErr("Place search is not available right now. You can enter coordinates instead."); });
    }, 180);
    return () => { ctl.abort(); window.clearTimeout(timer.current); };
  }, [q]);

  const pick = (p: Place) => { set({ place: placeLabel(p), manual: false }); setQ(""); setMatches([]); };
  const bad = error ? "bad" : "";

  if (draft.place) {
    return (
      <Wrap error={error}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between", background: "#10102B", border: "1px solid rgba(244,197,102,.5)", borderRadius: 12, padding: "14px 16px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 16, color: "#fff" }}>{draft.place.name}{draft.place.where ? `, ${draft.place.where}` : ""}</span>
            <span className="hint">Time zone: {draft.place.tz}, set automatically. We apply the rules that were in force on your birth date.</span>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => set({ place: null })}>Change</button>
        </div>
      </Wrap>
    );
  }

  if (mapOpen) {
    return (
      <Wrap error={error}>
        <Suspense fallback={<p className="hint">Loading the map…</p>}>
          <MapPicker onUse={(c) => { set({ place: c, manual: false }); setMapOpen(false); }}
            onCoords={(lat, lon) => { set({ place: null, manual: true, lat: String(lat), lon: String(lon) }); setMapOpen(false); }}
            onClose={() => setMapOpen(false)} />
        </Suspense>
      </Wrap>
    );
  }

  if (draft.manual) {
    return (
      <Wrap error={error}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, background: "#10102B", border: "1px solid rgba(255,255,255,.2)", borderRadius: 12, padding: 16 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 160px", display: "flex", flexDirection: "column", gap: 6 }}><label className="hint" htmlFor="lat">Latitude (-90 to 90)</label>
              <input className={`f ${bad}`} id="lat" inputMode="decimal" placeholder="18.5204" value={draft.lat} aria-invalid={!!error}
                onChange={(e) => set({ lat: e.target.value.replace(/[^0-9.-]/g, "").slice(0, 12) })} /></div>
            <div style={{ flex: "1 1 160px", display: "flex", flexDirection: "column", gap: 6 }}><label className="hint" htmlFor="lon">Longitude (-180 to 180)</label>
              <input className={`f ${bad}`} id="lon" inputMode="decimal" placeholder="73.8567" value={draft.lon} aria-invalid={!!error}
                onChange={(e) => set({ lon: e.target.value.replace(/[^0-9.-]/g, "").slice(0, 12) })} /></div>
          </div>
          <span className="hint">North and East are positive. South and West are negative. We work out the time zone from these coordinates.</span>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => set({ manual: false })}>Search for a city instead</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { set({ manual: false }); setMapOpen(true); }}>Pick on a map</button>
          </div>
        </div>
      </Wrap>
    );
  }

  const open = matches.length > 0;
  return (
    <Wrap error={error}>
      <input className={`f ${bad}`} id="place" type="text" role="combobox" aria-expanded={open} aria-controls="places" aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `pl-${active}` : undefined} aria-invalid={!!error} aria-describedby="place-h place-e"
        placeholder="Start typing a city or town" autoComplete="off" value={q} maxLength={80}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (!open) return;
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(matches.length - 1, a + 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
          else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(matches[active]); }
          else if (e.key === "Escape") setMatches([]);
        }} />
      {open && (
        <ul id="places" role="listbox" style={{ listStyle: "none", margin: 0, padding: 6, background: "#1B1B42", border: "1px solid rgba(244,197,102,.6)", borderRadius: 12, display: "flex", flexDirection: "column", gap: 2 }}>
          {matches.map((m, i) => (
            <li key={m.place_id} role="presentation">
              <button type="button" role="option" id={`pl-${i}`} aria-selected={i === active} className="opt" onClick={() => pick(m)}>
                {m.name}<span style={{ color: "var(--muted)" }}>{[m.admin1, m.country].filter(Boolean).map((x) => `, ${x}`).join("")}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {searched && !open && (
        <div id="places" style={{ background: "#1B1B42", border: "1px solid rgba(244,197,102,.6)", borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <span style={{ fontSize: 15, lineHeight: 1.5 }}>No place found for "{q}". Check the spelling, or try the nearest larger town.</span>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setMapOpen(true)}>Pick on a map</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => set({ manual: true })}>Enter coordinates instead</button>
          </div>
        </div>
      )}
      {searchErr && <div className="err" role="alert"><ErrIcon />{searchErr}</div>}
      <span className="hint" id="place-h">Search is instant and works from a built-in list of cities and towns.</span>
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
        <button type="button" className="lnk" style={{ color: "var(--gold)" }} onClick={() => set({ manual: true })}>Cannot find it? Enter latitude and longitude</button>
        <button type="button" className="lnk" style={{ color: "var(--gold)" }} onClick={() => setMapOpen(true)}>Or pick it on a map</button>
      </div>
    </Wrap>
  );
}

function Wrap({ error, children }: { error?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, position: "relative" }}>
      <label className="lbl" htmlFor="place">Place of birth</label>
      {children}
      {error && <div className="err" id="place-e" role="alert"><ErrIcon /><span>{error}</span></div>}
    </div>
  );
}
