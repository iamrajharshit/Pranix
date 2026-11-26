// SPDX-License-Identifier: AGPL-3.0-only
// One panel, two shapes (plan §17.1, D81): a side panel on wide screens (non-modal, so the chart stays
// clickable beside it) and a bottom sheet on phones (half or full height). Dragging is optional: Full,
// Half and Close buttons do the same (WCAG 2.5.7). Focus moves to the title on open and back to the
// control that opened it on close; Esc closes; a full-height phone sheet keeps Tab inside it.
import { useEffect, useId, useLayoutEffect, useRef, type PointerEvent, type ReactNode } from "react";
import { useFocusTrap } from "./useFocusTrap";
import { NARROW, useMediaQuery } from "./useMediaQuery";

export type SheetSize = "half" | "full";

export const DRAG_STEP_PX = 64; // a deliberate drag, not a tap

/** Where a drag of `dy` pixels (positive = down) takes the sheet. */
export function afterDrag(size: SheetSize, dy: number): SheetSize | "closed" {
  if (dy <= -DRAG_STEP_PX) return "full";
  if (dy >= DRAG_STEP_PX) return size === "full" ? "half" : "closed";
  return size;
}

export function Sheet({ open, title, eyebrow, label, size, onSize, onClose, actions, children, forceLayout }: {
  open: boolean;
  title: string;
  eyebrow?: string;
  label: string;                     // accessible name of the whole panel, e.g. "Inspector"
  size: SheetSize;
  onSize(size: SheetSize): void;
  onClose(): void;
  actions?: ReactNode;               // header buttons before Close (e.g. Previous / Next)
  children: ReactNode;
  forceLayout?: "side" | "bottom";   // tests and previews; otherwise from the screen width
}) {
  const narrow = useMediaQuery(NARROW);
  const layout = forceLayout ?? (narrow ? "bottom" : "side");
  const root = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const drag = useRef<{ y: number; id: number } | null>(null);
  const titleId = useId();
  const modal = layout === "bottom" && size === "full";

  // Remember who opened the panel, move focus in; give it back on close (plan §17.2).
  useLayoutEffect(() => {
    if (!open) return;
    const active = document.activeElement;
    opener.current = active instanceof HTMLElement && !root.current?.contains(active) ? active : null;
    titleRef.current?.focus({ preventScroll: true });
    return () => {
      const back = opener.current;
      if (back && document.contains(back)) back.focus({ preventScroll: true });
    };
  }, [open]);

  // A new target chosen from inside the panel (a chip, Previous/Next): focus the new title so screen
  // readers announce it. A target chosen on the chart leaves focus on the chart.
  useEffect(() => {
    if (!open) return;
    const a = document.activeElement;
    if (a === null || a === document.body || root.current?.contains(a)) titleRef.current?.focus({ preventScroll: true });
  }, [title, open]);

  useFocusTrap(root, open && modal);

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); onClose(); }
  };
  const down = (e: PointerEvent<HTMLButtonElement>) => {
    drag.current = { y: e.clientY, id: e.pointerId };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const up = (e: PointerEvent<HTMLButtonElement>) => {
    const d = drag.current; drag.current = null;
    if (!d || d.id !== e.pointerId) return;
    const dy = e.clientY - d.y;
    if (Math.abs(dy) < DRAG_STEP_PX) return; // a tap: the click handler toggles
    e.preventDefault();
    const to = afterDrag(size, dy);
    if (to === "closed") onClose(); else onSize(to);
  };
  const toggle = () => onSize(size === "full" ? "half" : "full");

  return (
    <section ref={root} className={`sheet ${layout === "side" ? "sheet-side" : `sheet-bottom ${size}`}`}
      role={modal ? "dialog" : "region"} aria-modal={modal || undefined} aria-label={label}
      onKeyDown={onKeyDown}>
      {layout === "bottom" && (
        <button type="button" className="sheet-handle" aria-label={size === "full" ? "Make the panel half height" : "Make the panel full height"}
          onClick={toggle} onPointerDown={down} onPointerUp={up}><span /></button>
      )}
      <div className="sheet-head">
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
          {eyebrow && <span className="eyebrow" style={{ color: "var(--lav)" }}>{eyebrow}</span>}
          <h2 ref={titleRef} id={titleId} className="sheet-title" tabIndex={-1}>{title}</h2>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {actions}
          {layout === "bottom" && (
            <button type="button" className="iconbtn wide" onClick={toggle}>{size === "full" ? "Half" : "Full"}</button>
          )}
          <button type="button" className="iconbtn" aria-label={`Close ${label.toLowerCase()}`} onClick={onClose}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
      </div>
      <div className="sheet-body">{children}</div>
    </section>
  );
}
