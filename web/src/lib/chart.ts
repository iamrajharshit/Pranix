// SPDX-License-Identifier: AGPL-3.0-only
// North Indian diamond chart (FR-UI-01): house 1 is the top-centre diamond, houses run anticlockwise.
// Positions are percentages of the square: [house label x, y, sign number x, y] (from the design).
import { SIGNS } from "./format";

export const POS: [number, number, number, number][] = [
  [50, 25, 50, 45], [25, 9, 25, 20], [9, 25, 20, 25], [25, 50, 45, 50], [9, 75, 20, 75], [25, 91, 25, 80],
  [50, 75, 50, 55], [75, 91, 75, 80], [91, 75, 80, 75], [75, 50, 55, 50], [91, 25, 80, 25], [75, 9, 75, 20],
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
