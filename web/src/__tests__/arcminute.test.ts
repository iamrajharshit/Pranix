// SPDX-License-Identifier: AGPL-3.0-only
// D86 B1: the server sends degrees truncated to whole arcminutes as minute/60 floats. Floating-point
// drift must never show one minute less (14°07' as 14°06'). Every value 0°00' to 29°59' is checked,
// built the way the server builds it: floor(x * 60) / 60.
import { describe, expect, it } from "vitest";
import { dm } from "../lib/format";

describe("dm() on arcminute values", () => {
  it("shows every one of the 1,800 degree and minute pairs exactly", () => {
    const wrong: string[] = [];
    for (let total = 0; total < 30 * 60; total++) {
      const want = `${Math.floor(total / 60)}°${String(total % 60).padStart(2, "0")}′`;
      // engine values inside the minute and a hair past its start, truncated as the server does
      for (const x of [(total + 0.5) / 60, (total + 1e-6) / 60, (total + 0.999) / 60]) {
        const sent = Math.floor(x * 60) / 60;
        if (dm(sent) !== want) wrong.push(`${total}: ${dm(sent)} != ${want}`);
      }
    }
    expect(wrong).toEqual([]);
  });
});
