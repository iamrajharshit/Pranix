// SPDX-License-Identifier: AGPL-3.0-only
// F4 UI kit: Sheet, Tabs, Chip, URL state, the Inspector link grammar (D81 §5) and the D9 caption fix.
import { act, cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import type { Master } from "../api/types";
import ChartsSection from "../dashboard/ChartsSection";
import sample from "../__fixtures__/sample_1984.json";
import { formatTarget, normaliseTarget, parseTarget, stepTarget, withChart, type InspectTarget } from "../features/inspector/urlState";
import { ChipLink, Sheet, TabPanel, Tabs, afterDrag, useQueryParam, type SheetSize } from "../ui";

afterEach(cleanup);

describe("Inspector link grammar", () => {
  it("parses planets and houses, case-insensitively for planets", () => {
    expect(parseTarget("d1.Jupiter")).toEqual({ chart: "d1", kind: "planet", ref: "Jupiter" });
    expect(parseTarget("d9.jupiter")).toEqual({ chart: "d9", kind: "planet", ref: "Jupiter" });
    expect(parseTarget("d1.h7")).toEqual({ chart: "d1", kind: "house", ref: 7 });
    expect(parseTarget("d9.h12")).toEqual({ chart: "d9", kind: "house", ref: 12 });
  });
  it("ignores anything it does not understand (never throws)", () => {
    for (const bad of [null, undefined, "", "d3.Jupiter", "d1.Pluto", "d1.h0", "d1.h13", "d1.h", "jupiter", "d1.Jupiter.x", "d1.h7x", "<script>"]) {
      expect(parseTarget(bad)).toBeNull();
    }
  });
  it("round-trips", () => {
    for (const s of ["d1.Sun", "d9.Ketu", "d1.h1", "d9.h10"]) expect(formatTarget(parseTarget(s)!)).toBe(s);
  });
  it("falls back on unknown-time profiles (D81 §5)", () => {
    const jup9 = parseTarget("d9.Jupiter")!, jup1 = parseTarget("d1.Jupiter")!, h7 = parseTarget("d1.h7")!;
    expect(normaliseTarget(jup9, true)).toEqual({ target: jup9, note: null });
    expect(normaliseTarget(jup1, false)).toEqual({ target: jup1, note: null });
    expect(normaliseTarget(jup9, false)).toEqual({ target: jup1, note: "D9_NEEDS_TIME" });
    expect(normaliseTarget(h7, false)).toEqual({ target: null, note: "HOUSES_NEED_TIME" });
  });
  it("steps with wrap-around and keeps the target across charts", () => {
    let t: InspectTarget = parseTarget("d1.Sun")!;
    expect(stepTarget(t, -1)).toEqual({ chart: "d1", kind: "planet", ref: "Ketu" });
    for (let i = 0; i < 9; i++) t = stepTarget(t, 1);
    expect(t.ref).toBe("Sun");
    expect(stepTarget(parseTarget("d1.h12")!, 1).ref).toBe(1);
    expect(stepTarget(parseTarget("d1.h1")!, -1).ref).toBe(12);
    expect(withChart(parseTarget("d1.h7")!, "d9")).toEqual({ chart: "d9", kind: "house", ref: 7 });
  });
});

describe("useQueryParam", () => {
  beforeEach(() => window.history.replaceState(null, "", "/dashboard#reading=identity"));
  it("pushes when opening, replaces when changing, and Back closes in one step", () => {
    const push = vi.spyOn(window.history, "pushState"), replace = vi.spyOn(window.history, "replaceState");
    const { result } = renderHook(() => useQueryParam("inspect"));
    expect(result.current[0]).toBeNull();
    act(() => result.current[1]("d1.Jupiter"));
    expect(push).toHaveBeenCalledTimes(1);
    expect(window.location.search).toBe("?inspect=d1.Jupiter");
    expect(window.location.hash).toBe("#reading=identity"); // other URL state survives
    act(() => result.current[1]("d1.Saturn"));
    expect(push).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalled();
    expect(result.current[0]).toBe("d1.Saturn");
    act(() => { window.history.replaceState(null, "", "/dashboard"); window.dispatchEvent(new PopStateEvent("popstate")); });
    expect(result.current[0]).toBeNull();
    push.mockRestore(); replace.mockRestore();
  });
});

describe("Tabs", () => {
  function Harness({ veda = true }: { veda?: boolean }) {
    const [v, setV] = useState<"snapshot" | "reading" | "veda">("snapshot");
    return (
      <>
        <Tabs label="Inspector views" idBase="t" value={v} onChange={setV}
          tabs={[{ id: "snapshot", label: "Snapshot" }, { id: "reading", label: "Reading" }, { id: "veda", label: "Ask VEDA", hidden: !veda }]} />
        <TabPanel idBase="t" id="snapshot" value={v}>snap</TabPanel>
        <TabPanel idBase="t" id="reading" value={v}>read</TabPanel>
      </>
    );
  }
  it("links tabs and panels and uses a roving tabindex", () => {
    render(<Harness />);
    const snap = screen.getByRole("tab", { name: "Snapshot" });
    expect(snap.getAttribute("aria-selected")).toBe("true");
    expect(snap.getAttribute("tabindex")).toBe("0");
    expect(screen.getByRole("tab", { name: "Reading" }).getAttribute("tabindex")).toBe("-1");
    expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe("t-tab-snapshot");
  });
  it("moves with arrows, Home and End, wrapping round", () => {
    render(<Harness />);
    const snap = screen.getByRole("tab", { name: "Snapshot" });
    fireEvent.keyDown(snap, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Ask VEDA" }).getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Ask VEDA" }));
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(screen.getByRole("tabpanel").textContent).toBe("snap");
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Snapshot" }).getAttribute("aria-selected")).toBe("true");
  });
  it("leaves a hidden tab out of the keyboard cycle", () => {
    render(<Harness veda={false} />);
    expect(screen.queryByRole("tab", { name: "Ask VEDA" })).toBeNull();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Snapshot" }), { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Reading" }).getAttribute("aria-selected")).toBe("true");
  });
});

describe("Sheet", () => {
  function Harness({ layout }: { layout: "side" | "bottom" }) {
    const [open, setOpen] = useState(false);
    const [size, setSize] = useState<SheetSize>("half");
    const [title, setTitle] = useState("Jupiter");
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>Open Jupiter</button>
        <Sheet open={open} title={title} eyebrow="Planet · D1" label="Inspector" size={size} onSize={setSize} onClose={() => setOpen(false)} forceLayout={layout}
          actions={<button type="button" onClick={() => setTitle("Saturn")}>Next</button>}>
          <ChipLink label="Inspect Saturn" onClick={() => setTitle("Saturn")}>Saturn</ChipLink>
        </Sheet>
      </>
    );
  }
  it("side panel: non-modal region, focus in on open, Esc closes, focus returns to the opener", () => {
    render(<Harness layout="side" />);
    const opener = screen.getByRole("button", { name: "Open Jupiter" });
    opener.focus(); fireEvent.click(opener);
    const panel = screen.getByRole("region", { name: "Inspector" });
    expect(panel.getAttribute("aria-modal")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Jupiter" }));
    expect(screen.queryByRole("button", { name: "Full" })).toBeNull(); // size buttons only on phones
    fireEvent.keyDown(panel, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Inspector" })).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
  it("a new target chosen inside the panel moves focus to the new title", () => {
    render(<Harness layout="side" />);
    fireEvent.click(screen.getByRole("button", { name: "Open Jupiter" }));
    const chip = screen.getByRole("button", { name: "Inspect Saturn" });
    chip.focus(); fireEvent.click(chip);
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Saturn" }));
  });
  it("bottom sheet: Full/Half buttons and the handle work without dragging (WCAG 2.5.7)", () => {
    render(<Harness layout="bottom" />);
    fireEvent.click(screen.getByRole("button", { name: "Open Jupiter" }));
    expect(screen.getByRole("region", { name: "Inspector" }).className).toContain("half");
    fireEvent.click(screen.getByRole("button", { name: "Full" }));
    const dialog = screen.getByRole("dialog", { name: "Inspector" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.className).toContain("full");
    fireEvent.click(screen.getByRole("button", { name: "Make the panel half height" }));
    expect(screen.getByRole("region", { name: "Inspector" }).className).toContain("half");
  });
  it("full-height phone sheet keeps Tab inside", () => {
    render(<Harness layout="bottom" />);
    fireEvent.click(screen.getByRole("button", { name: "Open Jupiter" }));
    fireEvent.click(screen.getByRole("button", { name: "Full" }));
    const dialog = screen.getByRole("dialog");
    const buttons = Array.from(dialog.querySelectorAll("button"));
    const last = buttons[buttons.length - 1], first = buttons[0];
    last.focus(); fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    first.focus(); fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });
  it("drag rules: up opens full, down steps half then closes, small moves do nothing", () => {
    expect(afterDrag("half", -80)).toBe("full");
    expect(afterDrag("full", 80)).toBe("half");
    expect(afterDrag("half", 80)).toBe("closed");
    expect(afterDrag("half", 20)).toBe("half");
    expect(afterDrag("full", -200)).toBe("full");
  });
});

describe("D9 caption fix", () => {
  const m = sample as unknown as Master;
  const props = { m, profileId: "p", selected: null, setSelected: () => {}, setTab: () => {}, onExpired: () => {}, onAddTime: () => {} };
  it("the D1 tab describes the D1 rising sign", () => {
    render(<ChartsSection {...props} tab="d1" />);
    expect(document.body.textContent).toContain("Rising sign Leo");
    expect(document.body.textContent).not.toContain("D9 rising sign");
  });
  it("the D9 tab describes the D9 chart, not the D1 rising sign", () => {
    render(<ChartsSection {...props} tab="d9" />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("D9 rising sign Libra");
    expect(text).toContain("Within ±2 minutes of your birth time, the D9 rising sign could be Virgo or Libra"); // D83
    expect(text).not.toContain("Rising sign Leo");
  });
  it("D83: a steady D9 says so; an approximate time names every option, and the D1 rising sign too", () => {
    const steady = { ...m, flags: { ...m.flags, minute_sensitive: [] } } as Master;
    render(<ChartsSection {...props} m={steady} tab="d9" />);
    expect(document.body.textContent).toContain("Within ±2 minutes of your birth time, its rising sign stays Libra.");
    cleanup();
    const hour = { ...m, flags: { ...m.flags, minute_window: 60, minute_sensitive: [
      { fact_id: "lagna.sign", values: ["Leo", "Virgo"] },
      { fact_id: "d9.lagna.sign", values: ["Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius"] },
      { fact_id: "d9.moon.sign", values: ["Aries", "Taurus"] },
    ] } } as Master;
    render(<ChartsSection {...props} m={hour} tab="d9" />);
    expect(document.body.textContent).toContain("could be any of 10 signs from Taurus to Aquarius");
    expect(document.body.textContent).toContain("the D9 sign could also change for Moon.");
    cleanup();
    render(<ChartsSection {...props} m={hour} tab="d1" />);
    expect(document.body.textContent).toContain("Within ±60 minutes of your birth time, the rising sign could be Leo or Virgo");
  });
});

describe("North chart proportions (owner, 26 Nov: phone)", () => {
  // point-in-polygon: the house's label anchor and sign number must sit inside the house's own shape
  const inside = ([x, y]: [number, number], poly: [number, number][]) => {
    let hit = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit;
    }
    return hit;
  };
  it("every house keeps its label and its sign number inside it, well apart", async () => {
    const { POS } = await import("../lib/chart");
    const { SHAPES } = await import("../dashboard/NorthChart");
    POS.forEach(([x, y, sx, sy], i) => {
      expect(inside([x, y], SHAPES[i])).toBe(true);
      expect(inside([sx, sy], SHAPES[i])).toBe(true);
      expect(Math.hypot(x - sx, y - sy)).toBeGreaterThanOrEqual(9); // % of the chart: room for a label between
    });
  });
});
