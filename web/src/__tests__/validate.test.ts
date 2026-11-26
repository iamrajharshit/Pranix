// SPDX-License-Identifier: AGPL-3.0-only
// Birth form checks, field by field (owner, 26 Nov): say exactly which box is wrong and how to fix it.
import { describe, expect, it } from "vitest";
import { emptyDraft, type Draft } from "../lib/storage";
import { checkDate, checkTime, splitDate, splitTime, validate } from "../lib/validate";

const today = new Date(2026, 10, 15);
const pune = { place_id: "1259229", name: "Pune", where: "Maharashtra, India", tz: "Asia/Kolkata", lat: 18.5196, lon: 73.8553 };
const ok: Draft = { ...emptyDraft, dd: "08", mm: "12", yy: "1984", hh: "12", mi: "20", ap: "AM", place: pune };
const date = (dd: string, mm: string, yy: string) => checkDate({ ...ok, dd, mm, yy }, today);
const time = (hh: string, mi: string, ap: "AM" | "PM" = "AM") => checkTime({ ...ok, hh, mi, ap });

describe("checkDate", () => {
  it("accepts a real date", () => expect(date("08", "12", "1984")).toEqual({ fields: [] }));

  it("names exactly what is missing, and counts as missing (shown only after submit)", () => {
    expect(date("", "", "")).toMatchObject({ kind: "missing", fields: ["dd", "mm", "yy"] });
    expect(date("08", "", "")).toMatchObject({ msg: "Add the month and year.", fields: ["mm", "yy"] });
    expect(date("08", "12", "")).toMatchObject({ msg: "Add the year.", fields: ["yy"] });
  });

  it("points at the one wrong box", () => {
    expect(date("08", "13", "1984")).toMatchObject({ kind: "invalid", fields: ["mm"], msg: expect.stringMatching(/month.*1 and 12/) });
    expect(date("08", "00", "1984").fields).toEqual(["mm"]);
    expect(date("00", "12", "1984")).toMatchObject({ fields: ["dd"], msg: expect.stringMatching(/day.*1 and 31/) });
    expect(date("32", "12", "1984").fields).toEqual(["dd"]);
    expect(date("08", "12", "84")).toMatchObject({ fields: ["yy"], msg: expect.stringMatching(/four digits/) });
  });

  it("knows each month's length, leap years included", () => {
    expect(date("31", "04", "1984").msg).toBe("April has 30 days, so the day cannot be 31.");
    expect(date("29", "02", "1983").msg).toBe("February 1983 has 28 days, so the day cannot be 29.");
    expect(date("29", "02", "1984")).toEqual({ fields: [] }); // leap year
    expect(date("29", "02", "1900").msg).toMatch(/February 1900 has 28 days/); // century rule
    expect(date("29", "02", "2000")).toEqual({ fields: [] });
  });

  it("range, future and age", () => {
    expect(date("01", "01", "1799")).toMatchObject({ fields: ["yy"], msg: expect.stringMatching(/1800/) });
    expect(date("01", "01", "0050").msg).toMatch(/1800/); // not "does not exist": JS Date reads 50 as 1950
    expect(date("01", "01", "2030")).toMatchObject({ fields: ["yy"], msg: expect.stringMatching(/future/) });
    expect(date("16", "11", "2008").msg).toMatch(/18 or over/);
    expect(date("15", "11", "2008")).toEqual({ fields: [] });
  });
});

describe("checkTime", () => {
  it("accepts a 12-hour time", () => {
    expect(time("12", "20")).toEqual({ fields: [] });
    expect(time("9", "5")).toEqual({ fields: [] });
  });
  it("unknown time needs nothing", () => expect(checkTime({ ...ok, hh: "", mi: "", timeUnknown: true })).toEqual({ fields: [] }));
  it("names what is missing", () => {
    expect(time("", "")).toMatchObject({ kind: "missing", fields: ["hh", "mi"] });
    expect(time("10", "")).toMatchObject({ kind: "missing", fields: ["mi"], msg: expect.stringMatching(/minutes/) });
    expect(time("", "30")).toMatchObject({ kind: "missing", fields: ["hh"] });
  });
  it("explains 24-hour input instead of just refusing it", () => {
    expect(time("14", "30")).toMatchObject({ kind: "invalid", fields: ["hh"], msg: "Use the 12-hour clock: for 14:30, enter 2 and choose PM." });
    expect(time("00", "20")).toMatchObject({ fields: ["hh"], msg: "Use the 12-hour clock: for 00:20, enter 12 and choose AM." });
    expect(time("24", "00").msg).toMatch(/1 to 12/);
  });
  it("checks the minutes on their own", () => {
    expect(time("10", "60")).toMatchObject({ kind: "invalid", fields: ["mi"], msg: expect.stringMatching(/0 to 59/) });
  });
});

describe("validate keeps the summary messages", () => {
  it("one message per group", () => {
    const e = validate({ ...ok, mm: "13", hh: "14" }, today);
    expect(e.dob).toMatch(/month/);
    expect(e.time).toMatch(/12-hour/);
  });
});

describe("pasting a whole date or time into one box", () => {
  it("splits common date forms", () => {
    expect(splitDate("08/12/1984")).toEqual({ dd: "08", mm: "12", yy: "1984" });
    expect(splitDate("8-12-1984")).toEqual({ dd: "8", mm: "12", yy: "1984" });
    expect(splitDate("08.12.1984")).toEqual({ dd: "08", mm: "12", yy: "1984" });
    expect(splitDate("1984-12-08")).toEqual({ dd: "08", mm: "12", yy: "1984" }); // year first
    expect(splitDate("08121984")).toBeNull(); // no separators: can't be sure, leave it
    expect(splitDate("hello")).toBeNull();
  });
  it("splits a time, with or without AM/PM", () => {
    expect(splitTime("10:35")).toEqual({ hh: "10", mi: "35" });
    expect(splitTime("10:35 pm")).toEqual({ hh: "10", mi: "35", ap: "PM" });
    expect(splitTime("7.05AM")).toEqual({ hh: "7", mi: "05", ap: "AM" });
    expect(splitTime("1035")).toBeNull();
  });
});
