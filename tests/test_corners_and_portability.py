"""Independent corner-shape, pre-warp ratio, OCR and CLI contracts."""
from __future__ import annotations
import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from discstraight.cassette_corners import aspect_ratio_tag,fit_corners
from discstraight.cassette_crop import crop_alpha
from discstraight.cli import parser
from discstraight.ocr import hocr_rows,select_backend,text_slope


class CornerTests(unittest.TestCase):
    def test_ratio_is_observed_before_template_stretch(self):
        q=np.array([[0,0],[100.4,0],[100.4,63.8],[0,63.8]])
        self.assertEqual(aspect_ratio_tag(q)['tag'],'compact cassette AR')
        self.assertTrue(aspect_ratio_tag(q*[.97,1])['matched'])
        self.assertFalse(aspect_ratio_tag(q*[.8,1])['matched'])

    def test_known_curves_preserve_screws_and_remove_exterior_corners(self):
        w,h=800.,800*63.8/100.4
        y,x=np.mgrid[:620,:920].astype(float);u=x-50;v=y-50
        distance=np.minimum.reduce([u,w-u,v,h-v])
        radii=[20.,26.,30.,24.]
        for i,r in enumerate(radii):
            a=u if i in [0,3] else w-u;b=v if i in [0,1] else h-v
            distance=np.where((a<r)&(b<r),np.minimum(distance,r-np.hypot(a-r,b-r)),distance)
        image=(245-12*np.clip(distance+.5,0,1)).astype('uint8')
        # Strong dark circles inside the shell must not become its corner edge.
        for a,b in [(35,35),(w-35,35),(w-35,h-35),(35,h-35)]:
            cv2.circle(image,(round(a+50),round(b+50)),16,20,-1)
        geometry=dict(plane_size_px=[w,h],source_to_plane_matrix=[[1,0,-50],[0,1,-50],[0,0,1]],
                      lens=dict(coefficient=0.,center_source_px=[460,310],scale_px=460),
                      conformance=dict(amplitudes_px=[[0.,0.]]*4))
        fits=fit_corners(image,geometry)
        self.assertTrue(all(f['applied'] for f in fits),fits)
        for measured,expected in zip(fits,radii):
            np.testing.assert_allclose(measured['fitted_radii_xy_px'],expected,atol=1.5)
        crop=dict(bounds_px=[0,0,w,h],corner_fits=fits)
        self.assertEqual(crop_alpha(np.array([1.]),np.array([1.]),crop)[0],0.)
        self.assertEqual(crop_alpha(np.array([35.]),np.array([35.]),crop)[0],1.)
        # Long straight sides are identical to the rectangle-only comparison.
        np.testing.assert_array_equal(crop_alpha(np.array([0.,w]),np.array([h/2,h/2]),crop),[.5,.5])

    def test_unsupported_corner_is_not_guessed(self):
        crop=dict(bounds_px=[0,0,100,64],corner_fits=[dict(applied=False)]*4)
        self.assertEqual(crop_alpha(np.array([1.]),np.array([1.]),crop)[0],1.)


class PortabilityTests(unittest.TestCase):
    def test_windows_auto_uses_tesseract_without_apple_helper(self):
        with patch('discstraight.ocr.platform.system',return_value='Windows'):
            self.assertEqual(select_backend(),'tesseract')
            with self.assertRaisesRegex(ValueError,'requires macOS'):select_backend('vision')

    def test_hocr_preserves_sloping_baseline_and_unicode(self):
        document='''<html><span class="ocr_line" title="bbox 10 20 110 60; baseline 0.1 -5">
        <span class="ocrx_word" title="bbox 10 20 50 60; x_wconf 94">Test</span>
        <span class="ocrx_word" title="bbox 60 22 110 60; x_wconf 90">кассета</span>
        </span></html>'''
        row=hocr_rows(document,200,100)[0]
        self.assertEqual(row['text'],'Test кассета')
        self.assertAlmostEqual(row['confidence'],.92)
        self.assertAlmostEqual(row['bottom_right'][1]-row['bottom_left'][1],-.1)

    def test_pixel_text_slope_has_independent_known_rotation(self):
        image=np.full((200,700),255,np.uint8)
        cv2.putText(image,'ARCHIVE LETTERS',(65,100),cv2.FONT_HERSHEY_SIMPLEX,1.3,0,2,cv2.LINE_AA)
        image=cv2.warpAffine(image,cv2.getRotationMatrix2D((350,100),-12,1),(700,200),borderValue=255)
        result=text_slope(image[10:115,65:410])  # OCR supplies a local text box.
        self.assertIsNotNone(result)
        self.assertAlmostEqual(np.degrees(np.arctan(result[0])),12,delta=.6)

    def test_help_has_windows_examples_and_review_exit_code(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output),self.assertRaises(SystemExit) as caught:parser().parse_args(['-h'])
        self.assertEqual(caught.exception.code,0)
        for token in ['Examples','de-askew.cmd','--cassette-crop','--ocr','2 = images saved']:
            self.assertIn(token,output.getvalue())
