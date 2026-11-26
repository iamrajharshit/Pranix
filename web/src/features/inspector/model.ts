// SPDX-License-Identifier: AGPL-3.0-only
// Bundle -> view groups. The ONLY place that fixes the Snapshot order (D81 §1); pure and tested on
// the engine's exported fixtures. It formats data for display; it computes no astrology.
import { dm } from "../../lib/format";
import type { InspectionBundle } from "./api";
import type { ChartId, InspectTarget, PlanetId } from "./urlState";

export interface ChipView { label: string; target?: InspectTarget; aria?: string }
export interface GroupView { id: string; title: string; head?: string; chips: ChipView[]; note?: string }

const DIG: Record<string, string> = {
  own: "own sign", exalted: "exalted", debilitated: "debilitated", friend: "friend's sign", enemy: "enemy's sign", neutral: "neutral sign",
};
const ORDN = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th", "11th", "12th"];
const NODES = ["Rahu", "Ketu"];
const join = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
const planet = (chart: ChartId, ref: string): ChipView => ({ label: ref, target: { chart, kind: "planet", ref: ref as PlanetId }, aria: `Inspect ${ref}` });
const fact = (label: string): ChipView => ({ label });
const who = (occ: string[]) => (occ.length ? join(occ) : "empty");

export function toSnapshot(b: InspectionBundle): GroupView[] {
  const c = b.chart as ChartId, p = b.placement, node = NODES.includes(b.target.ref);
  const g: GroupView[] = [];

  // 1. Placement (+ Vargottama) with the calm gloss (D81 §3)
  const place: ChipView[] = [];
  if (p.sign) place.push(fact(p.sign)); else (p.sign_options ?? []).forEach((s) => place.push(fact(s)));
  if (p.house != null) place.push(fact(`House ${p.house}`));
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
    g.push({ id: "rules", title: "Houses it rules", chips: b.houses_ruled.map((h) => fact(`House ${h.house}`)),
      note: b.houses_ruled.map((h) => `${ORDN[h.house]} house, ${h.sign}: ${who(h.occupants)}`).join(" · ") });
  }

  // 3. Sits with
  const where = b.level === "house" ? "house" : "sign";
  g.push({ id: "with", title: b.level === "house" ? "Sits with" : "Same sign", chips: b.sits_with.map((x) => planet(c, x)),
    note: b.sits_with.length ? undefined : `No other planet in this ${where}.` });

  // 4. Aspects · drishti (I3: shown once the aspect table is approved; null = not yet available)
  if (b.aspects_out) {
    g.push({ id: "looks", title: "Looks at", head: "Aspects · drishti", chips: b.aspects_out.map((h) => fact(`House ${h.house}`)),
      note: b.aspects_out.map((h) => `${ORDN[h.house]}${h.occupants.length ? ` (${join(h.occupants)})` : ""}`).join(" · ") });
  }
  if (b.aspects_in) {
    g.push({ id: "lookedby", title: "Looked at by", head: b.aspects_out ? undefined : "Aspects · drishti", chips: b.aspects_in.map((x) => planet(c, x)),
      note: b.aspects_in.length ? undefined : "No planet looks at this house." });
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
    g.push({ id: "sides", title: "Either side", chips: [fact(`House ${e.before.house}`), fact(`House ${e.after.house}`)],
      note: `Previous house: ${who(e.before.occupants)} · Next house: ${who(e.after.occupants)}` });
  }
  return g;
}

const NEEDS: Record<string, string> = { house: "house", houses_ruled: "houses it rules", degree: "degree", d9: "the D9", aspects: "aspects" };

/** Sign level (D56): what the birth time would add, in plain words. */
export function needsTime(b: InspectionBundle): string | null {
  const xs = b.unavailable.filter((u) => u.reason === "BIRTH_TIME_REQUIRED").map((u) => NEEDS[u.what]).filter(Boolean);
  return xs.length ? `${join(xs.map((x, i) => (i === 0 ? x[0].toUpperCase() + x.slice(1) : x)))}. Add a birth time to see them.` : null;
}
