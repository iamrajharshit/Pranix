// SPDX-License-Identifier: AGPL-3.0-only
// Browser-only state (FR-GST-01, ERR-02): the guest's draft (incl. name and pronouns) stays in
// sessionStorage and is never sent to the server except the birth fields needed for the chart.

export interface Draft {
  name: string; pronouns: "none" | "she_her" | "he_him" | "they_them";
  dd: string; mm: string; yy: string; hh: string; mi: string; ap: "AM" | "PM";
  acc: "exact" | "approx_5m" | "approx_30m" | "approx_1h"; timeUnknown: boolean;
  place: { place_id?: string; name: string; where: string; tz: string; lat: number; lon: number } | null;
  manual: boolean; lat: string; lon: string; disambiguation?: "earlier" | "later";
}

export const emptyDraft: Draft = {
  name: "", pronouns: "none", dd: "", mm: "", yy: "", hh: "", mi: "", ap: "AM", acc: "exact", timeUnknown: false,
  place: null, manual: false, lat: "", lon: "",
};

const K = { age: "pranix.age", draft: "pranix.draft", profile: "pranix.profile" };

function get(k: string): string | null { try { return window.sessionStorage.getItem(k); } catch { return null; } }
function set(k: string, v: string | null): void {
  try { if (v === null) window.sessionStorage.removeItem(k); else window.sessionStorage.setItem(k, v); } catch { /* private mode */ }
}

export const store = {
  ageOk: () => get(K.age) === "1",
  setAge: (ok: boolean) => set(K.age, ok ? "1" : null),
  draft: (): Draft | null => { const s = get(K.draft); try { return s ? { ...emptyDraft, ...(JSON.parse(s) as Draft) } : null; } catch { return null; } },
  setDraft: (d: Draft | null) => set(K.draft, d ? JSON.stringify(d) : null),
  profileId: () => get(K.profile),
  setProfileId: (id: string | null) => set(K.profile, id),
};
