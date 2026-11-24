// SPDX-License-Identifier: AGPL-3.0-only
// Grouping, labels, accents and order are frontend configuration keyed by module_id (§9.1).

export interface Group { id: string; numeral: string; title: string; accent: string; blurb: string; cards: { id: string; label: string }[] }

export const GROUPS: Group[] = [
  { id: "g1", numeral: "I", title: "Who you are", accent: "#F4C566", blurb: "Your rising sign, Moon and Sun, the star you were born under, and its naming syllable.",
    cards: [{ id: "identity", label: "Who you are" }, { id: "birthstar", label: "Birth star" }, { id: "nameletter", label: "Naming syllable" }] },
  { id: "g2", numeral: "II", title: "Your nature", accent: "#6FD6C9", blurb: "The elements, body-mind tendencies and energy centres your chart leans towards.",
    cards: [{ id: "elements", label: "Elemental nature" }, { id: "doshas", label: "Body-mind tendencies" }, { id: "chakras", label: "Energy centres" }] },
  { id: "g3", numeral: "III", title: "Your path", accent: "#A99CFF", blurb: "What drives you, the season of life you are in, and where you can grow.",
    cards: [{ id: "motive", label: "Core motive" }, { id: "season", label: "Life season now" }, { id: "growth", label: "Growth edges" }] },
  { id: "g4", numeral: "IV", title: "Your allies", accent: "#F2A6C0", blurb: "Your deity, colours and days: traditional companions for reflection.",
    cards: [{ id: "deity", label: "Your deity" }, { id: "colors", label: "Power colours" }, { id: "days", label: "Power days" }] },
];

export const ORDER = GROUPS.flatMap((g) => g.cards.map((c) => ({ ...c, group: g })));

export const SECTION_TITLES: Record<string, string> = {
  strengths: "Strengths", watch_points: "Watch points", try_this: "Try this", about_star: "About the star",
  tradition: "The tradition", variant: "Also possible", other_forms: "Other forms", qualities_to_grow: "Qualities to grow",
  practice: "A practice", this_season: "This season", how_to_use: "Ways to use them", ideas_for_the_day: "Ideas for the day",
  how_we_choose: "How we choose",
  growth_edges: "Growth edges", in_daily_life: "In daily life", // D80 structured readings
};
export const SECTION_DOTS = ["#F4C566", "#6FD6C9", "#A99CFF", "#F2A6C0"];

export const HOW: Record<string, string> = {
  identity: "From your rising sign, Moon sign and Sun sign in the sidereal (Lahiri) zodiac.",
  birthstar: "From the nakshatra the Moon occupied at your birth.",
  nameletter: "From the traditional syllable table for your birth star and its quarter.",
  elements: "Our own weighting of planets and signs by element; a heuristic, not a classical measure.",
  doshas: "Our own weighting of planets and signs by dosha; tendencies only, never a diagnosis.",
  chakras: "Each chakra is paired with a planet; its strength comes from that planet's dignity.",
  motive: "From your soul planet (Atmakaraka) and the Rahu-Ketu axis.",
  season: "From the Vimshottari Dasha periods running today.",
  growth: "From quieter energy centres, the Rahu axis and your soul planet's challenge.",
  deity: "Jaimini method: soul planet, its navamsa sign, the twelfth sign from it, and the planet that decides it.",
  colors: "Traditional colours of the planets that guide your chart: rising-sign lord, Moon-sign lord and soul planet.",
  days: "The weekdays of the same guiding planets.",
};

export const PLANET_COLOR: Record<string, string> = {
  Sun: "#F4A300", Moon: "#F5F3EC", Mars: "#D93A3A", Mercury: "#2FA866", Jupiter: "#F5D33B", Venus: "#F2A6C0",
  Saturn: "#4B5BA8", Rahu: "#8B7CF6", Ketu: "#A99CFF",
};
export const ELEMENT_COLOR: Record<string, string> = { Fire: "#F4A300", Earth: "#B7905B", Air: "#9CCBF0", Water: "#6FD6C9", Ether: "#C9C0FF" };
export const DOSHA_COLOR: Record<string, string> = { Vata: "#9CCBF0", Pitta: "#F4A300", Kapha: "#6FD6C9" };

/** Browser-only {{name}} substitution (FR-INS-10); without a name the vocative is removed cleanly. */
/** Browser-only name substitution (rule 10): at most once per card, as a sentence-opening vocative. */
export function withName(text: string, name: string, used = { done: false }): string {
  return text.replace(/\{\{name\}\}, (\w)/g, (_, c: string) => {
    if (name && !used.done) { used.done = true; return `${name}, ${c}`; }
    return c.toUpperCase();
  });
}
