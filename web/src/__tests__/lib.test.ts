// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from "vitest";
import { withName } from "../dashboard/config";
import { layout } from "../lib/chart";
import { dm, span } from "../lib/format";
import { emptyDraft, type Draft } from "../lib/storage";
import { toRequest, validate } from "../lib/validate";

const today = new Date(2026, 10, 15);
const pune = { place_id: "1259229", name: "Pune", where: "Maharashtra, India", tz: "Asia/Kolkata", lat: 18.5196, lon: 73.8553 };
const ok: Draft = { ...emptyDraft, name: "Asha", pronouns: "she_her", dd: "08", mm: "12", yy: "1984", hh: "12", mi: "20", ap: "AM", place: pune };

describe("validate", () => {
  it("accepts a complete form", () => expect(validate(ok, today)).toEqual({}));
  it("flags every empty field", () => {
    const e = validate(emptyDraft, today);
    expect(Object.keys(e).sort()).toEqual(["dob", "place", "time"]);
  });
  it("rejects impossible, future, pre-1800 and under-18 dates", () => {
    expect(validate({ ...ok, dd: "31", mm: "02" }, today).dob).toMatch(/February 1984 has 29 days/);
    expect(validate({ ...ok, yy: "2030" }, today).dob).toMatch(/future/);
    expect(validate({ ...ok, yy: "1799" }, today).dob).toMatch(/1800/);
    expect(validate({ ...ok, dd: "16", mm: "11", yy: "2008" }, today).dob).toMatch(/18 or over/);
    expect(validate({ ...ok, dd: "15", mm: "11", yy: "2008" }, today).dob).toBeUndefined();
  });
  it("needs a 12-hour time unless unknown", () => {
    expect(validate({ ...ok, hh: "13" }, today).time).toBeDefined();
    expect(validate({ ...ok, hh: "", mi: "", timeUnknown: true }, today).time).toBeUndefined();
  });
  it("checks manual coordinates", () => {
    expect(validate({ ...ok, manual: true, lat: "91", lon: "10" }, today).place).toMatch(/between/);
    expect(validate({ ...ok, manual: true, lat: "18.52", lon: "73.85" }, today).place).toBeUndefined();
  });
});

describe("toRequest", () => {
  it("converts 12 AM to midnight and 12 PM to noon", () => {
    expect(toRequest(ok).local_datetime).toBe("1984-12-08T00:20:00");
    expect(toRequest({ ...ok, ap: "PM" }).local_datetime).toBe("1984-12-08T12:20:00");
    expect(toRequest({ ...ok, hh: "7", mi: "5", ap: "PM" }).local_datetime).toBe("1984-12-08T19:05:00");
  });
  it("never sends name or pronouns (rule 10)", () => {
    const body = JSON.stringify(toRequest(ok));
    expect(body).not.toMatch(/Asha|she_her|name|pronoun/);
    expect(toRequest(ok).place).toEqual({ place_id: "1259229" });
  });
  it("drops time accuracy when the time is unknown", () => {
    const r = toRequest({ ...ok, timeUnknown: true });
    expect(r.birth_time_known).toBe(false);
    expect(r).not.toHaveProperty("time_accuracy");
  });
});

describe("dm truncates, never rounds (rule 6)", () => {
  it("cuts to the minute", () => {
    expect(dm(14.4)).toBe("14°24′");
    expect(dm(29.9999)).toBe("29°59′");
    expect(dm(5)).toBe("5°00′");
    expect(dm(22 + 13 / 60)).toBe("22°13′");
    expect(dm(10 - 1e-12)).toBe("9°59′");
  });
});

describe("withName (rule 10)", () => {
  it("adds the name once per card, as a vocative", () => {
    const used = { done: false };
    expect(withName("{{name}}, you lead with warmth.", "Asha", used)).toBe("Asha, you lead with warmth.");
    expect(withName("{{name}}, rest is part of it.", "Asha", used)).toBe("Rest is part of it.");
  });
  it("drops the token without a name", () => expect(withName("{{name}}, you lead.", "")).toBe("You lead."));
});

describe("North Indian layout", () => {
  it("puts the rising sign in house one and walks the zodiac", () => {
    const cells = layout("Leo", [{ id: "Moon", house: 10 }]);
    expect(cells).toHaveLength(12);
    expect(cells[0]).toMatchObject({ house: 1, signNo: 5 });
    expect(cells[8]).toMatchObject({ house: 9, signNo: 1 });
    expect(cells[9].planets).toEqual(["Moon"]);
  });
});

describe("span", () => it("formats a duration", () => expect(span("2016-08-16T00:00:00Z", "2032-08-16T00:00:00Z")).toMatch(/16 y/)));
