// SPDX-License-Identifier: AGPL-3.0-only
// Client pre-checks for the birth form (FR-INP-09), ported from the design (board 2).
// The server stays authoritative; these only save a round trip and give clear messages.
import type { Draft } from "./storage";
import type { BirthRequest } from "../api/client";

export interface FormErrors { name?: string; dob?: string; time?: string; place?: string }
export type DateField = "dd" | "mm" | "yy";
export type TimeField = "hh" | "mi";
/** One group's check: the message, the exact boxes at fault, and whether it is a gap (shown after
 *  submit) or a wrong value (shown as soon as the person leaves the box). */
export interface Check<F extends string> { msg?: string; kind?: "missing" | "invalid"; fields: F[] }

const digits = (v: string) => /^\d+$/.test(v || "");
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const leap = (y: number) => (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
const daysIn = (m: number, y: number) => [31, leap(y) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
const list = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

/** A local calendar date, safe for years below 100 (new Date(50, …) would mean 1950). */
function at(y: number, m: number, d: number): Date {
  const x = new Date(2000, m - 1, d);
  x.setFullYear(y, m - 1, d);
  return x;
}

export function checkDate(s: Draft, today = new Date()): Check<DateField> {
  const parts: [DateField, string, string][] = [["dd", s.dd, "day"], ["mm", s.mm, "month"], ["yy", s.yy, "year"]];
  const empty = parts.filter(([, v]) => !v);
  if (empty.length === 3) return { msg: "Enter the date of birth as day, month and year.", kind: "missing", fields: ["dd", "mm", "yy"] };
  if (empty.length) {
    const what = list(empty.map(([, , w]) => w));
    return { msg: `Add the ${what}.`, kind: "missing", fields: empty.map(([f]) => f) };
  }
  const bad = (msg: string, ...fields: DateField[]): Check<DateField> => ({ msg, kind: "invalid", fields });
  if (!digits(s.dd) || !digits(s.mm) || !digits(s.yy)) return bad("Use numbers only for the day, month and year.", "dd", "mm", "yy");
  const dd = +s.dd, mm = +s.mm, yy = +s.yy;
  if (s.yy.length !== 4) return bad("Enter the year with four digits, for example 1990.", "yy");
  if (mm < 1 || mm > 12) return bad("The month must be between 1 and 12.", "mm");
  if (dd < 1 || dd > 31) return bad("The day must be between 1 and 31.", "dd");
  if (yy < 1800) return bad("We can only calculate charts from 1 January 1800 onwards.", "yy");
  if (dd > daysIn(mm, yy)) {
    const month = mm === 2 ? `February ${yy}` : MONTHS[mm - 1];
    return bad(`${month} has ${daysIn(mm, yy)} days, so the day cannot be ${dd}.`, "dd");
  }
  const t = at(today.getFullYear(), today.getMonth() + 1, today.getDate());
  if (at(yy, mm, dd) > t) return bad("That date is in the future. Please check the year.", "yy");
  if (at(yy + 18, mm, dd) > t) return bad("Pranix can only make charts for people aged 18 or over.", "dd", "mm", "yy");
  return { fields: [] };
}

export function checkTime(s: Draft): Check<TimeField> {
  if (s.timeUnknown) return { fields: [] };
  if (!s.hh && !s.mi) return { msg: 'Enter the birth time, or tick "I do not know the birth time".', kind: "missing", fields: ["hh", "mi"] };
  if (!s.hh) return { msg: "Add the hour.", kind: "missing", fields: ["hh"] };
  if (!s.mi) return { msg: "Add the minutes. On the hour, enter 00.", kind: "missing", fields: ["mi"] };
  const bad = (msg: string, ...fields: TimeField[]): Check<TimeField> => ({ msg, kind: "invalid", fields });
  if (!digits(s.hh) || !digits(s.mi)) return bad("Use numbers only for the hour and minutes.", "hh", "mi");
  const hh = +s.hh, mi = +s.mi;
  const shown = `${String(hh).padStart(2, "0")}:${String(mi).padStart(2, "0")}`;
  // Someone typing a 24-hour time: say exactly what to enter instead of just refusing it.
  if (hh === 0 && mi <= 59) return bad(`Use the 12-hour clock: for ${shown}, enter 12 and choose AM.`, "hh");
  if (hh >= 13 && hh <= 23 && mi <= 59) return bad(`Use the 12-hour clock: for ${shown}, enter ${hh - 12} and choose PM.`, "hh");
  if (hh < 1 || hh > 12) return bad("The hour must be 1 to 12.", "hh");
  if (mi > 59) return bad("The minutes must be 0 to 59.", "mi");
  return { fields: [] };
}

/** "08/12/1984", "8-12-1984", "08.12.1984" (day first, as the form) or "1984-12-08" (year first). */
export function splitDate(text: string): { dd: string; mm: string; yy: string } | null {
  const t = text.trim();
  let m = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/.exec(t);
  if (m) return { dd: m[3], mm: m[2], yy: m[1] };
  m = /^(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{4})$/.exec(t);
  return m ? { dd: m[1], mm: m[2], yy: m[3] } : null;
}

/** "10:35", "10.35", "10:35 pm", "7.05AM". */
export function splitTime(text: string): { hh: string; mi: string; ap?: "AM" | "PM" } | null {
  const m = /^(\d{1,2})[:.](\d{2})\s*([ap])?\.?m?\.?$/i.exec(text.trim());
  if (!m) return null;
  return { hh: m[1], mi: m[2], ...(m[3] ? { ap: m[3].toLowerCase() === "p" ? "PM" as const : "AM" as const } : {}) };
}

export function validate(s: Draft, today = new Date()): FormErrors {
  const e: FormErrors = {};
  if (s.name.trim().length > 40) e.name = "Please use 40 characters or fewer.";
  const dob = checkDate(s, today).msg;
  if (dob) e.dob = dob;
  const time = checkTime(s).msg;
  if (time) e.time = time;
  if (s.manual) {
    const num = /^-?\d+(\.\d+)?$/;
    if (!num.test(s.lat) || !num.test(s.lon)) e.place = "Enter both latitude and longitude as numbers, for example 18.5204 and 73.8567.";
    else if (Math.abs(parseFloat(s.lat)) > 90 || Math.abs(parseFloat(s.lon)) > 180)
      e.place = "Latitude must be between -90 and 90, and longitude between -180 and 180.";
  } else if (!s.place) e.place = "Choose the birthplace from the suggestions, or enter coordinates instead.";
  return e;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** 12-hour form time to the API's local_datetime (unknown time is sent as noon; the server ignores it). */
export function toRequest(s: Draft): BirthRequest {
  let h = 12, m = 0;
  if (!s.timeUnknown) {
    h = parseInt(s.hh, 10) % 12 + (s.ap === "PM" ? 12 : 0);
    m = parseInt(s.mi, 10);
  }
  const local = `${s.yy}-${pad(+s.mm)}-${pad(+s.dd)}T${pad(h)}:${pad(m)}:00`;
  const place = s.manual
    ? { lat: parseFloat(s.lat), lon: parseFloat(s.lon) }
    : s.place?.place_id ? { place_id: s.place.place_id } : { lat: s.place!.lat, lon: s.place!.lon };
  return {
    place, local_datetime: local, birth_time_known: !s.timeUnknown,
    ...(s.timeUnknown ? {} : { time_accuracy: s.acc }),
    ...(s.disambiguation ? { disambiguation: s.disambiguation } : {}),
  };
}
