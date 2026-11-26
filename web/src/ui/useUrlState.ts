// SPDX-License-Identifier: AGPL-3.0-only
// One query parameter as React state, kept in the address bar (plan §16.3: links reopen a target, Back closes it).
// Opening pushes a history entry; changing the target while open replaces it, so Back always closes in one step.
import { useCallback, useEffect, useState } from "react";

export function readParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

export function writeParam(name: string, value: string | null, mode: "push" | "replace"): void {
  const url = new URL(window.location.href);
  if (value === null) url.searchParams.delete(name); else url.searchParams.set(name, value);
  const next = url.pathname + url.search + url.hash;
  if (next === window.location.pathname + window.location.search + window.location.hash) return;
  if (mode === "push") window.history.pushState(window.history.state, "", next);
  else window.history.replaceState(window.history.state, "", next);
}

export function useQueryParam(name: string): [string | null, (value: string | null) => void] {
  const [value, setValue] = useState<string | null>(() => readParam(name));
  useEffect(() => {
    const on = () => setValue(readParam(name));
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, [name]);
  const set = useCallback((next: string | null) => {
    const current = readParam(name);
    if (next === current) return;
    // closed -> open: a new entry (Back closes); open -> other target or closed: replace (no history pile-up)
    writeParam(name, next, current === null && next !== null ? "push" : "replace");
    setValue(next);
  }, [name]);
  return [value, set];
}
