// SPDX-License-Identifier: AGPL-3.0-only
// Chips (plan §4.2, FR-DASH-03): a plain fact, or a link that moves the Inspector to another planet or house.
import type { ReactNode } from "react";

export function Chip({ children }: { children: ReactNode }) {
  return <span className="chip">{children}</span>;
}

export function ChipLink({ children, label, onClick }: { children: ReactNode; label?: string; onClick(): void }) {
  return <button type="button" className="chip chip-link" aria-label={label} onClick={onClick}>{children}</button>;
}
