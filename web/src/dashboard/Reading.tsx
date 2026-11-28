// SPDX-License-Identifier: AGPL-3.0-only
// Full-page reading (FR-DASH-14/15/16): header, in short, detail, per-item blocks, sections,
// chips, how we worked it out, previous/next; Save as image (D64). No network call to open it.
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { InsightCard, Master } from "../api/types";
import { Link } from "../components/Shell";
import { HOW, ORDER, SECTION_DOTS, SECTION_TITLES, withName } from "./config";

export default function Reading({ card, m, profileId, name, readyIds, onClose, onOpen, onChip }: {
  card: InsightCard; m: Master; profileId: string; name: string; readyIds: string[];
  onClose(): void; onOpen(id: string): void; onChip(factId: string): void;
}) {
  const meta = ORDER.find((o) => o.id === card.module_id)!;
  const pos = readyIds.indexOf(card.module_id);
  const prev = pos > 0 ? ORDER.find((o) => o.id === readyIds[pos - 1]) : undefined;
  const next = pos >= 0 && pos < readyIds.length - 1 ? ORDER.find((o) => o.id === readyIds[pos + 1]) : undefined;
  const heading = useRef<HTMLHeadingElement>(null);
  const [img, setImg] = useState(false);
  const stars = useMemo(() => Array.from({ length: 40 }, (_, i) => ({ x: (i * 37) % 100, y: (i * 53) % 100, r: 1 + (i % 3), o: 0.3 + (i % 5) * 0.12, d: (i % 7) * 0.4 })), []);
  useEffect(() => { heading.current?.focus(); }, [card.module_id]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !img) onClose(); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [img, onClose]);

  const used = { done: false }; // one vocative per card, first field that carries the token
  const t = (s: string) => withName(s, name, used);
  const swatch = (ref: string) => m.colors?.swatches.find((s) => s.name === ref);
  return (
    <div className="page" role="region" aria-labelledby="pg-t">
      <div aria-hidden="true" style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
        {stars.map((s, i) => <span key={i} className="star" style={{ left: `${s.x}%`, top: `${s.y}%`, width: s.r, height: s.r, opacity: s.o, animationDelay: `${s.d}s` }} />)}
      </div>
      <div style={{ position: "relative", maxWidth: 880, margin: "0 auto", padding: "24px 32px 96px", display: "flex", flexDirection: "column", gap: 28 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <button type="button" className="navbtn" onClick={onClose}><span aria-hidden="true">←</span> Back to your map</button>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 14, color: "var(--muted)" }}>Card {pos + 1} of {readyIds.length}</span>
            {(card.state === "ready" || card.state === "fallback") && /* a card without content has no image (the server answers 404) */
              <button type="button" className="navbtn" onClick={() => setImg(true)}><span aria-hidden="true">⤓</span> Save as image</button>}
          </div>
        </div>

        <header className="rise" style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 16, paddingTop: 12 }}>
          <svg width="160" height="160" viewBox="0 0 180 180" aria-hidden="true">
            <defs><radialGradient id="hg"><stop offset="0%" stopColor={meta.group.accent} stopOpacity=".9" /><stop offset="60%" stopColor={meta.group.accent} stopOpacity=".18" /><stop offset="100%" stopColor={meta.group.accent} stopOpacity="0" /></radialGradient></defs>
            <circle cx="90" cy="90" r="86" fill="url(#hg)" className="pulse" /><circle cx="90" cy="90" r="22" fill={meta.group.accent} />
          </svg>
          <div className="eyebrow" style={{ color: meta.group.accent }}>Constellation {meta.group.numeral} · {meta.group.title} · {meta.label}</div>
          <h2 id="pg-t" ref={heading} tabIndex={-1} className="h1m" style={{ maxWidth: 760, outline: "none" }}>{t(card.headline)}</h2>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", justifyContent: "center" }}>
            <span className={`badge ${card.badge === "ai" ? "b-ai" : "b-cur"}`}>{card.badge === "ai" ? "AI-phrased" : "Curated"}</span>
            <span style={{ fontSize: 14, color: "var(--muted)" }}>{card.badge === "ai" ? "Worded by AI from your chart facts, then checked by our rules." : "Written from our reviewed library."}</span>
          </div>
        </header>

        <section className="rise" style={{ animationDelay: ".12s", background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.12)", borderRadius: 22, padding: 28 }}>
          <div className="eyebrow" style={{ color: meta.group.accent, marginBottom: 10 }}>In short</div>
          <p style={{ margin: 0, font: "500 24px/1.45 var(--serif)", color: "#fff" }}>{t(card.summary)}</p>
        </section>

        {card.detail && (
          <section className="rise" style={{ animationDelay: ".2s", display: "flex", flexDirection: "column", gap: 12 }}>
            <h3 style={{ margin: 0, font: "600 28px var(--serif)", color: "#fff" }}>{card.badge === "ai" ? "What it means for you" : "What your chart shows"}</h3>
            <p style={{ margin: 0, fontSize: 17, lineHeight: 1.75, color: "var(--text2)" }}>{t(card.detail)}</p>
          </section>
        )}

        {card.entries && card.entries.length > 0 && (
          <section className="rise" style={{ animationDelay: ".24s", display: "flex", flexDirection: "column", gap: 14 }}>
            <h3 style={{ margin: 0, font: "600 28px var(--serif)", color: "#fff" }}>{card.module_id === "colors" ? "Your colours, one by one" : card.module_id === "days" ? "Your days, one by one" : "The four sounds"}</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 16 }}>
              {card.entries.map((e, i) => {
                const sw = swatch(e.ref);
                const mine = e.tags?.includes("yours");
                return (
                  <article key={e.ref} className="rise" style={{ animationDelay: `${0.28 + i * 0.06}s`, display: "flex", flexDirection: "column", gap: 12, background: "rgba(255,255,255,.03)", border: mine ? "2px solid var(--gold)" : "1px solid rgba(255,255,255,.12)", borderRadius: 20, padding: 22 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                      <span aria-hidden="true" style={{ flex: "none", width: 56, height: 56, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", font: "600 17px var(--serif)",
                        background: sw ? sw.hex : mine ? "var(--gold)" : "rgba(255,255,255,.06)", color: mine ? "#1A1226" : "#fff", border: sw?.dark ? "2px solid #D5D0EE" : "none" }}>{sw ? "" : e.title.slice(0, 3)}</span>
                      <strong style={{ font: "600 24px/1.1 var(--serif)", color: "#fff" }}>{e.title}</strong>
                    </div>
                    {e.tags && e.tags.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{e.tags.map((g) => <span key={g} className="badge" style={{ border: "1px solid rgba(244,197,102,.45)", color: "var(--gold-l)", textTransform: "none", letterSpacing: ".02em", fontSize: 12 }}>{g}</span>)}</div>}
                    <p style={{ margin: 0, fontSize: 16, lineHeight: 1.65, color: "var(--text2)" }}>{t(e.text)}</p>
                  </article>
                );
              })}
            </div>
          </section>
        )}

        {card.sections.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 16 }}>
            {card.sections.map((x, i) => (
              <section key={x.kind} className="rise" style={{ animationDelay: `${0.3 + i * 0.06}s`, display: "flex", flexDirection: "column", gap: 10, background: "rgba(255,255,255,.03)", border: "1px solid rgba(255,255,255,.12)", borderTop: `3px solid ${SECTION_DOTS[i % 4]}`, borderRadius: 18, padding: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: SECTION_DOTS[i % 4] }} /><strong style={{ fontSize: 16, color: "#fff" }}>{SECTION_TITLES[x.kind] ?? x.kind}</strong></div>
                {x.items.map((it) => <p key={it} style={{ margin: 0, fontSize: 16, lineHeight: 1.65, color: "var(--text2)" }}>{t(it)}</p>)}
              </section>
            ))}
          </div>
        )}

        {card.reflect && (
          <section className="rise" aria-labelledby="rf-t" style={{ animationDelay: ".44s", display: "flex", flexDirection: "column", gap: 10, alignItems: "center", textAlign: "center", padding: "8px 12px" }}>
            <div id="rf-t" className="eyebrow" style={{ color: meta.group.accent }}>Reflect</div>
            <p style={{ margin: 0, maxWidth: 640, font: "italic 500 22px/1.5 var(--serif)", color: "#fff" }}>{t(card.reflect)}</p>
          </section>
        )}

        <section className="rise" style={{ animationDelay: ".5s", display: "flex", flexDirection: "column", gap: 10 }}>
          <h3 style={{ margin: 0, font: "600 24px var(--serif)", color: "#fff" }}>What this is based on</h3>
          {card.fact_ids.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>{card.fact_ids.filter((f) => m.facts[f]).map((f) => <button key={f} type="button" className="chipbtn" onClick={() => onChip(f)}>{m.facts[f].label}</button>)}</div>}
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.65, color: "var(--muted)" }}>{HOW[card.module_id]} <Link to="/how">How we calculate</Link></p>
        </section>

        <nav aria-label="More readings" className="rise" style={{ animationDelay: ".6s", display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", borderTop: "1px solid rgba(255,255,255,.12)", paddingTop: 20 }}>
          <button type="button" className="navbtn" aria-disabled={!prev} onClick={() => prev && onOpen(prev.id)}><span aria-hidden="true">←</span><span><span style={{ display: "block", fontSize: 12, color: "var(--faint)" }}>Previous</span>{prev?.label ?? "None"}</span></button>
          <button type="button" className="navbtn" aria-disabled={!next} onClick={() => next && onOpen(next.id)}><span><span style={{ display: "block", fontSize: 12, color: "var(--faint)" }}>Next</span>{next?.label ?? "None"}</span><span aria-hidden="true">→</span></button>
        </nav>
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: "var(--faint)" }}>A reflection from traditional Vedic and Ayurvedic ideas, not a prediction or advice.</p>
      </div>
      {img && <SaveImage url={api.cardImageUrl(profileId, card.module_id)} module={card.module_id} onClose={() => { setImg(false); heading.current?.focus(); }} />}
    </div>
  );
}

function SaveImage({ url, module, onClose }: { url: string; module: string; onClose(): void }) {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [note, setNote] = useState("");
  const [why, setWhy] = useState("Card images are not available on this server right now.");
  const title = useRef<HTMLHeadingElement>(null);
  // An <img> can't read the error body, so ask once more for the server's own message. While
  // developing it names what is missing (runbook §6.2); in production it stays generic (D86).
  const failed = () => {
    setState("error");
    fetch(url).then((r) => r.json()).then((p: { message?: string }) => { if (p.message) setWhy(p.message); }).catch(() => {});
  };
  useEffect(() => { title.current?.focus(); }, []);
  const share = async () => {
    try {
      const blob = await (await fetch(url)).blob();
      const file = new File([blob], `pranix-${module}.png`, { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) { await navigator.share({ files: [file], title: "My Pranix card" }); return; }
    } catch { /* fall through to download */ }
    const a = document.createElement("a"); a.href = url; a.download = `pranix-${module}.png`; a.click();
    setNote("Sharing is not available on this device, so we saved the image instead.");
  };
  return (
    <div className="overlay" style={{ paddingTop: 32 }}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="im-t">
        <h2 id="im-t" ref={title} tabIndex={-1} style={{ margin: 0, font: "600 28px var(--serif)", color: "#fff", outline: "none" }}>Save this card as an image</h2>
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "var(--text2)" }}>Our server draws a clean portrait image, sized for phones and stories. It shows this card only. Your name, birth date, time and place are never on it.</p>
        <div style={{ alignSelf: "center", width: "100%", maxWidth: 320, aspectRatio: "4/5", borderRadius: 14, overflow: "hidden", border: "1px solid rgba(255,255,255,.15)", background: "#0A0A1E", display: "flex", alignItems: "center", justifyContent: "center" }}>
          {state !== "error" && <img src={url} alt="Preview of your card image" style={{ width: "100%", height: "100%", objectFit: "cover", display: state === "ok" ? "block" : "none" }} onLoad={() => setState("ok")} onError={failed} />}
          {state === "loading" && <div className="skel" style={{ width: "60%" }} />}
          {state === "error" && <p className="hint" role="status" style={{ padding: 16, textAlign: "center" }}>{why}</p>}
        </div>
        {note && <p role="status" className="hint">{note}</p>}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          <a className="btn btn-gold" href={url} download={`pranix-${module}.png`} aria-disabled={state !== "ok"} onClick={(e) => state !== "ok" && e.preventDefault()}>Download image</a>
          <button type="button" className="btn btn-ghost" disabled={state !== "ok"} onClick={share}>Share…</button>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
