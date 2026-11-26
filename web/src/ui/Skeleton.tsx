// SPDX-License-Identifier: AGPL-3.0-only
// Loading placeholder in the shape of the final text, so nothing jumps when it arrives (plan §17.1).
export function Skeleton({ label, widths = ["70%", "100%", "92%", "96%", "60%"], heading = true }: { label: string; widths?: string[]; heading?: boolean }) {
  return (
    <div role="status" aria-busy="true" aria-label={label} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {widths.map((w, i) => <div key={i} className="skel" style={{ width: w, height: heading && i === 0 ? 24 : 14 }} />)}
    </div>
  );
}
