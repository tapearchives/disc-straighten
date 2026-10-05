"""Ensure the optimization preserves SciPy's subpixel and boundary behavior."""
import unittest

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates

from discstraight.sampling import CubicSampler


class CachedSamplingTests(unittest.TestCase):
    def test_matches_original_at_edges_and_far_outside(self):
        rng = np.random.default_rng(731)
        for shape in [(2,3), (73,103)]:
            plane = gaussian_filter(rng.uniform(0,255,shape), .65)
            coordinates = rng.uniform(-1000,1000,(2,20000))
            coordinates[:,:5000] = rng.uniform(-2,min(shape)+2,(2,5000))
            expected = map_coordinates(plane,coordinates,order=3,mode='nearest')
            np.testing.assert_array_equal(CubicSampler(plane).sample(coordinates),expected)

    def test_repeated_profiles_and_image_lifetime_are_independent(self):
        rng = np.random.default_rng(479)
        plane = rng.uniform(0,255,(80,91))
        coordinates = rng.uniform(0,80,(2,720,25))
        expected = map_coordinates(plane,coordinates,order=3,mode='nearest')
        sampler = CubicSampler(plane)
        plane.fill(0)
        for _ in range(3):
            np.testing.assert_array_equal(sampler.sample(coordinates),expected)
