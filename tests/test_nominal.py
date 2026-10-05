"""Nominal circles, mini discs, and independent interior-geometry controls."""
from __future__ import annotations
import unittest
import numpy as np
from discstraight.cli import measure_geometry, parser
from discstraight.geometry import detect
from discstraight.perspective import boost, detect_perspective, ellipse_points, rectify_concentric, transform
from discstraight.profiles import select_profile
from test_perspective import CAMERA, projected_circle, similarity_errors


def synthetic_disc(camera, ratio):
    y,x = np.mgrid[:680,:720]
    plane = transform(np.column_stack([x.ravel(),y.ravel()]),np.linalg.inv(camera))
    distance = np.linalg.norm(plane,axis=1)
    printing = np.linalg.norm(plane-[4,-3],axis=1)
    gray = 255-6*np.clip(240.5-distance,0,1)-140*np.clip(219.5-printing,0,1)
    return np.where(distance<240*ratio,255,gray).reshape(680,720).astype('uint8')


class NominalGeometryTests(unittest.TestCase):
    def test_exact_profiles_preserve_independent_interior_landmarks(self):
        for diameter in [120,80]:
            with self.subTest(diameter=diameter):
                ratio=15/diameter
                result=rectify_concentric(projected_circle(240),projected_circle(240*ratio),geometry_policy='nominal')
                self.assertEqual(result['disc_profile']['outer_diameter_mm'],diameter)
                self.assertEqual(result['spindle_radius_ratio'],ratio)
                self.assertLess(similarity_errors(CAMERA,result).max(),.001)
                matrix=np.array(result['source_to_plane_matrix'])
                for source,plane in [('model_source_outer_ellipse','plane_outer_circle'),
                                     ('model_source_spindle_ellipse','plane_spindle_circle')]:
                    radii=np.linalg.norm(transform(ellipse_points(result[source]),matrix),axis=1)
                    np.testing.assert_allclose(radii,result[plane]['radius_px'],rtol=0,atol=1e-8)

    def test_noise_is_logged_without_abandoning_exact_output_ratio(self):
        result=rectify_concentric(projected_circle(240,noise=.2),projected_circle(45,noise=.2),geometry_policy='nominal')
        self.assertEqual(result['spindle_radius_ratio'],.1875)
        self.assertGreater(result['nominal_fit']['spindle']['rms_px'],0)
        self.assertLess(similarity_errors(CAMERA,result).max(),.2)

    def test_mini_detection_with_weak_physical_rim_and_shifted_print(self):
        result=detect_perspective(synthetic_disc(CAMERA,.1875),geometry_policy='nominal')
        self.assertEqual(result['rectification']['disc_profile']['outer_diameter_mm'],80)
        self.assertEqual(result['rectification']['spindle_radius_ratio'],.1875)
        self.assertLess(similarity_errors(CAMERA,result['rectification']).max(),.5)
        self.assertTrue(result['needs_rectification'])

    def test_small_scan_stretch_is_corrected_below_old_threshold(self):
        camera=np.array([[1.,0,360],[0,.995,330],[0,0,1.]])
        geometry,perspective,matrix=measure_geometry(synthetic_disc(camera,.1875),parser().parse_args(['input.png']))
        self.assertIsNotNone(matrix)
        self.assertGreater(perspective['source_axis_ratio'],.985)
        self.assertTrue(perspective['applied'])
        self.assertLess(similarity_errors(camera,perspective).max(),.4)
        self.assertAlmostEqual(geometry['spindle_circle']['radius_px']/geometry['outer_circle']['radius_px'],.1875,places=14)

    def test_circular_outer_outline_does_not_disable_projective_correction(self):
        camera=np.array([[240.,0,340],[0,240.,330],[0,0,1.]])@boost(np.array([.08,-.05]))@np.diag([1/240,1/240,1])
        outer=projected_circle(240,camera)
        self.assertAlmostEqual(outer['semiaxes_px'][0]/outer['semiaxes_px'][1],1,places=5)
        result=rectify_concentric(outer,projected_circle(30,camera),geometry_policy='nominal')
        self.assertGreater(result['perspective_strength'],.08)
        self.assertLess(similarity_errors(camera,result).max(),.001)

    def test_face_on_mini_scan_and_forced_wrong_profile(self):
        camera=np.array([[1.,0,360],[0,1.,330],[0,0,1.]])
        gray=synthetic_disc(camera,.1875)
        self.assertEqual(detect(gray)['disc_profile']['outer_diameter_mm'],80)
        with self.assertRaises(ValueError):
            detect(gray,disc_size='120')

    def test_incompatible_dimensions_are_not_silently_normalized(self):
        for ratio in [.05,.155,.26,float('nan')]:
            with self.subTest(ratio=ratio),self.assertRaises(ValueError):
                select_profile(ratio)
        with self.assertRaises(ValueError):
            rectify_concentric(projected_circle(240),projected_circle(45),disc_size='120',geometry_policy='nominal')

    def test_default_offsets_preserve_ratio_and_disabling_requires_measured(self):
        args=parser().parse_args(['input.png'])
        self.assertEqual((args.outer_inset,args.hole_expansion),(0,0))
        self.assertEqual(args.geometry_policy,'nominal')
        for options in [['--perspective','off'],['--outer','150,150,120']]:
            args=parser().parse_args(['input.png',*options])
            with self.assertRaisesRegex(ValueError,'require --geometry-policy measured'):
                measure_geometry(np.full((300,300),255,dtype='uint8'),args)


if __name__=='__main__':
    unittest.main()
