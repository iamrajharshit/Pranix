// SPDX-License-Identifier: AGPL-3.0-only
// I1: the Inspector renders what the server sends, in the D81 order. Data comes from the fixtures the
// backend exports (tools/export_contract.py), so both sides test the same bytes.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Master } from "../api/types";
import ChartsSection, { type ChartTab } from "../dashboard/ChartsSection";
import { clearInspectCache, type InspectionSet } from "../features/inspector/api";
import { needsTime, summaryLines, titleOf, toSnapshot } from "../features/inspector/model";
import sample from "../__fixtures__/sample_1984.json";
import unknownSample from "../__fixtures__/sample_1984_unknown_time.json";
import d1 from "../__fixtures__/inspect_1984_d1.json";
import d9 from "../__fixtures__/inspect_1984_d9.json";
import u1 from "../__fixtures__/inspect_1984_unknown_d1.json";

const D1 = d1 as unknown as InspectionSet, D9 = d9 as unknown as InspectionSet, U1 = u1 as unknown as InspectionSet;
const PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"];
const titles = (s: InspectionSet, p: string) => toSnapshot(s.bundles[`planet:${p}`]).map((g) => g.title);

afterEach(() => { cleanup(); clearInspectCache(); vi.restoreAllMocks(); window.history.replaceState(null, "", "/dashboard"); });

describe("toSnapshot (D81 order, data only)", () => {
  it("keeps the D81 order for every planet in both charts, aspects after Sits with", () => {
    for (const p of PLANETS) {
      expect(titles(D1, p)).toEqual(["Placement", "Houses it rules", "Sits with", "Looks at", "Looked at by", "In your D9", "Dispositor chain", "Either side"]);
      expect(titles(D9, p)).toEqual(["Placement", "Houses it rules", "Sits with", "Looks at", "Looked at by", "In your D1", "Dispositor chain", "Either side"]);
    }
  });
  it("aspects (I3): house chips in the table's order, one heading, lookers link to planets", () => {
    const g = toSnapshot(D1.bundles["planet:Mars"]);
    const looks = g.find((x) => x.id === "looks"), by = g.find((x) => x.id === "lookedby");
    expect(looks?.head).toBe("Aspects · drishti");
    expect(looks?.chips.map((c) => c.target?.ref)).toEqual([9, 12, 1]);   // 4th, 7th and 8th from Mars, as the server sent them
    expect(by?.head).toBeUndefined();
    expect(by?.chips.map((c) => c.label)).toEqual(["Rahu"]);
    const sat = toSnapshot(D1.bundles["planet:Saturn"]).find((x) => x.id === "lookedby");
    expect(sat?.chips).toEqual([]);
    expect(sat?.note).toBe("No planet looks at its house.");
  });
  it("houses show who looks at them; an unlooked house says so", () => {
    const twelve = toSnapshot(D1.bundles["house:12"]).find((x) => x.id === "lookedby");
    expect(twelve?.chips.map((c) => c.label)).toEqual(["Mars", "Venus", "Saturn", "Ketu"]);
    const seven = toSnapshot(D1.bundles["house:7"]).find((x) => x.id === "lookedby");
    expect(seven?.note).toBeUndefined();   // I5: the reviewed line replaces the frontend note
    expect(seven?.lines).toEqual(["No planet looks at this house, so its lord and any planets in it speak for it without outside influence."]);
  });
  it("shows Jupiter as the server sent it", () => {
    const g = toSnapshot(D1.bundles["planet:Jupiter"]);
    expect(g[0].chips.map((c) => c.label)).toEqual(["Sagittarius", "House 5", "own sign", "22°21′", "Purva Ashadha"]);
    expect(g[1].note).toBe("5th house, Sagittarius: Mercury and Jupiter · 8th house, Pisces: empty");
    expect(g[2].chips.map((c) => [c.label, c.target?.ref])).toEqual([["Mercury", "Mercury"]]);
    expect(g.find((x) => x.id === "chain")?.note).toBe("Jupiter is its own lord here: a final dispositor.");
  });
  it("names the whole loop and the exchange", () => {
    expect(toSnapshot(D9.bundles["planet:Venus"]).find((g) => g.id === "chain")?.note).toBe("The chain ends in a loop: Venus → Saturn → Mercury → Venus.");
    expect(toSnapshot(D1.bundles["planet:Moon"]).find((g) => g.id === "chain")?.note).toBe("The chain ends in an exchange: Saturn and Venus sit in each other's signs.");
  });
  it("nodes act through their sign lord and carry the node gloss", () => {
    const g = toSnapshot(D1.bundles["planet:Rahu"]);
    expect(g[1].chips.map((c) => c.label)).toEqual(["Venus"]);
    expect(g[0].note).toBe("Shadow node: read through the lord of its sign.");
  });
  it("Vargottama sits in Placement; the bridge says so", () => {
    const g = toSnapshot(D1.bundles["planet:Moon"]);
    expect(g[0].chips.map((c) => c.label)).toContain("Vargottama");
    expect(g.find((x) => x.id === "other")?.note).toBe("Same sign in both charts: vargottama, a steadying signal.");
  });
  it("unknown time: sign level, both stars, nothing time-dependent", () => {
    for (const p of PLANETS) {
      // nodes still "act through" their sign lord: that needs only the sign, not the birth time
      const by = ["Looks at (by sign)", "Looked at by (by sign)"];   // D81 4: the same counts, by sign
      const expected = ["Rahu", "Ketu"].includes(p) ? ["Placement", "Houses it rules", "Same sign", ...by, "Dispositor chain"] : ["Placement", "Same sign", ...by, "Dispositor chain"];
      expect(titles(U1, p)).toEqual(expected);
    }
    const moon = toSnapshot(U1.bundles["planet:Moon"]);
    expect(moon[0].chips.map((c) => c.label)).toEqual(["Taurus", "exalted", "Rohini", "Mrigashira"]);
    expect(moon[0].note).toContain("changes star during that day");
    expect(moon.find((x) => x.id === "looks")?.chips.map((c) => c.label)).toEqual(["Scorpio"]);
    expect(moon.find((x) => x.id === "looks")?.note).toBe("Counted by sign, because houses need a birth time.");
    expect(needsTime(U1.bundles["planet:Moon"])).toBe("House, houses it rules, degree and the D9. Add a birth time to see them.");
    expect(JSON.stringify(moon)).not.toMatch(/House \d|°/);
  });
});

describe("houses (I2)", () => {
  const houses = Array.from({ length: 12 }, (_, i) => i + 1);
  it("every house keeps the D81 house order in both charts", () => {
    for (const h of houses) {
      expect(toSnapshot(D1.bundles[`house:${h}`]).map((g) => g.title)).toEqual(["Occupants", "Its lord", "Looked at by", `House ${h} in your D9`, "Either side"]);
      expect(toSnapshot(D9.bundles[`house:${h}`]).map((g) => g.title)).toEqual(["Occupants", "Its lord", "Looked at by", `House ${h} in your D1`, "Either side"]);
    }
    expect(Object.keys(U1.bundles).some((k) => k.startsWith("house:"))).toBe(false); // no houses without a birth time
  });
  it("an empty house is read through its lord", () => {
    const g = toSnapshot(D1.bundles["house:7"]);
    expect(g[0].chips).toEqual([]);
    expect(g[0].note).toBeUndefined();   // I5: replaced by the approved line
    expect(g[0].lines).toEqual(["An empty house is not an empty part of life: it is read through its lord and the planets that look at it."]);
    expect(g[1].chips.map((c) => c.label)).toEqual(["Saturn", "House 3"]);
    expect(g[1].note).toBe("Saturn rules Aquarius and sits in the 3rd house, in Libra (exalted). In your D9 it sits in the 9th house, in Gemini (friend's sign)."); // I4
    expect(D1.bundles["house:7"].summary).toBe("House seven is Aquarius. It is empty, so it is read through its lord.");
  });
  it("I4: every house names where its lord sits in the other chart", () => {
    for (const h of houses) {
      expect(toSnapshot(D1.bundles[`house:${h}`]).find((g) => g.id === "lord")?.note).toContain("In your D9 it sits in the");
      expect(toSnapshot(D9.bundles[`house:${h}`]).find((g) => g.id === "lord")?.note).toContain("In your D1 it sits in the");
    }
  });
  it("D83: the panel shows the server's birth-minute note, calmly, on every target of the set", async () => {
    expect(D1.minute_window).toBe(2);
    expect(D1.minute_note).toBe("Within your birth time's margin, your D9 rising sign could be Virgo or Libra, which would move the D9 houses.");
    expect(U1.minute_note).toBeNull();   // no birth time: nothing to check within a margin
  });
  it("I5: approved library lines sit under the group they explain", () => {
    const ju = toSnapshot(D1.bundles["planet:Jupiter"]);
    expect(summaryLines(D1.bundles["planet:Jupiter"])[0]).toMatch(/^Jupiter in the fifth house brings wisdom/);
    expect(ju.find((x) => x.id === "placement")?.lines?.[0]).toMatch(/^Own sign:/);
    expect(ju.find((x) => x.id === "chain")?.lines?.[0]).toMatch(/^Final dispositor:/);
    expect(ju.find((x) => x.id === "other")?.lines?.[0]).toMatch(/^It has less dignity in the D9/);
    const lord = toSnapshot(D1.bundles["house:7"]).find((x) => x.id === "lord");
    expect(lord?.note).toContain("Saturn rules Aquarius");          // the facts stay
    expect(lord?.lines?.[0]).toMatch(/^With the lord of the seventh house in the third/);
    expect(D1.bundles["house:7"].about?.arena).toMatch(/^The seventh house is partnership/);
    for (const h of houses) expect(D9.bundles[`house:${h}`].about).toBeTruthy();
    expect(Object.values(U1.bundles).every((b) => summaryLines(b).length === 0)).toBe(true); // no houses without a birth time
  });
  it("titles use words; house chips link to houses", () => {
    expect(titleOf(D1.bundles["house:1"], "house", 1)).toBe("House one · Leo");
    expect(titleOf(undefined, "house", 12)).toBe("House twelve");
    const place = toSnapshot(D1.bundles["planet:Jupiter"])[0].chips.find((c) => c.label === "House 5");
    expect(place?.target).toEqual({ chart: "d1", kind: "house", ref: 5 });
  });
});

describe("ChartsSection with the Inspector on", () => {
  const sets: Record<string, InspectionSet> = { d1: D1, d9: D9 };
  let calls: string[] = [];
  beforeEach(() => {
    calls = [];
    window.history.replaceState(null, "", "/dashboard");
    vi.spyOn(window, "fetch").mockImplementation(async (url) => {
      const u = String(url); calls.push(u);
      if (u.includes("/dasha")) return new Response("[]", { status: 200, headers: { "content-type": "application/json" } });
      const chart = u.endsWith("/d9") ? "d9" : "d1";
      const set = (u.includes("unknown") ? U1 : sets[chart]);
      return new Response(JSON.stringify(set), { status: 200, headers: { etag: `"${chart}"`, "content-type": "application/json" } });
    });
  });
  function Harness({ m = sample as unknown as Master, id = "p1" }: { m?: Master; id?: string }) {
    const [tab, setTab] = useState<ChartTab>("d1");
    return <ChartsSection m={m} profileId={id} tab={tab} setTab={setTab} selected={null} setSelected={() => {}} onExpired={() => {}} onAddTime={() => {}} inspect />;
  }
  it("clicking a planet opens the Inspector with the server's summary; Close returns focus", async () => {
    render(<Harness />);
    const ju = screen.getByRole("button", { name: /^Jupiter in Sagittarius/ });
    ju.focus(); fireEvent.click(ju);
    expect(window.location.search).toBe("?inspect=d1.Jupiter");
    expect(await screen.findByText("Jupiter in your fifth house, in Sagittarius, its own sign.")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Inspector" })).toBeTruthy();
    expect(screen.getByRole("note").textContent).toContain("your D9 rising sign could be Virgo or Libra"); // D83
    fireEvent.click(screen.getByRole("button", { name: "Close inspector" }));
    expect(window.location.search).toBe("");
    expect(document.activeElement).toBe(ju);
  });
  it("chips, Next and the D1/D9 switch move the target; D9 keeps it", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: /^Jupiter in Sagittarius/ }));
    await screen.findByText("Jupiter in your fifth house, in Sagittarius, its own sign.");
    fireEvent.click(screen.getByRole("button", { name: "Inspect Mercury" }));
    expect(window.location.search).toBe("?inspect=d1.Mercury");
    fireEvent.click(screen.getByRole("button", { name: "Next: Jupiter" }));
    expect(window.location.search).toBe("?inspect=d1.Jupiter");
    fireEvent.click(screen.getByRole("tab", { name: "D9 · Navamsa" }));
    expect(window.location.search).toBe("?inspect=d9.Jupiter");
    expect(await screen.findByText("Jupiter in your first house, in Libra, an enemy's sign.")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Dasha timeline" }));
    expect(window.location.search).toBe("");
  });
  it("a deep link opens directly; a bad link is ignored; the set is fetched once per chart", async () => {
    window.history.replaceState(null, "", "/dashboard?inspect=d1.Saturn");
    const { unmount } = render(<Harness />);
    expect(await screen.findByText("Saturn in your third house, in Libra, where it is exalted.")).toBeTruthy();
    expect(calls.filter((u) => u.endsWith("/inspect/d1")).length).toBe(1); // prefetch and the panel share one request
    unmount();
    window.history.replaceState(null, "", "/dashboard?inspect=d1.Pluto");
    render(<Harness />);
    expect(screen.queryByRole("region", { name: "Inspector" })).toBeNull();
  });
  it("unknown time: a D9 link falls back to the sign-level view (D81 §5)", async () => {
    window.history.replaceState(null, "", "/dashboard?inspect=d9.Moon");
    render(<Harness m={unknownSample as unknown as Master} id="unknown" />);
    expect(await screen.findByText("Moon in Taurus, where it is exalted.")).toBeTruthy();
    expect(screen.getByText(/The D9 needs your birth time/)).toBeTruthy();
    expect(screen.getByText(/Add a birth time to see them/)).toBeTruthy();
    expect(calls.every((u) => !u.endsWith("/d9"))).toBe(true);
  });
  it("shows Try again on an error and recovers", async () => {
    vi.mocked(window.fetch).mockImplementationOnce(async () => new Response("{}", { status: 503 }));
    window.history.replaceState(null, "", "/dashboard?inspect=d1.Sun");
    render(<Harness />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByText("Sun in your fourth house, in Scorpio, a friend's sign.")).toBeTruthy());
  });
  it("houses are buttons: open, chip into a planet, Next wraps from twelve to one", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "House seven, Aquarius, empty" }));
    expect(window.location.search).toBe("?inspect=d1.h7");
    expect(await screen.findByText("House seven is Aquarius. It is empty, so it is read through its lord.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "House seven · Aquarius" })).toBeTruthy();
    expect(screen.getByLabelText("About this house").textContent).toMatch(/^The seventh house is partnership/); // I5
    fireEvent.click(screen.getByRole("button", { name: "Inspect Saturn" }));
    expect(window.location.search).toBe("?inspect=d1.Saturn");
    fireEvent.click(screen.getByRole("button", { name: "Inspect house three" }));
    expect(window.location.search).toBe("?inspect=d1.h3");
    window.history.replaceState(null, "", "/dashboard?inspect=d1.h12");
    window.dispatchEvent(new PopStateEvent("popstate"));
    fireEvent.click(await screen.findByRole("button", { name: "Next: house one" }));
    expect(window.location.search).toBe("?inspect=d1.h1");
    expect(await screen.findByText("Your rising sign. House one is Leo. It is empty, so it is read through its lord and the planets that look at it.")).toBeTruthy();
  });
  it("a selected planet outlines the houses it looks at, and the house buttons say so", async () => {
    const { container } = render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: /^Mars in/ }));
    await screen.findByText(/^Mars in your/);
    await waitFor(() => expect(container.querySelectorAll("svg .aspect").length).toBe(3));
    expect(screen.getByRole("button", { name: /^House nine, .*Mars looks at it$/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "House seven, Aquarius, empty" }));  // a house target: no outlines
    await waitFor(() => expect(container.querySelectorAll("svg .aspect").length).toBe(0));
  });
  it("unknown time: a house link explains that houses need the birth time", async () => {
    window.history.replaceState(null, "", "/dashboard?inspect=d1.h7");
    render(<Harness m={unknownSample as unknown as Master} id="unknown" />);
    expect(await screen.findByText(/Houses are counted from the rising sign/)).toBeTruthy();
    const panel = screen.getByRole("region", { name: "Inspector" });
    expect(within(panel).getByRole("button", { name: "Add a birth time" })).toBeTruthy();
    expect(within(panel).queryByRole("button", { name: /^Next/ })).toBeNull();
  });
});
