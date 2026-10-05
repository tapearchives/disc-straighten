"""Outer silhouette refinement for small cassettes on a uniform backdrop.

Color locates physical reference lines for geometry only. It never creates a
mask or changes output transparency.
"""
from __future__ import annotations

import numpy as np

from .cassette import curve_consensus, geometry_from_traces, plane_to_source, source_to_plane


def sample_color(rgb: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Continuous bilinear analysis without cubic ringing outside faint rims."""
    x = np.clip(points[..., 0], 0, rgb.shape[1]-1)
    y = np.clip(points[..., 1], 0, rgb.shape[0]-1)
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    jx, jy = np.minimum(ix+1, rgb.shape[1]-1), np.minimum(iy+1, rgb.shape[0]-1)
    fx, fy = (x-ix)[..., None], (y-iy)[..., None]
    return ((1-fy)*((1-fx)*rgb[iy, ix]+fx*rgb[iy, jx]) +
            fy*((1-fx)*rgb[jy, ix]+fx*rgb[jy, jx]))


def refine_outer_boundary(rgb: np.ndarray, geometry: dict, *, debow: str) -> dict:
    if debow=='off':
        return geometry
    if min(rgb.shape[:2]) >= 400 or max(rgb.shape[:2]) > 1600:
        return geometry
    height, width = rgb.shape[:2]
    w, h = geometry['plane_size_px']
    yy, xx = np.mgrid[:height, :width]
    plane = source_to_plane(np.stack([xx, yy], -1), geometry)
    exterior = ((plane[..., 0] < -1) | (plane[..., 0] > w+1) |
                (plane[..., 1] < -1) | (plane[..., 1] > h+1))
    colors = rgb[exterior]
    if len(colors) < 100:
        return geometry
    quantized = colors.astype('int32')//8
    keys = quantized @ np.array([1024, 32, 1])
    mode = int(np.bincount(keys).argmax())
    cluster = colors[keys == mode]
    if len(cluster) < len(colors)*.65:
        return geometry
    background = np.median(cluster, axis=0)
    noise = float(np.percentile(np.max(abs(cluster.astype(float)-background), axis=1), 95))
    threshold = max(5., noise+2.)
    t = np.linspace(.06, .94, 220)
    offsets = np.arange(-10., 4.01, .125)
    traces = []
    evidence = []
    for side in range(4):
        bases = [np.stack([t*w, t*0], -1), np.stack([t*0+w, t*h], -1),
                 np.stack([(1-t)*w, t*0+h], -1), np.stack([t*0, (1-t)*h], -1)]
        normal = np.array([[0, 1], [-1, 0], [0, -1], [1, 0]][side])
        points = plane_to_source(bases[side][:, None]+offsets[None, :, None]*normal, geometry)
        valid = ((points[..., 0] >= 0) & (points[..., 0] <= width-1) &
                 (points[..., 1] >= 0) & (points[..., 1] <= height-1))
        values = sample_color(rgb, points)
        contrast = np.max(abs(values-background), axis=-1)
        selected = np.zeros(len(t), bool)
        shifts = np.zeros(len(t))
        strengths = np.zeros(len(t))
        for row in range(len(t)):
            # A measured exterior-to-shell crossing, not a maximum gradient.
            # Persistence rejects isolated JPEG speckles and ringing.
            for j in range(2, len(offsets)-4):
                if not valid[row, j-2:j+5].all():
                    continue
                if (np.max(contrast[row, j-2:j]) <= threshold and
                        np.min(contrast[row, j:j+4]) > threshold):
                    fraction = (threshold-contrast[row, j-1])/(contrast[row, j]-contrast[row, j-1])
                    shifts[row] = offsets[j-1]+.125*fraction
                    strengths[row] = contrast[row, j+3]-contrast[row, j-1]
                    selected[row] = True
                    break
        if selected.mean() < .55:
            return geometry
        try:
            _, inliers = curve_consensus(t, shifts, selected, .8)
        except (ValueError, np.linalg.LinAlgError):
            return geometry
        if inliers.mean() < .5:
            return geometry
        source = plane_to_source(bases[side]+shifts[:, None]*normal, geometry)
        traces.append(dict(points=source, inliers=inliers, coverage=float(inliers.mean()),
                           median_strength=float(np.median(strengths[inliers]))))
        evidence.append(dict(side=['top','right','bottom','left'][side],
                             coverage=float(inliers.mean()),
                             median_offset_from_old_reference_px=float(np.median(shifts[inliers]))))
    corrected = geometry_from_traces(rgb.shape[:2], traces, geometry['detection_score'],
                                     geometry['reel_evidence'], geometry['diagnostics'], debow=debow)
    corrected['outer_boundary'] = dict(method='uniform_exterior_first_contrast_crossing',
                                      background_rgb=background.tolist(), contrast_threshold=threshold,
                                      noise_p95_rgb=noise, exterior_mode_fraction=len(cluster)/len(colors),
                                      edges=evidence,
                                      scope='Geometry estimation only; no color-based alpha or pixel removal.')
    return corrected
