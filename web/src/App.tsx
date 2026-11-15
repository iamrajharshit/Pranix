// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useState } from "react";
import type { Profile } from "./api/types";
import Dashboard from "./dashboard/Dashboard";
import { useRoute } from "./lib/router";
import { store, type Draft } from "./lib/storage";
import BirthForm from "./screens/BirthForm";
import Entry from "./screens/Entry";
import { HowWeCalculate, Legal } from "./screens/InfoPages";

export default function App() {
  const route = useRoute();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [draft, setDraft] = useState<Draft | null>(store.draft());
  const [offline, setOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const on = () => setOffline(false), off = () => setOffline(true);
    window.addEventListener("online", on); window.addEventListener("offline", off);
    fetch("/healthz").catch(() => {}); // pre-wake a sleeping free server on landing (HOST-05)
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  const onReady = useCallback((p: Profile, d: Draft) => { store.setProfileId(p.profile_id); setDraft(d); setProfile(p); }, []);
  const onProfile = useCallback((p: Profile | null) => { setProfile(p); setDraft(store.draft()); }, []);

  return (
    <>
      {offline && (
        <div role="status" style={{ position: "sticky", top: 0, zIndex: 50, background: "#2A1B3A", borderBottom: "1px solid #FF9D9D", color: "#FFD9D9", padding: "10px 16px", textAlign: "center", fontSize: 14 }}>
          You are offline. Nothing is sent until you reconnect; what you typed is kept.
        </div>
      )}
      {route === "/" && <Entry />}
      {route === "/details" && <BirthForm onReady={onReady} />}
      {route === "/dashboard" && <Dashboard profile={profile} draft={draft} onProfile={onProfile} />}
      {route === "/how" && <HowWeCalculate />}
      {route === "/legal" && <Legal />}
    </>
  );
}
