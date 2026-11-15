# SPDX-License-Identifier: AGPL-3.0-only
"""Server-rendered shareable card image, 1080x1350 PNG (D64, FR-UI-18).

Background, star field and artwork are drawn from SVG with CairoSVG; text is drawn with
Pillow straight from the bundled OFL font files, so output does not depend on the host's
font configuration. Deterministic: the same card gives the same bytes (strong ETag).

Privacy: the input type has no field for a name, pronouns, date, time, place or coordinates,
and any text containing a digit or a template token is rejected.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

W, H, PAD = 1080, 1350, 96
GOLD, TEXT, MUTED = (244, 197, 102), (255, 255, 255), (213, 208, 238)
FONT_FILES = {"serif": "CormorantGaramond-SemiBold.ttf", "sans": "Inter-Regular.ttf", "sans_semi": "Inter-SemiBold.ttf"}


class CardImageUnavailable(RuntimeError):
    """Fonts or the Cairo library are missing on this host."""


class CardTextRejected(ValueError):
    pass


@dataclass(frozen=True)
class CardImageInput:
    module_id: str
    label: str
    headline: str
    summary: str
    accent: str  # "#RRGGBB"
    star_key: str | None = None
    deity_key: str | None = None
    source: str = "curated"  # "curated" | "ai" -> X-Card-Source


@cache
def _art() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(resources.files("pranix.cardimg").joinpath("art.json").read_text("utf-8"))
    return data


def _guard(text: str) -> str:
    if re.search(r"\d", text) or "{" in text or "}" in text:
        raise CardTextRejected("numerals or template tokens are not allowed on card images")
    return text


def _rgb(hex_: str) -> tuple[int, int, int]:
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class Renderer:
    def __init__(self, fonts_dir: str | Path) -> None:
        self.fonts_dir = Path(fonts_dir)
        missing = [f for f in FONT_FILES.values() if not (self.fonts_dir / f).is_file()]
        if missing:
            raise CardImageUnavailable("fonts missing: " + ", ".join(missing))
        try:
            import cairosvg  # noqa: F401  (needs the system Cairo library)
        except (ImportError, OSError) as e:
            raise CardImageUnavailable("Cairo library not available") from e

    def _font(self, kind: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.fonts_dir / FONT_FILES[kind]), size)

    @staticmethod
    def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int, max_lines: int) -> list[str]:
        lines: list[str] = []
        cur = ""
        for word in text.split():
            trial = f"{cur} {word}".strip()
            if font.getlength(trial) <= width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            while font.getlength(lines[-1] + "…") > width and " " in lines[-1]:
                lines[-1] = lines[-1].rsplit(" ", 1)[0]
            lines[-1] += "…"
        return lines

    def _background_svg(self, card: CardImageInput) -> str:
        stars = "".join(
            f'<circle cx="{abs(math.sin(i * 12.9898) * 43758.5453) % 1 * W:.0f}" '
            f'cy="{abs(math.sin(i * 78.233) * 12345.678) % 1 * H:.0f}" r="{1 + i % 3}" fill="#FFF" '
            f'opacity="{0.25 + (i % 5) * 0.12:.2f}"/>'
            for i in range(70)
        )
        art = ""
        svg = _art()["glyphs"].get(card.star_key or "") or _art()["deities"].get(card.deity_key or "")
        if svg:
            inner = svg.split(">", 1)[1].rsplit("</svg>", 1)[0]
            art = f'<g transform="translate({W / 2 - 160},250) scale(2.667)">{inner}</g>'
        else:
            art = (
                f'<circle cx="{W / 2}" cy="410" r="130" fill="url(#orb)"/><circle cx="{W / 2}" cy="410" r="152" '
                f'fill="none" stroke="{card.accent}" stroke-opacity=".35" stroke-dasharray="3 10"/>'
            )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs>'
            f'<radialGradient id="bg" cx="50%" cy="28%" r="80%"><stop offset="0" stop-color="{card.accent}" '
            f'stop-opacity=".30"/><stop offset=".55" stop-color="#0A0A1E"/></radialGradient>'
            f'<radialGradient id="orb"><stop offset="0" stop-color="{card.accent}"/>'
            f'<stop offset="1" stop-color="{card.accent}" stop-opacity="0"/></radialGradient></defs>'
            f'<rect width="{W}" height="{H}" fill="#0A0A1E"/><rect width="{W}" height="{H}" fill="url(#bg)"/>'
            f"{stars}{art}</svg>"
        )

    def render(self, card: CardImageInput) -> tuple[bytes, dict[str, str]]:
        import cairosvg

        label, head, summ = _guard(card.label).upper(), _guard(card.headline), _guard(card.summary)
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", card.accent):
            raise CardTextRejected("bad accent colour")
        bg = cairosvg.svg2png(bytestring=self._background_svg(card).encode(), output_width=W, output_height=H)
        img = Image.open(io.BytesIO(bg)).convert("RGB")
        d = ImageDraw.Draw(img)
        cx = W // 2
        d.text((cx, 190), " ".join(label), font=self._font("sans_semi", 28), fill=_rgb(card.accent), anchor="ms")
        hf, sf = self._font("serif", 76), self._font("sans", 38)
        y = 700
        for line in self._wrap(head, hf, W - 2 * PAD, 3):
            d.text((cx, y), line, font=hf, fill=TEXT, anchor="ms")
            y += 84
        y += 30
        for line in self._wrap(summ, sf, W - 2 * PAD, 6):
            d.text((cx, y), line, font=sf, fill=MUTED, anchor="ms")
            y += 58
        d.text((cx, H - 110), "P R A N I X", font=self._font("serif", 44), fill=GOLD, anchor="ms")
        d.text(
            (cx, H - 66),
            "A symbolic reading for reflection",
            font=self._font("sans", 26),
            fill=(184, 179, 214),
            anchor="ms",
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png = buf.getvalue()
        return png, {
            "Content-Disposition": f'attachment; filename="pranix-{card.module_id}.png"',
            "Cache-Control": "private, max-age=86400",
            "ETag": '"' + hashlib.sha256(png).hexdigest()[:32] + '"',
            "X-Card-Source": card.source,
        }
