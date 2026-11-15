// SPDX-License-Identifier: AGPL-3.0-only
// Original symbolic art (D64): static SVG strings we wrote ourselves, never user content.
import art from "../assets/art.json";

const A = art as { glyphs: Record<string, string>; deities: Record<string, string> };

function sized(svg: string, size: number): string {
  return svg.replace('width="120" height="120"', `width="${size}" height="${size}"`);
}

export function StarGlyph({ name, size = 104 }: { name: string; size?: number }) {
  const svg = A.glyphs[name];
  return svg ? <span aria-hidden="true" dangerouslySetInnerHTML={{ __html: sized(svg, size) }} /> : null;
}

export function DeitySymbol({ name, size = 120 }: { name: string; size?: number }) {
  const svg = A.deities[name.split(" ")[0]];
  return svg ? <span dangerouslySetInnerHTML={{ __html: sized(svg, size) }} /> : null;
}
