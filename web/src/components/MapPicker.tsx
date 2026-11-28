// SPDX-License-Identifier: AGPL-3.0-only
// Map pin (D64, FR-UI-12a). OpenStreetMap tiles load only after the person agrees (D86): the tile
// server sees their IP address and which area they view, never birth details. The choice lasts for
// this tab only. The nearest town and time zone come from our own server (/v1/places/nearest).
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { api, ApiError } from "../api/client";
import type { Nearest } from "../api/types";
import type { Draft } from "../lib/storage";

const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const CONSENT = "pranix.mapConsent";

function agreedBefore(): boolean {
  try { return sessionStorage.getItem(CONSENT) === "1"; } catch { return false; }
}

export default function MapPicker({ onUse, onCoords, onClose }: {
  onUse(p: NonNullable<Draft["place"]>): void;
  onCoords(lat: number, lon: number): void; // lookup failed: carry on with the pin's exact coordinates
  onClose(): void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.CircleMarker | null>(null);
  const [pin, setPin] = useState<{ lat: number; lon: number } | null>(null);
  const [near, setNear] = useState<Nearest | null>(null);
  const [msg, setMsg] = useState("No point yet. Tap the map, then fine-tune with the arrows.");
  const [failed, setFailed] = useState(false);
  const [agreed, setAgreed] = useState(agreedBefore);

  useEffect(() => {
    if (!agreed || !el.current) return;
    const m = L.map(el.current, { center: [20.5, 78.9], zoom: 4, worldCopyJump: true });
    L.tileLayer(TILES, { maxZoom: 18, attribution: "© OpenStreetMap contributors" }).addTo(m);
    m.on("click", (e: L.LeafletMouseEvent) => place(e.latlng.lat, e.latlng.lng));
    map.current = m;
    return () => { m.remove(); map.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agreed]);

  const place = (lat: number, lon: number) => {
    const p = { lat: Math.round(Math.max(-90, Math.min(90, lat)) * 1e4) / 1e4, lon: Math.round((((lon + 540) % 360) - 180) * 1e4) / 1e4 };
    setPin(p);
    if (map.current) {
      if (!marker.current) marker.current = L.circleMarker([p.lat, p.lon], { radius: 9, color: "#1A1226", weight: 2, fillColor: "#F4C566", fillOpacity: 1 }).addTo(map.current);
      else marker.current.setLatLng([p.lat, p.lon]);
    }
    setFailed(false);
    setMsg("Finding the nearest town…");
    api.nearest(p.lat, p.lon).then((n) => {
      setNear(n);
      const c = `${Math.abs(p.lat).toFixed(4)}° ${p.lat >= 0 ? "N" : "S"}, ${Math.abs(p.lon).toFixed(4)}° ${p.lon >= 0 ? "E" : "W"}`;
      setMsg(n.place ? `${c} · about ${n.distance_km} km from ${n.place.name}, ${[n.place.admin1, n.place.country].filter(Boolean).join(", ")} · time zone ${n.tz}`
        : `${c} · no town within 50 km; we will use these exact coordinates · time zone ${n.tz}`);
    }).catch((e: ApiError) => {
      setNear(null);
      const sea = e.code === "OCEAN_OR_NO_TZ";
      setFailed(!sea);
      setMsg(sea ? "That point is at sea and has no land time zone. Pick a point on land."
        : "We could not name the nearest town just now. You can still use this pin's exact coordinates.");
    });
  };
  const nudge = (dl: number, dn: number) => pin && place(pin.lat + dl, pin.lon + dn);
  const use = () => {
    if (!pin || !near) return;
    onUse({ name: near.place ? `Near ${near.place.name}` : `${pin.lat.toFixed(4)}, ${pin.lon.toFixed(4)}`,
      where: near.place ? `${[near.place.admin1, near.place.country].filter(Boolean).join(", ")} · pin at ${pin.lat.toFixed(4)}, ${pin.lon.toFixed(4)}` : "pinned on the map",
      tz: near.tz, lat: pin.lat, lon: pin.lon });
  };

  const box = { display: "flex", flexDirection: "column" as const, gap: 12, background: "#10102B", border: "1px solid rgba(244,197,102,.5)", borderRadius: 12, padding: 16 };
  if (!agreed) {
    const agree = () => { try { sessionStorage.setItem(CONSENT, "1"); } catch { /* private mode: ask again next time */ } setAgreed(true); };
    return (
      <div style={box} role="region" aria-labelledby="map-consent-title">
        <strong id="map-consent-title" style={{ fontSize: 16, color: "#fff" }}>Load the map from OpenStreetMap?</strong>
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55 }}>
          The map pictures come from OpenStreetMap's servers. To send them, those servers see your IP address and which area you look at.
          They never get your name, birth date or time. Search or coordinates work without the map.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button type="button" className="btn btn-gold btn-sm" onClick={agree}>Load the map</button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Back to search</button>
        </div>
      </div>
    );
  }

  return (
    <div style={box}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 16, color: "#fff" }}>Tap where you were born</strong>
        <span className="hint">Zoom in for accuracy; a nearby spot in the right town is enough.</span>
      </div>
      <div ref={el} style={{ height: 360, borderRadius: 10, overflow: "hidden", border: "1px solid rgba(255,255,255,.15)", cursor: "crosshair" }} aria-label="Map. Search and coordinates are also available." />
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }} role="group" aria-label="Move the pin">
        <span className="hint">Move pin:</span>
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Move pin north" onClick={() => nudge(0.01, 0)}>↑</button>
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Move pin south" onClick={() => nudge(-0.01, 0)}>↓</button>
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Move pin west" onClick={() => nudge(0, -0.01)}>←</button>
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Move pin east" onClick={() => nudge(0, 0.01)}>→</button>
      </div>
      <p role="status" aria-live="polite" style={{ margin: 0, fontSize: 15, lineHeight: 1.55 }}>{msg}</p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {failed && pin
          ? <button type="button" className="btn btn-gold btn-sm" onClick={() => onCoords(pin.lat, pin.lon)}>Use these coordinates</button>
          : <button type="button" className="btn btn-gold btn-sm" aria-disabled={!near} onClick={use}>Use this point</button>}
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Back to search</button>
      </div>
      <span className="hint">Map © OpenStreetMap contributors. Their servers see your IP address and the area you view, never your birth details.</span>
    </div>
  );
}
