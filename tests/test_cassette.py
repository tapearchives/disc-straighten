"""Known geometry and radiometry controls, independent of private photographs."""
from __future__ import annotations

import json
import copy
import argparse
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from discstraight.cassette import (BODY_MM, detect_cassette, division_distort,
                                  division_undistort, plane_to_source,
                                  plumb_line_fit, source_to_plane, straight_trace_edge, line)
from discstraight.sampling import CubicSampler
from discstraight.cassette_raster import lanczos_sample, map_metrics, render_cassette, analyze_orientation
from discstraight.cassette_crop import body_crop, crop_alpha
from discstraight.cassette_boundary import refine_outer_boundary
from discstraight.cli import cassette_corners
from discstraight.perspective import transform


def fixture(projections=True, reels=True):
    image=np.full((520,780),242,np.uint8)
    image[260:]=15  # The exterior contrast changes sign halfway down.
    cv2.rectangle(image,(70,55),(710,462),150,-1)
    if projections:
        cv2.rectangle(image,(65,350),(70,440),150,-1)
        cv2.rectangle(image,(710,350),(715,440),150,-1)
    if reels:
        for x in [255,525]:
            cv2.circle(image,(x,240),38,25,-1)
            cv2.circle(image,(x,240),29,210,-1)
    return image


def simple_geometry():
    return dict(plane_size_px=[100.4,63.8],pixels_per_mm=1.,
                source_to_plane_matrix=[[1,0,-10],[0,1,-10],[0,0,1]],
                lens=dict(coefficient=0.,center_source_px=[64,44],scale_px=64,applied=False),
                conformance=dict(amplitudes_px=[[0,0]]*4,applied=False))


class CassetteGeometryTests(unittest.TestCase):
    def test_default_corners_intersect_straight_lines_without_lens_estimation(self):
        # A deliberately slanted view must remain a single homography, even if
        # a curved-corner or uncalibrated lens routine could fit it more closely.
        image=fixture(projections=False)
        source=np.array([[69.5,54.5],[710.5,54.5],[710.5,462.5],[69.5,462.5]],np.float32)
        target=np.array([[160,90],[688,43],[732,482],[94,417]],np.float32)
        photo=cv2.warpPerspective(image,cv2.getPerspectiveTransform(source,target),(800,550),borderValue=230)
        with patch('discstraight.cassette.curved_corners',side_effect=AssertionError('curved corners used')), \
             patch('discstraight.cassette.minimize_scalar',side_effect=AssertionError('lens estimation used')):
            g=detect_cassette(photo)
        q=np.array(g['undistorted_source_corners_px'])
        lines=np.array(g['fitted_source_lines'])
        for i in range(4):
            for j in [i-1,i]:
                self.assertLess(abs(lines[j,:2]@q[i]+lines[j,2]),1e-8)
        np.testing.assert_allclose(q,target,atol=1.)
        w,h=g['plane_size_px']
        np.testing.assert_allclose(source_to_plane(q,g),[[0,0],[w,0],[w,h],[0,h]],atol=1e-4)
        self.assertEqual(g['corner_method'],'intersections_of_fitted_straight_lines')
        self.assertIsNone(g['lens']['estimated_coefficient'])
        self.assertFalse(g['conformance']['applied'])

    def test_straight_ridge_ignores_faint_diverging_exterior_fringe(self):
        y,x=np.indices((180,160))
        image=np.full(x.shape,255.,np.float32)
        image[x<103+8*(y/179)**2]=246.  # faint exterior fringe widens downward
        image[x<100]=80.
        sampler=CubicSampler(cv2.GaussianBlur(image,(0,0),.65))
        trace=straight_trace_edge(sampler,np.array([100.,0.]),np.array([100.,179.]),band=12.)
        fitted=line(trace['points'][trace['inliers']])
        # Independent physical boundary is between columns 99 and 100.
        for ordinate in [15.,90.,165.]:
            abscissa=-(fitted[1]*ordinate+fitted[2])/fitted[0]
            self.assertAlmostEqual(abscissa,99.5,delta=.15)

    def test_low_resolution_frame_preserves_features_next_to_boundary(self):
        image = cv2.resize(fixture(projections=False), (390, 260), interpolation=cv2.INTER_AREA)
        g = detect_cassette(image)
        mask = body_crop(image, g, minimum_source_scale=map_metrics(g)['minimum_source_pixels_per_output_pixel'], corners='rectangle')
        w, h = g['plane_size_px']
        # Edge-adjacent screw rims must survive rather than lose a fixed
        # two-source-pixel guard plus aspect-ratio-amplified side margins.
        x = np.array([1., w-1., w-1., 1.])
        y = np.array([1., 1., h-1., h-1.])
        np.testing.assert_array_equal(crop_alpha(x, y, mask), np.ones(4))
        self.assertEqual(mask['bounds_px'],[0.,0.,w,h])
        self.assertEqual(mask['corner_radii_xy_px'],[[0.,0.]]*4)
        self.assertFalse(mask['source_pixels_masked_before_warp'])
        self.assertEqual(crop_alpha(np.array([mask['bounds_px'][0]-1.]), np.array([h/2]), mask)[0], 0)

    def test_weaker_outer_rim_is_not_erased_by_stronger_inner_reference(self):
        g = simple_geometry()
        image = np.full((90,130), 255, np.uint8)
        cv2.rectangle(image, (10,10), (110,74), 80, 1)
        cv2.line(image, (7,12), (7,72), 190, 1)
        cv2.line(image, (113,12), (113,72), 190, 1)
        g['diagnostics'] = dict(edge_source_points_px=[
            [[10,10],[110.4,10]], [[110.4,10],[110.4,73.8]],
            [[110.4,73.8],[10,73.8]], [[10,73.8],[10,10]]])
        g.update(detection_score=.8,reel_evidence={})
        g=refine_outer_boundary(cv2.cvtColor(image,cv2.COLOR_GRAY2RGB),g,debow='auto')
        mask = body_crop(image, g, minimum_source_scale=1.)
        # Both weaker outer lines must be fully opaque, including with a
        # feather. They are deliberately absent from calibration evidence.
        p=source_to_plane(np.array([[7.,40.],[113.,40.]]),g)
        a = crop_alpha(p[:,0],p[:,1],mask)
        np.testing.assert_array_equal(a, np.ones(2))

    def test_split_background_and_guide_rails_do_not_set_body_width(self):
        image=fixture()
        g=detect_cassette(image)
        expected=np.array([[69.5,54.5],[710.5,54.5],[710.5,462.5],[69.5,462.5]])
        np.testing.assert_allclose(g['undistorted_source_corners_px'],expected,atol=.4)
        self.assertGreater(g['detection_score'],.65)
        self.assertFalse(g['lens']['applied'])
        self.assertFalse(g['conformance']['applied'])
        self.assertAlmostEqual(g['plane_size_px'][0]/g['plane_size_px'][1],100.4/63.8,places=6)
        # Rails are excluded from the final straight crop as well as calibration.
        mask=body_crop(image,g,minimum_source_scale=map_metrics(g)['minimum_source_pixels_per_output_pixel'])
        p=source_to_plane(np.array([[67,400],[713,400],[40,300],[255,240]]),g)
        alpha=crop_alpha(p[:,0],p[:,1],mask)
        np.testing.assert_array_equal(alpha[:3],np.zeros(3))
        self.assertGreater(alpha[3],.9)  # A reel is not a disc knockout.
        self.assertFalse(mask['internal_apertures_removed'])

    def test_projective_recovery_preserves_independent_interior_landmarks(self):
        image=fixture(projections=False)
        source=np.array([[69.5,54.5],[710.5,54.5],[710.5,462.5],[69.5,462.5]],np.float32)
        target=np.array([[160,90],[688,43],[732,482],[94,417]],np.float32)
        matrix=cv2.getPerspectiveTransform(source,target)
        photo=cv2.warpPerspective(image,matrix,(800,550),borderValue=230)
        g=detect_cassette(photo,debow='off')
        # These points are not fitted or supplied to the detector.
        interior=np.array([[230,175],[570,180],[300,355],[525,330]],float)
        recovered=source_to_plane(transform(interior,matrix),g)/g['plane_size_px']
        expected=(interior-source[0])/(source[2]-source[0])
        np.testing.assert_allclose(recovered,expected,atol=.004)
        self.assertFalse(g['conformance']['applied'])

    def test_rectangle_without_reels_and_single_disc_are_not_cassettes(self):
        circle=np.full((520,780),245,np.uint8)
        cv2.circle(circle,(390,260),225,70,-1)
        cv2.circle(circle,(390,260),28,245,-1)
        for image in [fixture(reels=False),circle,np.full((500,800),255,np.uint8)]:
            with self.subTest(kind=int(image.mean())),self.assertRaises(ValueError):
                detect_cassette(image)

    def test_corners_refuse_crossing_concave_and_nonfinite_input(self):
        for value in ['0,0,100,0,30,20,0,80','0,0,100,80,100,0,0,80','0,0,nan,0,100,80,0,80']:
            with self.subTest(value=value),self.assertRaises(argparse.ArgumentTypeError):
                cassette_corners(value)
        self.assertEqual(cassette_corners('0,0,100,0,100,80,0,80').shape,(4,2))


class BowTests(unittest.TestCase):
    def test_division_model_inverse_and_nonreal_refusal(self):
        points=np.array([[25,80],[650,400],[300,200]],float)
        center=np.array([400,300]);scale=400
        for k in [-.09,0,.07]:
            distorted=division_distort(points,k,center,scale)
            np.testing.assert_allclose(division_undistort(distorted,k,center,scale),points,atol=1e-10)
        with self.assertRaises(ValueError):
            division_distort(np.array([[5000,5000]]),.1,center,scale)

    def test_radial_correction_requires_multiple_agreeing_edges(self):
        center=np.array([399.5,299.5]);scale=400
        q=np.array([[80,80],[720,80],[720,490],[80,490]])
        traces=[]
        for i in range(4):
            t=np.linspace(.05,.95,180)
            points=q[i]+t[:,None]*(q[(i+1)%4]-q[i])
            traces.append(dict(points=division_distort(points,.06,center,scale),inliers=np.ones(180,bool)))
        fit=plumb_line_fit(traces,(600,800),'auto')
        self.assertTrue(fit['applied'])
        self.assertAlmostEqual(fit['coefficient'],.06,places=4)
        self.assertLess(max(fit['heldout_edge_rms_after_candidate_px']),.001)
        for i in range(1,4):
            t=np.linspace(.05,.95,180)
            traces[i]['points']=q[i]+t[:,None]*(q[(i+1)%4]-q[i])
        self.assertFalse(plumb_line_fit(traces,(600,800),'auto')['applied'])
        self.assertFalse(plumb_line_fit(traces,(600,800),'off')['applied'])

    def test_composed_bow_and_lens_map_roundtrip_and_orientation(self):
        geometry=simple_geometry()
        geometry['lens'].update(coefficient=.03,applied=True)
        geometry['conformance'].update(applied=True,amplitudes_px=[[4,1],[2,-1],[-3,2],[-1,1]])
        y,x=np.mgrid[0:63.8:21j,0:100.4:31j];points=np.stack([x,y],axis=-1)
        source=plane_to_source(points,geometry)
        np.testing.assert_allclose(source_to_plane(source,geometry),points,atol=1e-8)
        self.assertGreater(map_metrics(geometry)['minimum_jacobian_determinant'],0)
        broken=copy.deepcopy(geometry);broken['source_to_plane_matrix'][0][0]=-1
        with self.assertRaises(ValueError):map_metrics(broken)


class OuterBoundaryTests(unittest.TestCase):
    def fixture(self):
        image = np.full((220,320,3), 253, np.uint8)
        cv2.rectangle(image,(20,20),(300,198),(240,240,240),-1)
        cv2.rectangle(image,(20,20),(300,198),(185,185,185),1)
        cv2.rectangle(image,(24,24),(296,194),(60,60,60),1)
        # White interior matches the exterior exactly, but is wanted content.
        cv2.rectangle(image,(80,70),(130,100),(253,253,253),-1)
        g = simple_geometry()
        g.update(plane_size_px=[272.,170.],pixels_per_mm=2.7,
                 source_to_plane_matrix=[[1,0,-24],[0,1,-24],[0,0,1]],
                 detection_score=.8,reel_evidence={},diagnostics={})
        return image,g

    def test_outer_boundary_defines_plane_without_opaque_guard_band(self):
        image,g = self.fixture()
        corrected = refine_outer_boundary(image,g,debow='auto')
        self.assertIn('outer_boundary',corrected)
        np.testing.assert_allclose(corrected['undistorted_source_corners_px'],
                                   [[19,19],[301,19],[301,199],[19,199]],atol=.7)
        crop = body_crop(cv2.cvtColor(image,cv2.COLOR_RGB2GRAY),corrected,
                         minimum_source_scale=map_metrics(corrected)['minimum_source_pixels_per_output_pixel'])
        self.assertTrue(crop['outer_boundary_refitted'])
        self.assertFalse(crop['alpha_depends_on_image_colors'])
        self.assertEqual(crop['bounds_px'][0],0.)
        p=source_to_plane(np.array([[10,100],[20,100],[105,85]],float),corrected)
        alpha=crop_alpha(p[:,0],p[:,1],crop)
        np.testing.assert_array_equal(alpha,[0,1,1])

    def test_mixed_background_does_not_trigger_uniform_color_key(self):
        image,g = self.fixture()
        image[110:,:20] = 0
        image[110:,301:] = 0
        image[199:] = 0
        corrected = refine_outer_boundary(image,g,debow='auto')
        self.assertNotIn('outer_boundary',corrected)

    @unittest.skipUnless(shutil.which('magick'),'ImageMagick required')
    def test_encoded_output_keeps_rim_and_interior_but_removes_white_exterior(self):
        image,g = self.fixture()
        corrected = refine_outer_boundary(image,g,debow='auto')
        crop = body_crop(cv2.cvtColor(image,cv2.COLOR_RGB2GRAY),corrected,
                         minimum_source_scale=map_metrics(corrected)['minimum_source_pixels_per_output_pixel'])
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.png';target=Path(temp)/'result.png'
            cv2.imwrite(str(source),image)
            for flip in [False,True]:
                info=render_cassette(source,target,image.shape[:2],corrected,crop,flip=flip)
                pix=cv2.imread(str(target),cv2.IMREAD_UNCHANGED)
                positions=source_to_plane(np.array([[10,100],[20,100],[105,85]],float),corrected)
                if flip:positions=np.array(corrected['plane_size_px'])-positions
                positions-=info['output_origin_in_rectified_plane_px']
                x,y=np.rint(positions[1]).astype(int)
                # Check integrated line contrast across neighboring samples:
                # a thin rim may land between output pixel centers. The stronger
                # inner frame is four source pixels away, outside this window.
                strip=pix[y,x-1:x+2].astype(float)/65535
                on_white=strip[:,:3]*strip[:,3,None]+(1-strip[:,3,None])
                self.assertGreater(float(np.sum(1-on_white.mean(axis=1))*255),35)
                self.assertLess(float(on_white.mean(axis=1).min()*255),225)
                x,y=np.rint(positions[2]).astype(int)
                self.assertEqual(pix[y,x,3],65535)
                self.assertFalse(pix[0,:,3].any())
                self.assertFalse(pix[:,:,:3][pix[:,:,3]==0].any())


class CassetteOrientationTests(unittest.TestCase):
    def test_prominent_heading_vs_many_small_rotated_lines(self):
        def row(text,height):
            return dict(text=text,confidence=.99,bottom_left=[.1,.4],bottom_right=[.9,.4],
                        top_left=[.1,.4+height],top_right=[.9,.4+height])
        title=[row('MAIN TITLE WITH WORDS',.10),row('PRIMARY SIDE HEADING',.09)]
        legal=[row('copyright notice',.015) for _ in range(10)]
        image=np.full((90,130,3),127,np.uint8)
        with tempfile.TemporaryDirectory() as temp:
            for policy,expected in [('balanced',0),('majority',180)]:
                with patch('discstraight.cassette_raster.recognize',side_effect=[dict(rows=title),dict(rows=legal)]):
                    result=analyze_orientation(image,simple_geometry(),Path(temp),Path(temp),'en-US',policy=policy)
                self.assertEqual(result['clockwise_degrees'],expected)
                self.assertFalse(result['fine_text_rotation_applied'])


class CassetteSamplingTests(unittest.TestCase):
    def test_integer_identity_and_continuous_subpixel_phase(self):
        image=np.arange(40*50,dtype='float32').reshape(40,50,1)/2000
        y,x=np.mgrid[8:25,9:34].astype(float)
        np.testing.assert_allclose(lanczos_sample(image,x,y),image[8:25,9:34],atol=2e-7)
        first=lanczos_sample(image,x+.005,y)
        second=lanczos_sample(image,x+.015,y)
        # Both coordinates round to the same 1/32-pixel lookup-table phase.
        self.assertGreater(float(np.mean(second-first)),2e-6)
        self.assertTrue(np.all(lanczos_sample(image,x-1000,y)==0))

    def test_premultiplied_sampling_keeps_edge_color(self):
        alpha=np.zeros((40,50),np.float32);alpha[6:34,7:40]=1
        color=np.array([.17,.43,.68],np.float32)
        image=np.dstack([alpha[...,None]*color,alpha])
        y,x=np.mgrid[3:38,4:44].astype(float)
        sample=lanczos_sample(image,x+.31,y+.63)
        valid=sample[...,3]>.001
        np.testing.assert_allclose(sample[valid,:3]/sample[valid,3,None],np.broadcast_to(color,(valid.sum(),3)),atol=2e-6)

    @unittest.skipUnless(shutil.which('magick'),'ImageMagick required')
    def test_encoded_alpha_and_color_are_valid_at_both_depths(self):
        geometry=simple_geometry()
        image=np.full((90,130,3),[70,120,180],np.uint8)
        crop=dict(bounds_px=[2,1.5,98.4,62.3],corner_radii_px=[3]*4)
        # Constant-color radiometry through the unmasked warp and final crop.
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.png';cv2.imwrite(str(source),image)
            for depth in [8,16]:
                target=Path(temp)/f'result-{depth}.png'
                render_cassette(source,target,image.shape[:2],geometry,crop,flip=True,depth=depth,feather=2)
                pixels=cv2.imread(str(target),cv2.IMREAD_UNCHANGED)
                self.assertEqual(pixels.dtype,np.uint8 if depth==8 else np.uint16)
                self.assertFalse(pixels[:,:,:3][pixels[:,:,3]==0].any())
                self.assertEqual(int(pixels[0,:,3].max()),0)
                self.assertGreater(int(pixels[:,:,3].max()),0)
                maximum=255 if depth==8 else 65535
                edge=(pixels[:,:,3]>0)&(pixels[:,:,3]<maximum)
                colors=pixels[:,:,:3][edge]/(maximum/255)
                np.testing.assert_allclose(colors,np.broadcast_to([70,120,180],colors.shape),atol=1)
                # Every central scan line has exactly the same straight edge.
                np.testing.assert_array_equal(pixels[20,10:-10,3],pixels[30,10:-10,3])

    def test_analytic_edges_do_not_inherit_bow_or_jagged_source_mask(self):
        crop=dict(bounds_px=[2.31,3.42,97.7,62.1],corner_radii_px=[4]*4)
        y,x=np.mgrid[:70,:105].astype(float)
        alpha=crop_alpha(x,y,crop,1.4)
        np.testing.assert_array_equal(alpha[20],alpha[45])
        np.testing.assert_array_equal(alpha[:,20],alpha[:,70])
        self.assertFalse(alpha[y<3.42-.7].any())
        self.assertFalse(alpha[x<2.31-.7].any())
        self.assertGreater(alpha[4,3],.95)  # No guessed corner cut.
        self.assertEqual(alpha[25,50],1)  # Interior features stay opaque.

    @unittest.skipUnless(shutil.which('magick'),'ImageMagick required')
    def test_output_alpha_is_rectangle_independent_of_all_pixel_colors(self):
        geometry=simple_geometry()
        crop=dict(bounds_px=[0,0,100.4,63.8],corner_radii_px=[0]*4)
        white=np.full((90,130,3),255,np.uint8)
        rng=np.random.default_rng(2)
        textured=rng.integers(0,256,white.shape,dtype=np.uint8)
        with tempfile.TemporaryDirectory() as temp:
            alphas=[]
            for i,image in enumerate([white,textured]):
                source=Path(temp)/f'source-{i}.png';target=Path(temp)/f'result-{i}.png'
                cv2.imwrite(str(source),image)
                info=render_cassette(source,target,image.shape[:2],geometry,crop,flip=False)
                pixels=cv2.imread(str(target),cv2.IMREAD_UNCHANGED)
                alphas.append(pixels[:,:,3])
                self.assertFalse(info['source_pixels_masked_before_warp'])
                self.assertFalse(info['alpha_depends_on_image_colors'])
                self.assertEqual(info['source_boundary_clipped_pixels'],0)
            np.testing.assert_array_equal(alphas[0],alphas[1])
            np.testing.assert_array_equal(alphas[0][10],alphas[0][50])
            np.testing.assert_array_equal(alphas[0][:,10],alphas[0][:,90])
            self.assertTrue((alphas[0][3:65,3:102]==65535).all())


if __name__=='__main__':unittest.main()
