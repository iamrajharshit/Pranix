// SPDX-License-Identifier: AGPL-3.0-only
import { layout } from "../lib/chart";
import { ABBR, SIGNS } from "../lib/format";

const signName = (first: string, house: number) => SIGNS[(SIGNS.indexOf(first) + house - 1) % 12];

export interface ChartPlanet { id: string; house: number; label: string; aria: string }

// The twelve houses of the North Indian chart as polygons, in % of the square (house 1 = top diamond).
export const SHAPES: [number, number][][] = [
  [[50, 0], [75, 25], [50, 50], [25, 25]], [[0, 0], [50, 0], [25, 25]], [[0, 0], [25, 25], [0, 50]],
  [[0, 50], [25, 25], [50, 50], [25, 75]], [[0, 50], [25, 75], [0, 100]], [[0, 100], [25, 75], [50, 100]],
  [[50, 100], [25, 75], [50, 50], [75, 75]], [[50, 100], [75, 75], [100, 100]], [[100, 100], [75, 75], [100, 50]],
  [[100, 50], [75, 75], [50, 50], [75, 25]], [[100, 50], [75, 25], [100, 0]], [[100, 0], [75, 25], [50, 0]],
];
// An outline drawn just inside a house, so it never sits on the chart's own lines (I3 aspects).
const inset = (poly: [number, number][], k = 0.76) => {
  const cx = poly.reduce((a, q) => a + q[0], 0) / poly.length, cy = poly.reduce((a, q) => a + q[1], 0) / poly.length;
  return poly.map(([x, y]) => `${(cx + (x - cx) * k) * 4},${(cy + (y - cy) * k) * 4}`).join(" ");
};
const WORDS = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];

export default function NorthChart({ firstSign, planets, mark, selected, onPick, aria, onPickHouse, selectedHouse = null, looks = null }: {
  firstSign: string; planets: ChartPlanet[]; mark: string; selected: string | null; onPick(id: string): void; aria: string;
  onPickHouse?(house: number): void; selectedHouse?: number | null;   // I2: houses are buttons when the Inspector is on
  looks?: { from: string; houses: number[] } | null;                    // I3: houses the selected planet looks at (engine data)
}) {
  const cells = layout(firstSign, planets);
  const byId = Object.fromEntries(planets.map((p) => [p.id, p]));
  return (
    <div className="ni" role="group" aria-label={aria}>
      <svg viewBox="0 0 400 400" aria-hidden="true">
        <defs><linearGradient id="ng" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#1B1B4A" /><stop offset="1" stopColor="#0F0F2E" /></linearGradient></defs>
        <rect x="1" y="1" width="398" height="398" rx="6" fill="url(#ng)" stroke="#F4C566" strokeOpacity=".75" strokeWidth="2" />
        <line x1="0" y1="0" x2="400" y2="400" stroke="#F4C566" strokeOpacity=".45" />
        <line x1="400" y1="0" x2="0" y2="400" stroke="#F4C566" strokeOpacity=".45" />
        <polygon points="200,2 398,200 200,398 2,200" fill="none" stroke="#F4C566" strokeOpacity=".6" strokeWidth="1.5" />
        <polygon points="200,2 300,100 200,200 100,100" fill="#F4C566" fillOpacity=".06" />
        {looks?.houses.map((n) => (
          <polygon key={`a${n}`} className="aspect" points={inset(SHAPES[n - 1])} />
        ))}
      </svg>
      {onPickHouse && cells.map((h) => {
        // Each house's tap area is its real shape (a diamond or a triangle of the chart), so there is room
        // around the planet labels on top of it (WCAG 2.5.8). clip-path limits clicks to the shape.
        const poly = SHAPES[h.house - 1];
        const xs = poly.map((q) => q[0]), ys = poly.map((q) => q[1]);
        const x0 = Math.min(...xs), y0 = Math.min(...ys), w = Math.max(...xs) - x0, ht = Math.max(...ys) - y0;
        const clip = `polygon(${poly.map(([x, y]) => `${((x - x0) / w) * 100}% ${((y - y0) / ht) * 100}%`).join(", ")})`;
        const sign = signName(firstSign, h.house);
        return (
          <button key={`h${h.house}`} type="button" className={`hz ${selectedHouse === h.house ? "on" : ""}`} aria-pressed={selectedHouse === h.house}
            aria-label={`House ${WORDS[h.house]}, ${sign}${h.planets.length ? `, with ${h.planets.join(", ")}` : ", empty"}${looks?.houses.includes(h.house) ? `, ${looks.from} looks at it` : ""}`}
            style={{ left: `${x0}%`, top: `${y0}%`, width: `${w}%`, height: `${ht}%`, clipPath: clip }}
            onClick={() => onPickHouse(h.house)} />
        );
      })}
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
