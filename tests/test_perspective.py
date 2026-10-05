"""Independent known-camera controls, including interior geometry and raster pixels."""
from __future__ import annotations

import math
from pathlib import Path
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from discstraight.cli import measure_geometry, parser
from discstraight.imaging import render, run
from discstraight.perspective import (boost, detect_perspective, ellipse_points,
                                     rectify_concentric, transform)

CAMERA = np.array([[1.04,.17,330],[-.11,.72,310],[.0004,-.0007,1.]])


def projected_circle(radius, camera=CAMERA, noise=0):
    points = ellipse_points(dict(center_px=[0,0],semiaxes_px=[radius,radius],angle_radians=0))
    points = transform(points,camera)
    points += np.random.default_rng(802).normal(0,noise,points.shape)
    center,axes,angle = cv2.fitEllipse(points.astype('float32'))
    return dict(center_px=list(center),semiaxes_px=(np.array(axes)/2).tolist(),
                angle_radians=math.radians(angle))


def similarity_errors(camera, rectification):
    # These interior points were NOT involved in fitting either boundary.
    grid = np.array([[x,y] for x in range(-140,141,35) for y in range(-140,141,35)])
    reconstructed = transform(transform(grid,camera),np.array(rectification['source_to_plane_matrix']))
    a,b = grid-grid.mean(axis=0),reconstructed-reconstructed.mean(axis=0)
    u,_,vt = np.linalg.svd(a.T@b)
    rotation = u@vt
    scale = np.sum((a@rotation)*b)/np.sum(a*a)
    return np.linalg.norm(a@rotation*scale-b,axis=1)


class PerspectiveGeometryTests(unittest.TestCase):
    def test_recovers_interior_metric_geometry_not_only_round_outline(self):
        for camera in [CAMERA,np.array([[.62,.05,360],[.14,.94,310],[.00075,.00015,1.]])]:
            rectification = rectify_concentric(projected_circle(240,camera),projected_circle(30,camera))
            self.assertLess(similarity_errors(camera,rectification).max(),.001)
            np.testing.assert_allclose(rectification['projected_physical_center_px'],camera[:2,2],atol=.001)
            self.assertAlmostEqual(rectification['spindle_radius_ratio'],.125,places=6)

    def test_noisy_subpixel_boundary_samples_preserve_interior(self):
        rectification = rectify_concentric(projected_circle(240,noise=.2),projected_circle(30,noise=.2))
        self.assertLess(similarity_errors(CAMERA,rectification).max(),.15)

    def test_angled_weak_rim_survives_shifted_high_contrast_print(self):
        y,x = np.mgrid[:680,:720]
        plane = transform(np.column_stack([x.ravel(),y.ravel()]),np.linalg.inv(CAMERA))
        distance = np.linalg.norm(plane,axis=1)
        printing = np.linalg.norm(plane-[4,-3],axis=1)
        gray = 255-6*np.clip(240.5-distance,0,1)-140*np.clip(219.5-printing,0,1)
        gray = np.where(distance<30,255,gray).reshape(680,720).astype('uint8')
        result = detect_perspective(gray)
        expected = projected_circle(240)
        np.testing.assert_allclose(result['outer_ellipse']['center_px'],expected['center_px'],atol=.7)
        np.testing.assert_allclose(result['outer_ellipse']['semiaxes_px'],expected['semiaxes_px'],atol=.7)
        self.assertLess(similarity_errors(CAMERA,result['rectification']).max(),.4)
        self.assertTrue(result['needs_rectification'])

    def test_rejects_wrong_aperture_size_and_nonconcentric_conics(self):
        outer = projected_circle(240)
        with self.assertRaises(ValueError):
            rectify_concentric(outer,projected_circle(48),disc_size='120')
        hole = projected_circle(30)
        hole['semiaxes_px'][0] *= .6
        with self.assertRaises(ValueError):
            rectify_concentric(outer,hole)

    def test_unstable_projective_horizon_refused(self):
        with self.assertRaises(ValueError):
            boost(np.array([.9,0]))
        with self.assertRaises(ValueError):
            transform(np.array([[1.,2.]]),np.array([[1.,0,0],[0,1,0],[-1,0,1]]))

    def test_forced_perspective_cannot_silently_fall_back(self):
        args = parser().parse_args(['input.jpg','--perspective','on'])
        with self.assertRaises(ValueError):
            measure_geometry(np.full((300,300),255,dtype='uint8'),args)

    def test_explicit_scan_circle_overrides_skip_perspective(self):
        args = parser().parse_args(['input.jpg','--geometry-policy','measured',
                                   '--outer','150,150,120','--hole','151,149,15'])
        geometry,perspective,matrix = measure_geometry(np.full((300,300),255,dtype='uint8'),args)
        self.assertIsNone(matrix)
        self.assertFalse(perspective['applied'])
        self.assertEqual(geometry['spindle_circle']['center_px'],[151,149])


@unittest.skipUnless(shutil.which('magick'),'ImageMagick required')
class PerspectiveRenderingTests(unittest.TestCase):
    def test_single_projective_warp_maps_actual_fiducials_and_feathered_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory); source=path/'source.ppm'; target=path/'out.png'
            y,x = np.mgrid[:320,:320]
            centers = np.array([[94.2,90.6],[224.7,150.3],[140.4,244.8]])
            # Small colored Gaussian fiducials expose swapped coefficients and
            # half-pixel mistakes that an output roundness test cannot see.
            pixels = np.stack([np.exp(-((x-cx)**2+(y-cy)**2)/8)*230 for cx,cy in centers],axis=2)
            source.write_bytes(b'P6\n320 320\n255\n'+pixels.astype('uint8').tobytes())
            matrix = np.array([[1.04,.09,-175],[-.05,.98,-150],[.0005,-.0003,1.]])
            outer=dict(center_px=[0,0],radius_px=137.3);hole=dict(center_px=[0,0],radius_px=17.2)
            mapped=render(source,target,outer,hole,21,size=292,feather=1,rectification_matrix=matrix)
            self.assertEqual(target.read_bytes()[24:26],bytes([16,6]))
            raw=run(['magick',str(target),'-depth','16','-endian','LSB','rgba:-'],binary=True)
            result=np.frombuffer(raw,dtype='<u2').reshape(292,292,4)
            expected=transform(centers,np.array(mapped['source_to_output_matrix']))
            yy,xx=np.mgrid[:292,:292]
            for channel,(cx,cy) in enumerate(expected):
                weights=result[:,:,channel].astype(float)
                measured=np.array([(weights*xx).sum(),(weights*yy).sum()])/weights.sum()
                self.assertLess(np.linalg.norm(measured-[cx,cy]),.2)
            alpha=result[:,:,3]/65535
            self.assertLess(abs(alpha.sum()/(math.pi*(137.3**2-17.2**2))-1),.0002)
            self.assertFalse(result[:,:,:3][result[:,:,3]==0].any())
            self.assertFalse(alpha[0].any())
            self.assertEqual(alpha[146,146],0)


if __name__=='__main__':
    unittest.main()
