"""Recover faint clear-shell lines from a background texture transition.

This supplies four measured lines to the same projective fit. It never creates
an alpha silhouette, invents corners, or estimates lens distortion.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.optimize import least_squares

from .sampling import CubicSampler


def _texture_line(sampler: CubicSampler, a: np.ndarray, b: np.ndarray,
                  band: float) -> dict:
    # Work in the bounded analysis image. The tolerance represents uncertainty
    # in a blurred texture transition, not subpixel certainty in the source.
    t = np.linspace(.06, .94, 200)
    direction = b-a
    normal = np.array([-direction[1], direction[0]])/np.linalg.norm(direction)
    base = a+t[:, None]*direction
    step = .5
    offsets = np.arange(-band, band+step/2, step)
    points = base[:, None]+offsets[None, :, None]*normal
    outside, inside = points-normal, points+normal
    strength = np.maximum(0, (sampler.sample([outside[..., 1], outside[..., 0]])-
                             sampler.sample([inside[..., 1], inside[..., 0]]))/2)
    valid = ((points[..., 0] > 13) & (points[..., 0] < sampler.shape[1]-14) &
             (points[..., 1] > 13) & (points[..., 1] < sampler.shape[0]-14))
    peaks = (strength > np.maximum(.4, strength.max(axis=1, keepdims=True)*.15)) & valid
    peaks[:, 1:-1] &= ((strength[:, 1:-1] > strength[:, :-2]) &
                      (strength[:, 1:-1] >= strength[:, 2:]))
    peaks[:, [0, -1]] = False
    support = cv2.dilate(peaks.astype('uint8'), np.ones((1, 9), np.uint8))
    intercept, slope = np.meshgrid(offsets, offsets)
    hypotheses = intercept.ravel()[:, None]+slope.ravel()[:, None]*(t-.5)
    indices = np.rint((hypotheses+band)/step).astype(int)
    votes = support[np.arange(len(t)), np.clip(indices, 0, len(offsets)-1)]
    votes *= (indices >= 0) & (indices < len(offsets))
    # A corner, guide rail or a few cloth ridges cannot supply an entire side.
    distributed = votes.reshape(-1, 4, 50).mean(axis=-1).min(axis=1) >= .5
    scores = np.where(distributed, votes.mean(axis=1), 0.)
    eligible = np.flatnonzero(scores >= max(.75, float(scores.max())-.06))
    if not len(eligible):
        raise ValueError('No distributed straight texture boundary')
    chosen = eligible[np.argmin(intercept.ravel()[eligible])]
    distances = np.where(peaks, abs(offsets[None]-hypotheses[chosen, :, None]), np.inf)
    rows = np.arange(len(t))
    ids = distances.argmin(axis=1)
    inliers = distances[rows, ids] < 2.5
    values = strength[rows, ids]
    lo = strength[rows, np.maximum(0, ids-1)]
    hi = strength[rows, np.minimum(len(offsets)-1, ids+1)]
    denominator = lo-2*values+hi
    adjustment = np.divide(.5*(lo-hi), denominator, out=np.zeros_like(values),
                           where=abs(denominator) > 1e-8)
    shifts = offsets[ids]+np.clip(adjustment, -.5, .5)*step
    design = np.column_stack([np.ones(len(t)), t-.5])
    fit = least_squares(lambda c: (design@c-shifts)[inliers],
                        np.linalg.lstsq(design[inliers], shifts[inliers], rcond=None)[0],
                        loss='soft_l1', f_scale=.75)
    inliers &= abs(design@fit.x-shifts) < 2.5
    if inliers.mean() < .70 or inliers.reshape(4, 50).mean(axis=1).min() < .5:
        raise ValueError('Texture boundary does not span the shell')
    observed = base+shifts[:, None]*normal
    outer = observed-normal*5
    inner = observed+normal*5
    outer_energy = sampler.sample([outer[:, 1], outer[:, 0]])
    inner_energy = sampler.sample([inner[:, 1], inner[:, 0]])
    extended = observed-normal*12
    extended_energy = sampler.sample([extended[:, 1], extended[:, 0]])
    ratio = float(np.median(outer_energy/np.maximum(inner_energy, .1)))
    fraction = float(np.mean(outer_energy > inner_energy*1.25))
    if (ratio < 1.35 or fraction < .70 or np.median(outer_energy) < 1. or
            np.median(extended_energy) < np.median(outer_energy)*.65):
        raise ValueError('Texture ridge is not a consistent exterior-to-shell transition')
    return dict(points=observed, inliers=inliers, coverage=float(inliers.mean()),
                median_strength=float(np.median(values[inliers])),
                selection='multiscale_texture_boundary_line',
                texture_ratio=ratio, texture_transition_fraction=fraction)


def texture_boundary_traces(gray: np.ndarray, seed: np.ndarray) -> tuple[list[dict], dict]:
    """Accept a complete frame only when two texture scales agree on all sides.

    Call only as a rescue for unreliable luminance lines. The texture may be
    visible through clear material, but should be weaker inside the shell.
    Uniform backgrounds and insufficiently supported edges reject this route.
    """
    from .cassette import intersect, line
    factor = min(1., 900/max(gray.shape))
    q = np.asarray(seed)*factor
    pixels = gray.astype('float32')
    band = max(6., min(gray.shape)*factor*.05)
    groups = []
    for sigma in [.8, 1.2]:
        high = pixels-cv2.GaussianBlur(pixels, (0, 0), sigma/factor)
        energy = np.sqrt(cv2.GaussianBlur(high*high, (0, 0), 2./factor))
        energy = cv2.resize(energy, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        sampler = CubicSampler(energy*4)
        groups.append([_texture_line(sampler, q[i], q[(i+1) % 4], band) for i in range(4)])
    traces, agreements = [], []
    for first, second in zip(*groups):
        a = line(first['points'][first['inliers']])
        b = line(second['points'][second['inliers']])
        # Compare predictions across the measured span, not just at its center.
        p = first['points'][first['inliers']]
        projection = p-(p@a[:2]+a[2])[:, None]*a[:2]
        disagreement = float(np.max(abs(projection@b[:2]+b[2])))
        if disagreement > 2.:
            raise ValueError('Texture scales disagree on a shell side')
        agreements.append(disagreement/factor)
        traces.append(dict(points=np.concatenate([first['points'], second['points']])/factor,
                           inliers=np.concatenate([first['inliers'], second['inliers']]),
                           coverage=min(first['coverage'], second['coverage']),
                           median_strength=min(first['median_strength'], second['median_strength']),
                           gradient_domain='local_texture_energy',
                           selection='multiscale_texture_boundary_line'))
    lines = [line(t['points'][t['inliers']]) for t in traces]
    corners = np.array([intersect(lines[i-1], lines[i]) for i in range(4)])
    if (not cv2.isContourConvex(corners.astype('float32')) or
            np.max(np.linalg.norm(corners-seed, axis=1))*factor > band*1.5 or
            corners.min() < 0 or np.any(corners[:, 0] >= gray.shape[1]) or
            np.any(corners[:, 1] >= gray.shape[0])):
        raise ValueError('Texture rectangle is outside the supported search region')
    return traces, dict(applied=True, method='two_scale_exterior_texture_transition',
                        scale_agreement_source_px=agreements,
                        exterior_to_interior_texture_ratios=[min(a['texture_ratio'], b['texture_ratio'])
                                                            for a, b in zip(*groups)],
                        analysis_scale=factor,
                        note='Four long lines measured from texture attenuation. No pixel alpha key, lens estimate, or corner padding.')
