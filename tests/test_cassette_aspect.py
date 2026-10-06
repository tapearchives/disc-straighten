"""A strong inset label cannot replace a supported faint physical shell edge."""
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from discstraight.cassette import intersect,line
from discstraight.cassette_aspect import recover_faint_body_edge


def traces_for(q):
    return [dict(points=np.linspace(q[i],q[(i+1)%4],180),inliers=np.ones(180,dtype=bool),
                 coverage=1.,median_strength=8.) for i in range(4)]


class AspectRecoveryTests(unittest.TestCase):
    def test_faint_top_recovered_from_three_sides_and_nominal_ratio(self):
        photo=np.full((600,900),244,np.uint8)
        cv2.rectangle(photo,(70,55),(830,538),235,-1)
        cv2.rectangle(photo,(100,92),(800,490),90,-1)
        q=np.array([[69.5,91.5],[830.5,91.5],[830.5,538.5],[69.5,538.5]])
        with patch('discstraight.cassette.reel_evidence',return_value={'score':.95}):
            traces,note=recover_faint_body_edge(photo,traces_for(q))
        self.assertTrue(note['applied']);self.assertEqual(note['side'],'top')
        lines=[line(t['points'][t['inliers']]) for t in traces]
        recovered=np.array([intersect(lines[i-1],lines[i]) for i in range(4)])
        np.testing.assert_allclose(recovered[:2,1],54.5,atol=.5)
        np.testing.assert_allclose(recovered[2:],q[2:],atol=1e-6)

    def test_no_boundary_is_invented_on_a_uniform_background(self):
        q=np.array([[70.,90.],[830.,90.],[830.,538.],[70.,538.]])
        with patch('discstraight.cassette.reel_evidence',return_value={'score':.95}):
            _,note=recover_faint_body_edge(np.full((600,900),244,np.uint8),traces_for(q))
        self.assertFalse(note['applied'])

    def test_deep_perspective_does_not_force_raw_photo_to_nominal_ratio(self):
        q=np.array([[180.,90.],[740.,40.],[830.,538.],[70.,538.]])
        _,note=recover_faint_body_edge(np.full((600,900),244,np.uint8),traces_for(q))
        self.assertFalse(note['applied'])
