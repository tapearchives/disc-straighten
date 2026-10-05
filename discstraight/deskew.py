"""Bounded disc straightness estimation without OCR; analysis pixels only."""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from .imaging import ocr_view


def text_pixels(gray: np.ndarray, center: tuple[float, float], radius: float) -> tuple[np.ndarray, int]:
    """Select small local-contrast components, excluding rims and hub graphics.

    These are text-like marks, not recognized letters. Both polarities count.
    Reject a component crossing the annulus rather than clipping it into a line.
    """
    smooth = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), max(3., radius*.015))
    contrast = gray.astype(np.float32)-smooth
    y, x = np.indices(gray.shape)
    radial = np.hypot(x-center[0], y-center[1])/radius
    interior = (radial > .20) & (radial < .91)
    selected = np.zeros(gray.shape, bool)
    count = 0
    for sign in (-1, 1):
        binary = (sign*contrast > 8).astype(np.uint8)
        _, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
        for label, (left, top, width, height, area) in enumerate(stats[1:], 1):
            if not (8 <= area <= radius**2*.025 and
                    3 <= width <= radius*.27 and 3 <= height <= radius*.27 and
                    max(width, height) <= 6*min(width, height)):
                continue
            region = labels[top:top+height, left:left+width] == label
            if not interior[top:top+height, left:left+width][region].all():
                continue
            selected[top:top+height, left:left+width] |= region
            count += 1
    return selected, count


def estimate(gray: np.ndarray, center: tuple[float, float], radius: float) -> dict:
    """Search clockwise corrections in [-45, 45] by projection sharpness.

    Fractional histogram binning and smoothing reduce pixel-grid angle bias.
    The deterministic pixel budget bounds runtime for unusually busy artwork.
    """
    mask, components = text_pixels(gray, center, radius)
    y, x = np.nonzero(mask)
    pixels = len(x)
    stride = max(1, math.ceil(pixels/60_000))
    x = x[::stride].astype(float)-center[0]
    y = y[::stride].astype(float)-center[1]
    offset = math.ceil(math.hypot(*gray.shape))

    def score(angle: float) -> float:
        radians = math.radians(angle)
        position = x*math.sin(radians)+y*math.cos(radians)+offset
        lower = np.floor(position).astype(int)
        fraction = position-lower
        profile = (np.bincount(lower, weights=1-fraction, minlength=2*offset+2)+
                   np.bincount(lower+1, weights=fraction, minlength=2*offset+2))
        profile = gaussian_filter1d(profile, 1.)
        return float(np.sum(np.diff(profile)**2)/max(1, len(x)))

    result = dict(clockwise_degrees=0., status='review_required',
                  reasons=['ocr_free_upright_direction_unverified'], mixed_directions=False,
                  relative_margin=0., candidates=[], unique_text_regions=[],
                  method='ocr_free_horizontal_projection',
                  search=dict(clockwise_range_degrees=[-45., 45.], coarse_step_degrees=1.,
                              fine_step_degrees=.05, analysis_size_px=list(gray.shape[::-1]),
                              text_like_components=components, selected_pixels=pixels,
                              scored_pixels=len(x), rim_exclusion_radius_fraction=.91,
                              hub_exclusion_radius_fraction=.20),
                  confidence_note='Visual straightness only; cannot read text, identify semantic importance, '
                                  'or resolve upright versus upside-down. Scores are not probabilities.')
    if components < 8 or pixels < 160:
        result['reasons'].append('insufficient_text_like_marks_kept_original_angle')
        return result
    angles = np.arange(-45., 46.)
    scores = np.array([score(a) for a in angles])
    best_index = int(np.argmax(scores))
    coarse = float(angles[best_index])
    fine = np.arange(max(-45., coarse-1), min(45., coarse+1)+.001, .05)
    fine_scores = np.array([score(a) for a in fine])
    angle = float(fine[int(np.argmax(fine_scores))])
    best = float(np.max(fine_scores))
    alternative = float(np.max(scores[abs(angles-angle) >= 10]))
    margin = (best-alternative)/max(best, 1e-12)
    gain = best/max(float(np.median(scores)), 1e-12)
    peaks = set(find_peaks(scores)[0].tolist()) | {0, len(scores)-1, best_index}
    result['candidates'] = sorted([
        dict(clockwise_degrees=float(angles[i]), score=round(float(scores[i]), 6))
        for i in peaks], key=lambda row: -row['score'])[:8]
    result['search'].update(proposed_clockwise_degrees=round(angle, 4),
                            peak_to_median_score=round(gain, 4),
                            alternative_separation_degrees=10.)
    result['relative_margin'] = round(margin, 4)
    result['mixed_directions'] = margin < .5
    if gain < 1.20 or margin < .15:
        result['reasons'].append('ambiguous_straightness_kept_original_angle')
    else:
        result['clockwise_degrees'] = round(angle, 4)
        if abs(angle) >= 44.95:
            result['reasons'].append('straightness_peak_at_search_limit')
    return result


def analyze_visual(source: Path, outer: dict, work: Path, *,
                   rectification_matrix: np.ndarray | None) -> dict:
    """Measure visual alignment independently of whether OCR is available."""
    path = work/'straightness-analysis.png'
    view = ocr_view(source, path, 0., outer['center_px'], outer['radius_px'], rectification_matrix)
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError('Could not read the disc straightness analysis view')
    scale = min(1., 1000/max(gray.shape))
    original_size = gray.shape[1]
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    center = ((gray.shape[1]-1)/2, (gray.shape[0]-1)/2)
    result = estimate(gray, center, outer['radius_px']*view['scale']*gray.shape[1]/original_size)
    result['text_coordinate_space'] = 'rectified_disc_plane' if rectification_matrix is not None else 'normalized_source'
    return result


def orient_without_ocr(source: Path, outer: dict, work: Path, *,
                       rectification_matrix: np.ndarray | None, reason: str,
                       requested_backend: str) -> dict:
    result = analyze_visual(source, outer, work, rectification_matrix=rectification_matrix)
    result['reasons'].insert(0, 'ocr_disabled' if requested_backend == 'none' else 'ocr_unavailable')
    result['ocr'] = dict(engine=None, available=False, requested_backend=requested_backend,
                         fallback_reason=reason, used_for_orientation=False)
    return result
