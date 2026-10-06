"""Known outer shell boundaries must beat stronger inset molded seams."""
from __future__ import annotations

import unittest

import cv2
import numpy as np

from discstraight.cassette import geometry_from_traces, intersect, line, source_to_plane
from discstraight.cassette_crop import crop_alpha
from discstraight.cassette_texture import texture_boundary_traces


def transparent_shell():
    y, x = np.indices((700, 1050))
    pattern = 18*np.sin(x*1.7)+15*np.cos(y*1.5)
    mask = np.zeros(x.shape, np.uint8)
    cv2.rectangle(mask, (80, 70), (970, 635), 1, -1)
    # Same mean color inside/outside. Only the weave is attenuated by plastic.
    image = (155+pattern*np.where(mask, .15, 1.)).astype('float32')
    cv2.rectangle(image, (92, 83), (958, 622), 210, 3)
    for xx in [337, 714]:
        cv2.circle(image, (xx, 330), 48, 65, -1)
        cv2.circle(image, (xx, 330), 35, 185, -1)
    for xx, yy in [(100, 91), (950, 91), (950, 614), (100, 614)]:
        cv2.circle(image, (xx, yy), 8, 30, 2)
    source = np.array([[79.5, 69.5], [970.5, 69.5], [970.5, 635.5], [79.5, 635.5]], np.float32)
    expected = np.array([[111, 79], [980, 125], [945, 596], [61, 651]], np.float32)
    homography = cv2.getPerspectiveTransform(source, expected)
    photo = cv2.warpPerspective(image, homography, (1050, 720), borderMode=cv2.BORDER_REFLECT)
    seed = cv2.perspectiveTransform(np.array([[[93., 84.], [957., 84.], [957., 621.], [93., 621.]]]), homography)[0]
    return photo, seed, expected, homography


class TextureBoundaryTests(unittest.TestCase):
    def test_perspective_shell_with_stronger_inner_seams_preserves_fasteners(self):
        photo, seed, expected, homography = transparent_shell()
        traces, evidence = texture_boundary_traces(photo, seed)
        lines = [line(t['points'][t['inliers']]) for t in traces]
        corners = np.array([intersect(lines[i-1], lines[i]) for i in range(4)])
        np.testing.assert_allclose(corners, expected, atol=1.5)
        self.assertTrue(evidence['applied'])
        geometry = geometry_from_traces(photo.shape, traces, .8, {}, {}, debow='off')
        w, h = geometry['plane_size_px']
        theta = np.linspace(0, 2*np.pi, 64)
        rivet = np.column_stack([950+9*np.cos(theta), 614+9*np.sin(theta)])
        photographed = cv2.perspectiveTransform(rivet[None], homography)[0]
        mapped = source_to_plane(photographed, geometry)
        # The old inset rectangle intersects this rivet. The recovered frame
        # must contain its entire circumference, not just its center.
        alpha = crop_alpha(mapped[:, 0], mapped[:, 1], dict(bounds_px=[0, 0, w, h]))
        np.testing.assert_array_equal(alpha, np.ones(64))
        self.assertFalse(geometry['lens']['applied'])
        self.assertFalse(geometry['conformance']['applied'])

    def test_uniform_background_does_not_invent_texture_edges(self):
        image = np.full((700, 1050), 155., np.float32)
        cv2.rectangle(image, (92, 83), (958, 622), 210, 3)
        seed = np.array([[93., 84.], [957., 84.], [957., 621.], [93., 621.]])
        with self.assertRaises(ValueError):
            texture_boundary_traces(image, seed)

    def test_one_unsupported_side_rejects_the_complete_frame(self):
        photo, seed, _, _ = transparent_shell()
        photo[:, 915:] = 155.
        with self.assertRaises(ValueError):
            texture_boundary_traces(photo, seed)


if __name__ == '__main__':
    unittest.main()
