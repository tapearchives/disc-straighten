"""Reusable cubic coefficients for repeated subpixel samples of one gray plane."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import map_coordinates, spline_filter


class CubicSampler:
    """Match SciPy's order=3, mode='nearest' sampling without refiltering.

    SciPy 1.18 uses 12 edge-padding pixels before its cubic prefilter for
    nearest boundaries. Preserve that convention, including outside samples.
    Only public SciPy APIs are used; tests compare directly with the original
    map_coordinates call so dependency updates cannot silently change it.
    Coefficients belong to this sampler, never a global image cache.
    """

    def __init__(self, plane: np.ndarray):
        self.shape = plane.shape
        self._padding = 12
        self._coefficients = spline_filter(
            np.pad(plane, self._padding, mode='edge'), order=3,
            output=np.float64, mode='nearest')

    def sample(self, coordinates: np.ndarray | list[np.ndarray]) -> np.ndarray:
        return map_coordinates(
            self._coefficients, np.asarray(coordinates, dtype=float)+self._padding,
            order=3, mode='nearest', prefilter=False)
