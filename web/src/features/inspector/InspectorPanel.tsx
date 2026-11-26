// SPDX-License-Identifier: AGPL-3.0-only
// The Chart Inspector panel (I1): renders what the server sends, in the D81 order. No astrology here.
// Reading (I6) and Ask VEDA (V2) join as tabs later; until then the Snapshot needs no tab bar.
import { Fragment } from "react";
import { Chip, ChipLink, Sheet, Skeleton, type SheetSize } from "../../ui";
import type { Load } from "./api";
import { HOUSE_WORDS, needsTime, titleOf, toSnapshot } from "./model";
import { stepTarget, type InspectTarget } from "./urlState";

export function InspectorPanel({ target, needsTimeOnly = false, note, load, size, onSize, onGo, onClose, onAddTime, onRetry, forceLayout }: {
  target: InspectTarget;
  needsTimeOnly?: boolean;           // a house link on an unknown-time profile (D81 §5): no data, just the reason
  note: "D9_NEEDS_TIME" | null;
  load: Load;
  size: SheetSize;
  onSize(s: SheetSize): void;
  onGo(t: InspectTarget): void;
  onClose(): void;
  onAddTime(): void;
  onRetry(): void;
  forceLayout?: "side" | "bottom";
}) {
  const bundle = load.state === "ready" ? load.data.bundles[`${target.kind}:${target.ref}`] : undefined;
  const signLevel = load.state === "ready" && load.data.level === "sign";
  const name = titleOf(bundle, target.kind, target.ref);
  const prev = stepTarget(target, -1), next = stepTarget(target, 1);
  const label = (t: InspectTarget) => (t.kind === "planet" ? t.ref : `house ${HOUSE_WORDS[t.ref]}`);
  const arrow = (d: string) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d={d} /></svg>;

  return (
    <Sheet open title={name} label="Inspector" size={size} onSize={onSize} onClose={onClose} forceLayout={forceLayout}
      eyebrow={`${target.kind === "planet" ? "Planet" : "House"} · ${signLevel || needsTimeOnly ? "sign level" : target.chart.toUpperCase()}`}
      actions={needsTimeOnly ? undefined : <>
        <button type="button" className="iconbtn" aria-label={`Previous: ${label(prev)}`} onClick={() => onGo(prev)}>{arrow("M15 6l-6 6 6 6")}</button>
        <button type="button" className="iconbtn" aria-label={`Next: ${label(next)}`} onClick={() => onGo(next)}>{arrow("M9 6l6 6-6 6")}</button>
      </>}>
      {needsTimeOnly ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "flex-start" }}>
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "var(--text2)" }}>Houses are counted from the rising sign, which needs your birth time. Without it we would be guessing, so we do not show houses.</p>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onAddTime}>Add a birth time</button>
        </div>
      ) : <>
      {note === "D9_NEEDS_TIME" && <p className="hint" style={{ margin: 0 }}>The D9 needs your birth time, so this is what we can say from the sign alone.</p>}
      {load.state === "loading" || load.state === "idle" ? <Skeleton label={`Loading ${name}`} widths={["90%", "60%", "75%", "40%", "70%"]} heading={false} />
        : load.state === "error" ? (
          <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "flex-start" }}>
            <p style={{ margin: 0, color: "var(--text2)" }}>{load.error.status === 429 ? "Slow down a moment, then try again." : "We could not load this right now."}</p>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>Try again</button>
          </div>
        ) : !bundle ? <p style={{ margin: 0, color: "var(--text2)" }}>This view is not available yet.</p> : (
          <>
            {bundle.summary && <p style={{ margin: 0, fontSize: 16, lineHeight: 1.55, color: "var(--text)" }}>{bundle.summary}</p>}
            {toSnapshot(bundle).map((g) => (
              <Fragment key={g.id}>
                {g.head && <span style={{ font: "600 16px var(--serif)", color: "var(--lav)", borderTop: "1px solid rgba(255,255,255,.10)", paddingTop: 10 }}>{g.head}</span>}
                <section aria-label={g.title} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <span className="eyebrow" style={{ color: "var(--muted)", fontSize: 11 }}>{g.title}</span>
                  {g.chips.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {g.chips.map((ch, i) => ch.target
                        ? <ChipLink key={i} label={ch.aria} onClick={() => onGo(ch.target!)}>{ch.label}</ChipLink>
                        : <Chip key={i}>{ch.label}</Chip>)}
                    </div>
                  )}
                  {g.note && <span style={{ fontSize: 13, lineHeight: 1.5, color: "var(--muted)" }}>{g.note}</span>}
                </section>
              </Fragment>
            ))}
            {signLevel && needsTime(bundle) && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: 14, borderRadius: 16, border: "1px dashed rgba(201,192,255,.45)", background: "rgba(201,192,255,.05)" }}>
                <span className="eyebrow" style={{ color: "var(--lav)", fontSize: 11 }}>Needs your birth time</span>
                <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: "var(--text2)" }}>{needsTime(bundle)}</p>
                <button type="button" className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={onAddTime}>Add a birth time</button>
              </div>
            )}
          </>
        )}
      </>}
    </Sheet>
  );
}
