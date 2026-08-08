"""
Regression gate for portrait rendering fidelity on real photographs.

Every prior portrait test asserted structure/counts against synthetic
flat-color cartoon fixtures (``tests/fixtures/portrait/gold/``) — none
asked "does the ink land where the photo is dark" or "does any single
pass paint over most of the page". Those are exactly the two defects
that shipped as garbled real-photo output while the whole suite stayed
green: a tone gate that (on the classic path) can favor bright areas
over dark ones, and a facet-fill bug that painted each Cubism region's
*bounding box* instead of its shape (up to ~49% of the page in one pass,
measured against ``tests/fixtures/portrait/photos/armstrong_headshot.jpg``
before the ``restyle_regions_mosaic`` polygon-clip fix).

Thresholds below are calibrated against the actual measured values on the
two real fixtures in this repo (see the docstring in ``fidelity.py`` for
the metric definition), not against a specific person's expectation of
"correct" — they exist to catch the two concrete defects above regressing,
not to certify artistic quality.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from botdraw.core.models import PaperSize, QualityPreset, StyleParams
from botdraw.palettes import load_palette
from botdraw.portrait.fidelity import score_render
from botdraw.portrait.ingest import ingest_portrait
from botdraw.portrait.neural import neural_available
from botdraw.portrait.pens import assign_pens
from botdraw.portrait.restyle import render_from_vector

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "portrait" / "photos"
REAL_PHOTOS = sorted(FIXTURES_DIR.glob("*.jpg"))

# Styles whose ink placement is driven by the tone gate (edges + midtone
# hatch / mesh walks) rather than color-region segmentation.
TONE_SENSITIVE_STYLES = ["portrait_linework", "portrait_pen", "portrait_color_shade"]
# Cubism is the only style whose fill came from the bounding-box bug.
REGION_FILL_STYLE = "portrait_cubism"

MAX_SINGLE_PASS_COVERAGE = 0.35  # old bbox-fill bug measured 0.489 on this fixture set
MIN_TONE_CORR = 0.0  # ink should not be net anti-correlated with photo darkness


def _render(photo: Path, style: str, *, line_source: str, quality: QualityPreset):
    palette = load_palette("default-6")
    pv = ingest_portrait(
        str(photo),
        mode="photo",
        quality=quality,
        paper=PaperSize.A4,
        line_source=line_source,
    )
    pv = assign_pens(pv, palette)
    params = StyleParams(seed=42, quality=quality, density=1.0)
    layered = render_from_vector(style, pv, palette, params)
    return score_render(layered, palette, pv), pv


@pytest.fixture(params=REAL_PHOTOS, ids=[p.stem for p in REAL_PHOTOS])
def real_photo(request) -> Path:
    return request.param


@pytest.mark.parametrize("style", TONE_SENSITIVE_STYLES)
def test_classic_tone_correlation_not_inverted(real_photo: Path, style: str):
    """
    Ink should skew toward the photo's darker areas, not away from them.
    A negative correlation here is the tone-polarity inversion that made
    real-photo output look like it ignores the source image.
    """
    report, _ = _render(real_photo, style, line_source="classic", quality=QualityPreset.BOOTH_BALANCED)
    assert report.tone_corr > MIN_TONE_CORR, (
        f"{style} on {real_photo.name}: tone_corr={report.tone_corr:.3f} "
        "(ink is anti-correlated with photo darkness)"
    )


def test_cubism_facet_fill_does_not_blanket_the_page(real_photo: Path):
    """
    Regression guard for the restyle_regions_mosaic() bounding-box fill bug:
    each facet must be clipped to its polygon, not its bounding box, so no
    single pass paints a large flat rectangle over most of the page.
    """
    report, _ = _render(
        real_photo, REGION_FILL_STYLE, line_source="classic", quality=QualityPreset.STUDIO_HQ
    )
    assert report.max_single_pass_coverage < MAX_SINGLE_PASS_COVERAGE, (
        f"{REGION_FILL_STYLE} on {real_photo.name}: pass '{report.max_single_pass_id}' "
        f"covers {report.max_single_pass_coverage:.1%} of the page"
    )


@pytest.mark.skipif(not neural_available(), reason="neural weights not fetched (botdraw models fetch)")
@pytest.mark.parametrize("style", TONE_SENSITIVE_STYLES)
def test_neural_tone_correlation_at_least_matches_classic(real_photo: Path, style: str):
    """
    The neural line detector should never place ink worse (by this metric)
    than the classic fallback on a real photo — it exists specifically to
    fix the tone-polarity problem the classic path has on real photos.
    """
    classic, _ = _render(real_photo, style, line_source="classic", quality=QualityPreset.BOOTH_BALANCED)
    neural, _ = _render(real_photo, style, line_source="neural", quality=QualityPreset.BOOTH_BALANCED)
    assert neural.tone_corr >= classic.tone_corr - 0.02, (
        f"{style} on {real_photo.name}: neural tone_corr={neural.tone_corr:.3f} "
        f"regressed below classic tone_corr={classic.tone_corr:.3f}"
    )
