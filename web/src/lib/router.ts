// SPDX-License-Identifier: AGPL-3.0-only
// Minimal history router: no dependency needed for six routes.
import { useEffect, useState } from "react";

export type Route = "/" | "/details" | "/dashboard" | "/how" | "/legal";
const ROUTES: Route[] = ["/", "/details", "/dashboard", "/how", "/legal"];

export function currentRoute(): Route {
  const p = window.location.pathname.replace(/\/+$/, "") || "/";
  return (ROUTES as string[]).includes(p) ? (p as Route) : "/";
}

export function navigate(to: string, replace = false): void {
  if (replace) window.history.replaceState(null, "", to);
  else window.history.pushState(null, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
  if (!to.includes("#")) window.scrollTo(0, 0);
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(currentRoute());
  useEffect(() => {
    const on = () => setRoute(currentRoute());
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  return route;
}

export function goBack(fallback: string): void {
  if (window.history.length > 1 && document.referrer.startsWith(window.location.origin)) window.history.back();
  else navigate(fallback);
}
