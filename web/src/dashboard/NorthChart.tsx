// SPDX-License-Identifier: AGPL-3.0-only
import { ABBR } from "../lib/format";
import { layout } from "../lib/chart";

export interface ChartPlanet { id: string; house: number; label: string; aria: string }

export default function NorthChart({ firstSign, planets, mark, selected, onPick, aria }: {
  firstSign: string; planets: ChartPlanet[]; mark: string; selected: string | null; onPick(id: string): void; aria: string;
}) {
  const cells = layout(firstSign, planets);
  const byId = Object.fromEntries(planets.map((p) => [p.id, p]));
  return (
    <div className="ni" role="img" aria-label={aria}>
      <svg viewBox="0 0 400 400" aria-hidden="true">
        <defs><linearGradient id="ng" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#1B1B4A" /><stop offset="1" stopColor="#0F0F2E" /></linearGradient></defs>
        <rect x="1" y="1" width="398" height="398" rx="6" fill="url(#ng)" stroke="#F4C566" strokeOpacity=".75" strokeWidth="2" />
        <line x1="0" y1="0" x2="400" y2="400" stroke="#F4C566" strokeOpacity=".45" />
        <line x1="400" y1="0" x2="0" y2="400" stroke="#F4C566" strokeOpacity=".45" />
        <polygon points="200,2 398,200 200,398 2,200" fill="none" stroke="#F4C566" strokeOpacity=".6" strokeWidth="1.5" />
        <polygon points="200,2 300,100 200,200 100,100" fill="#F4C566" fillOpacity=".06" />
      </svg>
      {cells.map((h) => (
        <div key={h.house}>
          <span className="sn" style={{ left: `${h.sx}%`, top: `${h.sy}%` }} aria-hidden="true">{h.signNo}</span>
          <div className="hs" style={{ left: `${h.x}%`, top: `${h.y}%` }}>
            {h.house === 1 && <span className="asc">{mark}</span>}
            {h.planets.map((id) => (
              <button key={id} type="button" className={`pl ${selected === id ? "on" : ""}`} aria-label={byId[id].aria} aria-pressed={selected === id} onClick={() => onPick(id)}>
                {byId[id].label || ABBR[id]}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
