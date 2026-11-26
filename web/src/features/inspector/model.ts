// SPDX-License-Identifier: AGPL-3.0-only
// Bundle -> view groups. The ONLY place that fixes the Snapshot order (D81 §1); pure and tested on
// the engine's exported fixtures. It formats data for display; it computes no astrology.
import { dm } from "../../lib/format";
import type { InspectionBundle } from "./api";
import type { ChartId, InspectTarget, PlanetId } from "./urlState";

export interface ChipView { label: string; target?: InspectTarget; aria?: string }
export interface GroupView { id: string; title: string; head?: string; chips: ChipView[]; note?: string; lines?: string[] }

const DIG: Record<string, string> = {
  own: "own sign", exalted: "exalted", debilitated: "debilitated", friend: "friend's sign", enemy: "enemy's sign", neutral: "neutral sign",
};
const ORDN = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th", "11th", "12th"];
const NODES = ["Rahu", "Ketu"];
const join = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
const planet = (chart: ChartId, ref: string): ChipView => ({ label: ref, target: { chart, kind: "planet", ref: ref as PlanetId }, aria: `Inspect ${ref}` });
const fact = (label: string): ChipView => ({ label });
const who = (occ: string[]) => (occ.length ? join(occ) : "empty");

export const HOUSE_WORDS = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
const house = (chart: ChartId, n: number): ChipView => ({ label: `House ${n}`, target: { chart, kind: "house", ref: n }, aria: `Inspect house ${HOUSE_WORDS[n]}` });

/** Panel title: "Jupiter", or "House seven · Aquarius" once the data has arrived. */
export function titleOf(b: InspectionBundle | undefined, kind: "planet" | "house", ref: string | number): string {
  if (kind === "planet") return String(ref);
  const word = HOUSE_WORDS[Number(ref)] ?? String(ref);
  return b?.house ? `House ${word} · ${b.house.sign}` : `House ${word}`;
}

export function toSnapshot(b: InspectionBundle): GroupView[] {
  const groups = b.target.kind === "house" ? houseSnapshot(b) : planetSnapshot(b);
  return groups.map((g) => withLines(g, b));
}

// I5: the server's approved library lines go under the group they explain. Where a line says what a
// group's own note said (empty house, nothing looks at it), the line replaces the note: one voice, reviewed.
const REPLACES_NOTE = new Set(["occupants", "lookedby"]);
function withLines(g: GroupView, b: InspectionBundle): GroupView {
  const lines = (b.lines ?? []).filter((l) => l.group === g.id).map((l) => l.text);
  if (!lines.length) return g;
  const note = b.target.kind === "house" && REPLACES_NOTE.has(g.id) ? undefined : g.note;
  return { ...g, note, lines };
}

/** I5: lines that belong right under the summary (a planet in its house). */
export const summaryLines = (b: InspectionBundle): string[] => (b.lines ?? []).filter((l) => l.group === "summary").map((l) => l.text);

/** House panel, D81 order: Occupants → Its lord → [Aspects: Looked at by, I3] → same house in the other chart → Either side. */
function houseSnapshot(b: InspectionBundle): GroupView[] {
  const c = b.chart as ChartId, h = b.house, lord = b.lord;
  if (!h || !lord) return [];
  const g: GroupView[] = [];
  g.push({ id: "occupants", title: "Occupants", chips: h.occupants.map((x) => planet(c, x)),
    note: h.occupants.length ? undefined
      : b.aspects_in?.length ? "Empty house: read it through its lord and the planets that look at it." : "Empty house: read it through its lord." });
  g.push({ id: "lord", title: "Its lord", chips: [planet(c, lord.planet), house(c, lord.house)],
    note: `${lord.planet} rules ${h.sign} and sits in the ${ORDN[lord.house]} house, in ${lord.sign}${lord.dignity ? ` (${DIG[lord.dignity]})` : ""}.`
      + (b.lord_other_chart ? ` In your ${c === "d1" ? "D9" : "D1"} it sits in the ${ORDN[b.lord_other_chart.house]} house, in ${b.lord_other_chart.sign}${b.lord_other_chart.dignity ? ` (${DIG[b.lord_other_chart.dignity]})` : ""}.` : "") });  // I4
  if (b.aspects_in) {
    g.push({ id: "lookedby", title: "Looked at by", head: "Aspects · drishti", chips: b.aspects_in.map((x) => planet(c, x)),
      note: b.aspects_in.length ? undefined : "No planet looks at this house." });
  }
  const o = b.same_house_other_chart;
  if (o) {
    const other = c === "d1" ? "D9" : "D1";
    g.push({ id: "other", title: `House ${h.house} in your ${other}`, chips: [fact(o.sign), ...o.occupants.map(fact)],
      note: o.occupants.length ? undefined : "Empty there too." });
  }
  if (b.either_side) {
    const e = b.either_side;
    g.push({ id: "sides", title: "Either side", chips: [house(c, e.before.house), house(c, e.after.house)],
      note: `Previous house: ${who(e.before.occupants)} · Next house: ${who(e.after.occupants)}` });
  }
  return g;
}

function planetSnapshot(b: InspectionBundle): GroupView[] {
  const c = b.chart as ChartId, node = NODES.includes(b.target.ref);
  const p = b.placement;
  if (!p || !b.dispositor) return [];
  const g: GroupView[] = [];

  // 1. Placement (+ Vargottama) with the calm gloss (D81 §3)
  const place: ChipView[] = [];
  if (p.sign) place.push(fact(p.sign)); else (p.sign_options ?? []).forEach((s) => place.push(fact(s)));
  if (p.house != null) place.push(house(c, p.house));
  if (p.dignity) place.push(fact(DIG[p.dignity]));
  if (p.vargottama) place.push(fact("Vargottama"));
  if (p.deg_in_sign != null) place.push(fact(dm(p.deg_in_sign)));
  if (p.nakshatra) place.push(fact(p.nakshatra)); else (p.nakshatra_options ?? []).forEach((n) => place.push(fact(n)));
  if (p.retrograde === true && !node) place.push(fact("Retrograde"));
  const twoStars = !p.nakshatra && (p.nakshatra_options?.length ?? 0) > 1;
  const twoSigns = !p.sign && (p.sign_options?.length ?? 0) > 1;
  const placeNote = [p.dignity_gloss, twoSigns ? `${b.target.ref} changes sign during that day, so both are shown.` : null,
    twoStars ? `${b.target.ref} changes star during that day, so both are shown.` : null].filter(Boolean).join(" ");
  g.push({ id: "placement", title: "Placement", chips: place, note: placeNote || undefined });

  // 2. Houses it rules (nodes act through their sign lord)
  if (node && b.acts_through) {
    g.push({ id: "rules", title: "Houses it rules", chips: [planet(c, b.acts_through)],
      note: `Node: rules no sign, so it acts through ${b.acts_through}, the lord of ${p.sign}.` });
  } else if (b.houses_ruled) {
    g.push({ id: "rules", title: "Houses it rules", chips: b.houses_ruled.map((h) => house(c, h.house)),
      note: b.houses_ruled.map((h) => `${ORDN[h.house]} house, ${h.sign}: ${who(h.occupants)}`).join(" · ") });
  }

  // 3. Sits with
  const where = b.level === "house" ? "house" : "sign";
  g.push({ id: "with", title: b.level === "house" ? "Sits with" : "Same sign", chips: b.sits_with.map((x) => planet(c, x)),
    note: b.sits_with.length ? undefined : `No other planet in this ${where}.` });

  // 4. Aspects · drishti (I3, jyotish-core@1). House level counts houses; sign level counts signs (D81 4).
  const by = b.level === "house" ? "" : " (by sign)";
  if (b.aspects_out) {
    g.push({ id: "looks", title: "Looks at", head: "Aspects · drishti", chips: b.aspects_out.map((h) => house(c, h.house)),
      note: b.aspects_out.map((h) => `${ORDN[h.house]}${h.occupants.length ? ` (${join(h.occupants)})` : ""}`).join(" · ") });
  } else if (b.aspects_out_signs) {
    g.push({ id: "looks", title: `Looks at${by}`, head: "Aspects · drishti", chips: b.aspects_out_signs.map(fact),
      note: "Counted by sign, because houses need a birth time." });
  }
  if (b.aspects_in) {
    const first = !(b.aspects_out || b.aspects_out_signs);
    g.push({ id: "lookedby", title: `Looked at by${by}`, head: first ? "Aspects · drishti" : undefined, chips: b.aspects_in.map((x) => planet(c, x)),
      note: b.aspects_in.length ? undefined : `No planet looks at its ${b.level === "house" ? "house" : "sign"}.` });
  }

  // 5. In your D9 / D1
  if (b.other_chart) {
    const o = b.other_chart, other = o.chart.toUpperCase();
    g.push({ id: "other", title: `In your ${other}`, chips: [fact(o.sign), fact(`House ${o.house}`), fact(o.dignity ? DIG[o.dignity] : "—")],
      note: p.vargottama ? "Same sign in both charts: vargottama, a steadying signal."
        : o.change === "none" ? "Nodes carry no dignity; read them through their sign lord in each chart."
        : o.change === "same" ? "Same dignity in both charts."
        : `Dignity changes from ${DIG[p.dignity ?? ""] ?? "—"} to ${DIG[o.dignity ?? ""] ?? "—"}.` });
  }

  // 6. Dispositor chain
  const d = b.dispositor, last = d.steps[d.steps.length - 1];
  const end = d.end === "final" ? (d.steps.length === 1 ? `${b.target.ref} is its own lord here: a final dispositor.` : `The chain ends at ${last}, in its own sign.`)
    : d.end === "exchange" ? `The chain ends in an exchange: ${d.pair?.[0]} and ${d.pair?.[1]} sit in each other's signs.`
    : d.end === "cycle" ? `The chain ends in a loop: ${(d.cycle_members ?? []).join(" → ")} → ${d.cycle_members?.[0] ?? ""}.`
    : `The chain stops at ${last}, whose sign depends on the birth time.`;
  g.push({ id: "chain", title: "Dispositor chain", chips: d.steps.map((x) => planet(c, x)), note: end });

  // 7. Either side (last until kartari ships in V2)
  if (b.either_side) {
    const e = b.either_side;
    g.push({ id: "sides", title: "Either side", chips: [house(c, e.before.house), house(c, e.after.house)],
      note: `Previous house: ${who(e.before.occupants)} · Next house: ${who(e.after.occupants)}` });
  }
  return g;
}

const NEEDS: Record<string, string> = { house: "house", houses_ruled: "houses it rules", degree: "degree", d9: "the D9" };

/** Sign level (D56): what the birth time would add, in plain words. */
export function needsTime(b: InspectionBundle): string | null {
  if (!b.placement) return null;
  const xs = b.unavailable.filter((u) => u.reason === "BIRTH_TIME_REQUIRED").map((u) => NEEDS[u.what]).filter(Boolean);
  return xs.length ? `${join(xs.map((x, i) => (i === 0 ? x[0].toUpperCase() + x.slice(1) : x)))}. Add a birth time to see them.` : null;
}
