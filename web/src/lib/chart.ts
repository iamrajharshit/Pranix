// SPDX-License-Identifier: AGPL-3.0-only
// North Indian diamond chart (FR-UI-01): house 1 is the top-centre diamond, houses run anticlockwise.
// Positions are percentages of the square: [house label x, y, sign number x, y] (from the design).
import { SIGNS } from "./format";

// Side triangles (3, 5, 9, 11): labels sit toward the wide base and sign numbers by the inner point, so the
// two never touch on a phone-sized chart; top and bottom triangles (2, 6, 8, 12) likewise.
export const POS: [number, number, number, number][] = [
  [50, 25, 50, 45], [25, 10, 25, 21], [11, 25, 22, 25], [25, 50, 45, 50], [11, 75, 22, 75], [25, 90, 25, 79],
  [50, 75, 50, 55], [75, 90, 75, 79], [89, 75, 78, 75], [75, 50, 55, 50], [89, 25, 78, 25], [75, 10, 75, 21],
];

export interface HouseCell { house: number; signNo: number; x: number; y: number; sx: number; sy: number; planets: string[] }

/** Lay out planets by house for a chart whose first house is `firstSign`. */
export function layout(firstSign: string, planets: { id: string; house: number }[]): HouseCell[] {
  const ref = SIGNS.indexOf(firstSign);
  return POS.map((p, i) => ({
    house: i + 1, signNo: ((ref + i) % 12) + 1, x: p[0], y: p[1], sx: p[2], sy: p[3],
    planets: planets.filter((q) => q.house === i + 1).map((q) => q.id),
  }));
}
