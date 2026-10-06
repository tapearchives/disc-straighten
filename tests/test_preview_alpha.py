"""Preview checks must reveal, not alter, the transparent master."""
from pathlib import Path
import hashlib
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from discstraight.outputs import after_preview
from discstraight.imaging import alpha_canvas_bounds


class PreviewTests(unittest.TestCase):
    def test_tight_canvas_preserves_even_one_unit_of_feather_alpha(self):
        for dtype in (np.uint8,np.uint16):
            pixels=np.zeros((30,40,4),dtype)
            pixels[5:25,8:32]=np.iinfo(dtype).max
            pixels[4,19,3]=1  # The faintest representable feather is content.
            pixels[5:9,8:12]=0  # A transparent corner must remain transparent.
            left,top,right,bottom=alpha_canvas_bounds(pixels[...,3])
            self.assertEqual((left,top,right,bottom),(8,4,32,25))
            cut=pixels[top:bottom,left:right]
            np.testing.assert_array_equal(cut[cut[...,3]>0],pixels[pixels[...,3]>0])
            self.assertEqual(cut[0,11,3],1)
            self.assertEqual(cut[2,1,3],0)

    def test_transparent_canvas_is_an_error_not_a_fake_one_pixel_image(self):
        with self.assertRaisesRegex(ValueError,'no visible pixels'):
            alpha_canvas_bounds(np.zeros((10,20),np.uint16))

    @unittest.skipUnless(shutil.which('magick'),'ImageMagick required')
    def test_checkerboard_leaves_master_unchanged(self):
        image=np.zeros((60,100,4),np.uint8);image[15:45,20:80]=[30,80,160,255]
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'master.png';preview=Path(temporary)/'preview.png'
            cv2.imwrite(str(source),image);digest=hashlib.sha256(source.read_bytes()).digest()
            after_preview(source,preview)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),digest)
            result=cv2.imread(str(preview),cv2.IMREAD_UNCHANGED)
            self.assertEqual(result.shape,(60,100,3))
            self.assertGreater(len(np.unique(result[:15].reshape(-1,3),axis=0)),1)
            np.testing.assert_array_equal(result[30,50],[30,80,160])
