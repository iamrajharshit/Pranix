// SPDX-License-Identifier: AGPL-3.0-only
// Display helpers. Degrees are truncated, never rounded (FR-UI-01), so 29.99° shows 29°59′.

export const ABBR: Record<string, string> = { Sun: "Su", Moon: "Mo", Mars: "Ma", Mercury: "Me", Jupiter: "Ju", Venus: "Ve", Saturn: "Sa", Rahu: "Ra", Ketu: "Ke" };
export const SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"];
export const ORD = ["", "first", "second", "third", "fourth"];

export function dm(deg: number): string {
  const d = Math.floor(deg);
  const m = Math.min(59, Math.floor((deg - d) * 60 + 1e-9)); // truncate, never show the next minute's 60
  return `${d}°${String(m).padStart(2, "0")}′`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function shortDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

export function span(startIso: string, endIso: string): string {
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime();
  const days = ms / 86_400_000;
  if (days >= 365.25) {
    const y = Math.floor(days / 365.25), mo = Math.floor((days - y * 365.25) / 30.4375);
    return mo ? `${y} y ${mo} m` : `${y} y`;
  }
  if (days >= 30.4375) { const mo = Math.floor(days / 30.4375); const d = Math.floor(days - mo * 30.4375); return d ? `${mo} m ${d} d` : `${mo} m`; }
  if (days >= 1) { const d = Math.floor(days); const h = Math.floor((days - d) * 24); return h ? `${d} d ${h} h` : `${d} d`; }
  return `${Math.max(1, Math.round(days * 24))} h`;
}

export function the(planet: string): string { return planet === "Sun" || planet === "Moon" ? `the ${planet}` : planet; }
