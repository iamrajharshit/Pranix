// SPDX-License-Identifier: AGPL-3.0-only
// Accessible tabs (WAI-ARIA tabs pattern): roving tabindex, Left/Right/Home/End, panels linked by id.
import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem<T extends string> { id: T; label: string; hidden?: boolean }

export function Tabs<T extends string>({ label, idBase, tabs, value, onChange }: {
  label: string; idBase: string; tabs: TabItem<NoInfer<T>>[]; value: T; onChange(id: NoInfer<T>): void;
}) {
  const shown = tabs.filter((t) => !t.hidden);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const move = (e: KeyboardEvent, i: number) => {
    const last = shown.length - 1;
    const to = e.key === "ArrowRight" ? (i === last ? 0 : i + 1) : e.key === "ArrowLeft" ? (i === 0 ? last : i - 1)
      : e.key === "Home" ? 0 : e.key === "End" ? last : -1;
    if (to < 0) return;
    e.preventDefault();
    onChange(shown[to].id);
    refs.current[shown[to].id]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className="ktabs">
      {shown.map((t, i) => (
        <button key={t.id} ref={(el) => { refs.current[t.id] = el; }} type="button" role="tab" className="ktab"
          id={`${idBase}-tab-${t.id}`} aria-controls={`${idBase}-panel-${t.id}`} aria-selected={t.id === value}
          tabIndex={t.id === value ? 0 : -1} onClick={() => onChange(t.id)} onKeyDown={(e) => move(e, i)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ idBase, id, value, children }: { idBase: string; id: string; value: string; children: ReactNode }) {
  if (id !== value) return null;
  return <div role="tabpanel" id={`${idBase}-panel-${id}`} aria-labelledby={`${idBase}-tab-${id}`} tabIndex={0} style={{ outline: "none" }}>{children}</div>;
}
