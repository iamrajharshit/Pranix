// SPDX-License-Identifier: AGPL-3.0-only
// Types mirroring the backend JSON (contracts in backend/src/pranix). Only fields the UI reads.

export type Dignity = "exalted" | "own" | "friend" | "neutral" | "enemy" | "debilitated" | null;
export interface Planet {
  id: string; sign: string | null; deg_in_sign: number | null; house: number | null;
  retrograde: boolean | null; dignity: Dignity; nakshatra: string | null; pada: number | null; vargottama: boolean | null;
}
export interface Lagna { sign: string; deg_in_sign: number; nakshatra: string; pada: number; vargottama: boolean }
export interface House { house: number; sign: string }
export interface D9Planet { id: string; sign: string; house: number; retrograde: boolean; dignity: Dignity }
// start is null on the period running at birth (D86 C1: the birth instant never leaves the server);
// period_start (when that period itself began) is only for drawing bars, never printed.
export interface DashaPeriod { lord: string; level: number; start: string | null; end: string; path: string; from_birth?: boolean; period_start?: string; contains_now?: boolean; cycle?: number /* D84: absent means the first run */ }

/** For drawing only: where a bar segment begins. */
export const begins = (p: DashaPeriod): string => p.start ?? p.period_start ?? p.end;
export interface Swatch { name: string; hex: string; planets: string[]; roles: string[]; kind: string; dark: boolean }
export interface Syllable { pada: number; latin: string; deva: string }
export interface Fact { label: string; target: { kind: string; ref: string; chart: "d1" | "d9" | "none" } }

export interface Master {
  meta: { schema_version: string; birth_time_known: boolean; ayanamsa_value: number; ephemeris_mode: string; ruleset: { id: string; version: number }; dasha_year_days: number };
  identity: { lagna: { sign: string; lord: string; deg_in_sign: number } | null; moon: { sign: string } | null; sun: { sign: string } | null };
  nakshatra: { number: number; name: string; pada: number | null; lord: string; deity: string; symbol: string } | null;
  naming: { nakshatra: string; pada: number | null; syllables: Syllable[]; alternatives: { nakshatra: string; syllables: Syllable[] }[] };
  d1: { lagna: Lagna | null; houses: House[] | null; planets: Planet[] };
  d9: { lagna: { sign: string }; houses: House[]; planets: D9Planet[] } | null;
  purpose: { atmakaraka: string | null; rahu_ketu_axis: { rahu_house: number; ketu_house: number } | null };
  ishta_devta: { main: string; others: string[]; deciding_planet: string; time_sensitive: boolean } | null;
  colors: { swatches: Swatch[] } | null;
  days: { items: { weekday: string; planets: string[]; roles: string[] }[] } | null;
  elements: { percent: Record<string, number> } | null;
  doshas: { percent: Record<string, number>; label: string; dominant: string[] } | null;
  chakras: { id: string; planet: string; dignity: Dignity; class: "dominant" | "balanced" | "low_activity" }[] | null;
  dasha: { as_of: string; active_chain: DashaPeriod[] | null };
  facts: Record<string, Fact>;
  flags: {
    near_boundary: string[];
    time_sensitive: { fact_id: string; values: string[] }[];
    minute_window?: number | null;                                 // D83: the birth time's margin in minutes
    minute_sensitive?: { fact_id: string; values: string[] }[];    // D83: signs that could differ within it
  };
}

export interface Profile { profile_id: string; expires_at: string; master: Master }

export type CardState = "ready" | "fallback" | "error" | "unavailable";
export interface Section { kind: string; items: string[] }
export interface Entry { ref: string; title: string; text: string; tags?: string[]; source?: string }
export interface InsightCard {
  module_id: string; headline: string; summary: string; detail: string; sections: Section[]; entries?: Entry[];
  badge: "curated" | "ai"; fact_ids: string[]; state: CardState; reason: string | null; degraded: boolean; chart_ref?: string;
  /** D80: one open question to sit with (AI readings only). */
  reflect?: string | null;
}

export interface Place { place_id: string; name: string; admin1: string | null; country: string; lat: number; lon: number; tz: string }
export interface Nearest { place: Place | null; tz: string; distance_km: number | null }
export interface Problem { code: string; message: string; retry_after: number | null; reset_at: string | null; request_id: string;
  options?: { disambiguation: "earlier" | "later"; utc: string }[] }
