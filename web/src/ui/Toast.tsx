// SPDX-License-Identifier: AGPL-3.0-only
// A short status message, announced politely and gone after a few seconds.
import { useEffect } from "react";

export function Toast({ text, onDone, ms = 4500 }: { text: string; onDone: () => void; ms?: number }) {
  useEffect(() => { const t = setTimeout(onDone, ms); return () => clearTimeout(t); }, [text, onDone, ms]);
  return <div className="toast" role="status" aria-live="polite">{text}</div>;
}
