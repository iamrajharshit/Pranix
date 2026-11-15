// SPDX-License-Identifier: AGPL-3.0-only
// Client pre-checks for the birth form (FR-INP-09), ported from the design (board 2).
// The server stays authoritative; these only save a round trip and give clear messages.
import type { Draft } from "./storage";
import type { BirthRequest } from "../api/client";

export interface FormErrors { name?: string; dob?: string; time?: string; place?: string }
const digits = (v: string) => /^\d+$/.test(v || "");

export function validate(s: Draft, today = new Date()): FormErrors {
  const e: FormErrors = {};
  if (s.name.trim().length > 40) e.name = "Please use 40 characters or fewer.";
  const dd = parseInt(s.dd, 10), mm = parseInt(s.mm, 10), yy = parseInt(s.yy, 10);
  if (!digits(s.dd) || !digits(s.mm) || !digits(s.yy)) e.dob = "Enter the full date of birth as day, month and year.";
  else if (String(s.yy).length !== 4) e.dob = "Enter the year with four digits, for example 1990.";
  else if (mm < 1 || mm > 12) e.dob = "The month must be between 1 and 12.";
  else {
    const d = new Date(yy, mm - 1, dd);
    const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    if (dd < 1 || d.getFullYear() !== yy || d.getMonth() !== mm - 1 || d.getDate() !== dd)
      e.dob = "That date does not exist. Please check the day and month.";
    else if (yy < 1800) e.dob = "We can only calculate charts from 1 January 1800 onwards.";
    else if (d > t) e.dob = "That date is in the future. Please check the year.";
    else if (new Date(yy + 18, mm - 1, dd) > t) e.dob = "Pranix can only make charts for people aged 18 or over.";
  }
  if (!s.timeUnknown) {
    if (s.hh === "" && s.mi === "") e.time = 'Enter the birth time, or tick "I do not know the birth time".';
    else if (!digits(s.hh) || !digits(s.mi) || +s.hh < 1 || +s.hh > 12 || +s.mi > 59)
      e.time = "The hour must be 1 to 12 and the minutes 0 to 59.";
  }
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
