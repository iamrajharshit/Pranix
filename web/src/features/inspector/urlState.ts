// SPDX-License-Identifier: AGPL-3.0-only
// The Inspector's target in the address bar: ?inspect=d1.Jupiter or ?inspect=d9.h7
// (Inspector_data_contract_and_modules.md A8). Parsing never throws; anything unknown is ignored.
// normaliseTarget applies D81 §5: on an unknown-time profile there is no D9 and no houses, so a link
// to them falls back to the sign-level planet view, or to "needs your birth time" for a house.

export const PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"] as const;
export type PlanetId = (typeof PLANETS)[number];
export type ChartId = "d1" | "d9";

export type InspectTarget =
  | { chart: ChartId; kind: "planet"; ref: PlanetId }
  | { chart: ChartId; kind: "house"; ref: number };

export const PARAM = "inspect";

const RE = /^(d1|d9)\.(?:h(\d{1,2})|([A-Za-z]{3,8}))$/;

export function parseTarget(raw: string | null | undefined): InspectTarget | null {
  if (!raw) return null;
  const m = RE.exec(raw.trim());
  if (!m) return null;
  const chart = m[1] as ChartId;
  if (m[2] !== undefined) {
    const h = Number(m[2]);
    return Number.isInteger(h) && h >= 1 && h <= 12 ? { chart, kind: "house", ref: h } : null;
  }
  const name = m[3][0].toUpperCase() + m[3].slice(1).toLowerCase();
  return (PLANETS as readonly string[]).includes(name) ? { chart, kind: "planet", ref: name as PlanetId } : null;
}

export function formatTarget(t: InspectTarget): string {
  return t.kind === "house" ? `${t.chart}.h${t.ref}` : `${t.chart}.${t.ref}`;
}

export type Normalised =
  | { target: InspectTarget; note: null }
  | { target: InspectTarget; note: "D9_NEEDS_TIME" }          // D9 planet asked for; shown at sign level
  | { target: null; note: "HOUSES_NEED_TIME" };               // a house asked for; "Needs your birth time"

export function normaliseTarget(t: InspectTarget, birthTimeKnown: boolean): Normalised {
  if (birthTimeKnown) return { target: t, note: null };
  if (t.kind === "house") return { target: null, note: "HOUSES_NEED_TIME" };
  if (t.chart === "d9") return { target: { chart: "d1", kind: "planet", ref: t.ref }, note: "D9_NEEDS_TIME" };
  return { target: t, note: null };
}

/** Previous / Next with wrap-around: Sun ... Ketu, or house one ... twelve. */
export function stepTarget(t: InspectTarget, by: 1 | -1): InspectTarget {
  if (t.kind === "house") return { ...t, ref: ((t.ref - 1 + by + 12) % 12) + 1 };
  const i = PLANETS.indexOf(t.ref);
  return { ...t, ref: PLANETS[(i + by + PLANETS.length) % PLANETS.length] };
}

/** The D1/D9 switch keeps the target (D81, prototype §3.9). */
export function withChart(t: InspectTarget, chart: ChartId): InspectTarget {
  return { ...t, chart } as InspectTarget;
}
