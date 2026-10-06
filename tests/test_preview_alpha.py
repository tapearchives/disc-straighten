"""Preview checks must reveal, not alter, the transparent master."""
from pathlib import Path
import hashlib
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from discstraight.outputs import after_preview


class PreviewTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('magick'),'ImageMagick required')
    def test_checkerboard_leaves_master_unchanged(self):
        image=np.zeros((60,100,4),np.uint8);image[15:45,20:80]=[30,80,160,255]
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'master.png';preview=Path(temporary)/'preview.png'
            cv2.imwrite(str(source),image);digest=hashlib.sha256(source.read_bytes()).digest()
            after_preview(source,preview)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),digest)
            result=cv2.imread(str(preview),cv2.IMREAD_UNCHANGED)
            self.assertEqual(result.shape,(72,112,3))
            self.assertGreater(len(np.unique(result[:15].reshape(-1,3),axis=0)),1)
            np.testing.assert_array_equal(result[36,56],[30,80,160])
