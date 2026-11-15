# SPDX-License-Identifier: AGPL-3.0-only
import pytest

from pranix.cardimg.render import CardImageInput, CardImageUnavailable, CardTextRejected, Renderer
from pranix.config.settings import get_settings

try:
    R: Renderer | None = Renderer(get_settings().fonts_dir)
except CardImageUnavailable:
    R = None
pytestmark = pytest.mark.skipif(R is None, reason="card-image fonts or Cairo not installed")
BASE = CardImageInput(
    "birthstar", "Birth star", "Born under Rohini", "The star of growth.", "#F4C566", star_key="Rohini"
)


def test_deterministic_png() -> None:
    assert R is not None
    a, ha = R.render(BASE)
    b, hb = R.render(BASE)
    assert a == b and ha["ETag"] == hb["ETag"] and a[:4] == b"\x89PNG"


@pytest.mark.parametrize("field", ["headline", "summary", "label"])
def test_rejects_numerals_and_tokens(field: str) -> None:
    assert R is not None
    for bad in ("Born in 1984", "Hello {{name}}"):
        with pytest.raises(CardTextRejected):
            R.render(CardImageInput(**{**BASE.__dict__, field: bad}))
