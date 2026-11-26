// SPDX-License-Identifier: AGPL-3.0-only
// Media-query hook: false where matchMedia is missing (tests, old browsers), so layouts default to desktop.
import { useEffect, useState } from "react";

export function matches(query: string): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}

export function useMediaQuery(query: string): boolean {
  const [on, setOn] = useState(() => matches(query));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(query);
    const update = () => setOn(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [query]);
  return on;
}

/** Phones and narrow tablets get the bottom sheet (plan §17.1). */
export const NARROW = "(max-width: 899px)";
export const reducedMotion = () => matches("(prefers-reduced-motion: reduce)");
