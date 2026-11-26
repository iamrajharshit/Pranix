// SPDX-License-Identifier: AGPL-3.0-only
// Stream group (bug bounty, 26 Nov): retrying a card used to start a second stream and forget the
// first, so nothing closed it. Its cards then landed on the next chart's dashboard (D52 B2).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { streamGroup, type StreamHandlers } from "../api/sse";

class FakeSource {
  static all: FakeSource[] = [];
  closed = false;
  onerror: (() => void) | null = null;
  private on: Record<string, (e: { data: string }) => void> = {};
  constructor(public url: string) { FakeSource.all.push(this); }
  addEventListener(type: string, fn: (e: { data: string }) => void) { this.on[type] = fn; }
  close() { this.closed = true; }
  emit(type: string, data: unknown) { this.on[type]?.({ data: JSON.stringify(data) }); }
}

const handlers = () => {
  const h = { plan: vi.fn(), card: vi.fn(), done: vi.fn(), failed: vi.fn() };
  return h as typeof h & StreamHandlers;
};

beforeEach(() => { FakeSource.all = []; vi.stubGlobal("EventSource", FakeSource); });
afterEach(() => vi.unstubAllGlobals());

describe("streamGroup", () => {
  it("closes every stream it opened, not only the last one", () => {
    const g = streamGroup("chart-a");
    g.start(handlers());
    g.start(handlers(), ["birthstar"]); // a retry while the first stream is still running
    expect(FakeSource.all).toHaveLength(2);
    g.closeAll();
    expect(FakeSource.all.every((s) => s.closed)).toBe(true);
  });

  it("drops anything a closed group's streams still deliver", () => {
    const g = streamGroup("chart-a");
    const h = handlers();
    g.start(h);
    const [main] = FakeSource.all;
    g.closeAll();
    main.emit("insight", { module_id: "identity", chart_ref: "chart-a" });
    main.emit("done", { degraded: false });
    main.onerror?.();
    expect(h.card).not.toHaveBeenCalled();
    expect(h.done).not.toHaveBeenCalled();
    expect(h.failed).not.toHaveBeenCalled();
  });

  it("a finished stream leaves the group, so a long visit does not pile them up", () => {
    const g = streamGroup("chart-a");
    g.start(handlers());
    FakeSource.all[0].emit("done", { degraded: false });
    expect(g.size()).toBe(0);
  });

  it("still ignores events for another chart", () => {
    const g = streamGroup("chart-a");
    const h = handlers();
    g.start(h);
    FakeSource.all[0].emit("insight", { module_id: "identity", chart_ref: "chart-b" });
    expect(h.card).not.toHaveBeenCalled();
  });
});
