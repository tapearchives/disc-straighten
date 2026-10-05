"""Camera provenance must survive normalization without inventing calibration."""
from pathlib import Path
import json
import shutil
import struct
import tempfile
import unittest

import cv2
import numpy as np

from discstraight.camera import describe_camera
from discstraight.imaging import normalize, run


def tagged_jpeg(path: Path, model: str) -> None:
    """An actual little-endian EXIF APP1 segment, not mocked identify output."""
    # IFD0 camera identity, software and a private description; nested EXIF lens.
    fields = [(0x010e, b'PRIVATE NOTE MUST NOT BE LOGGED\0'), (0x010f, b'Apple\0'),
              (0x0110, model.encode()+b'\0'), (0x0131, b'Fixture capture app\0')]
    ifd0_count = len(fields)+1
    exif_offset = 8+2+12*ifd0_count+4
    data_offset = exif_offset+2+12*2+4
    entries = []; data = bytearray()
    for tag, value in fields:
        entries.append(struct.pack('<HHII', tag, 2, len(value), data_offset+len(data)))
        data.extend(value)
    entries.append(struct.pack('<HHII', 0x8769, 4, 1, exif_offset))
    lens = b'Fixture back camera 6.765mm f/1.78\0'
    lens_entry = struct.pack('<HHII', 0xa434, 2, len(lens), data_offset+len(data))
    data.extend(lens)
    focal_entry = struct.pack('<HHII', 0x920a, 5, 1, data_offset+len(data))
    data.extend(struct.pack('<II', 6765, 1000))
    tiff = (b'II\x2a\x00'+struct.pack('<I', 8)+struct.pack('<H', ifd0_count)+b''.join(entries)+b'\0'*4
            +struct.pack('<H', 2)+focal_entry+lens_entry+b'\0'*4+data)
    exif = b'Exif\0\0'+tiff
    ok, encoded = cv2.imencode('.jpg', np.full((128, 160, 3), 180, np.uint8))
    assert ok
    original = encoded.tobytes()
    path.write_bytes(original[:2]+b'\xff\xe1'+struct.pack('>H', len(exif)+2)+exif+original[2:])


class CameraTests(unittest.TestCase):
    def test_model_names_do_not_imply_coefficients_or_capture_setting(self):
        for model in ['iPhone 7 Plus', 'iPhone 15 Pro Max']:
            result = describe_camera(dict(make='Apple', model=model,
                                          focal_length_35mm_equivalent='48', digital_zoom_ratio='2'))
            self.assertEqual(result['recognized_family'], model)
            self.assertEqual(result['lens_role_from_explicit_label'], 'unknown')
            self.assertEqual(result['prior_software_lens_correction'], 'unknown')
            self.assertFalse(result['model_specific_profile_applied'])
        self.assertIsNone(describe_camera(dict(make='Other',model='iPhone 7 Plus'))['recognized_family'])
        self.assertEqual(describe_camera({})['metadata_status'], 'absent')

    def test_only_explicit_lens_label_sets_role(self):
        result = describe_camera(dict(model='iPhone 15 Pro Max',lens_model='Back Ultra Wide camera'))
        self.assertEqual(result['lens_role_from_explicit_label'], 'ultra_wide')
        self.assertFalse(result['model_specific_profile_applied'])

    @unittest.skipUnless(shutil.which('magick'), 'ImageMagick required')
    def test_real_embedded_tags_saved_before_profiles_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'camera.jpg'; target = Path(directory)/'normalized.miff'
            for model in ['iPhone 7 Plus', 'iPhone 15 Pro Max']:
                tagged_jpeg(source, model)
                result = normalize(source, target)['camera']
                self.assertEqual(result['recognized_family'], model)
                self.assertEqual(result['exif']['make'], 'Apple')
                self.assertIn('6.765mm', result['exif']['lens_model'])
                self.assertTrue(result['exif']['focal_length_mm'])
                self.assertNotIn('PRIVATE NOTE', json.dumps(result))
                # MIFF can cache EXIF properties even after dropping its profile.
                # This temporary file is private; final PNG chunk cleanup drops
                # all source metadata. The public log uses only our allowlist.
                self.assertNotIn('exif', run(['magick','identify','-format','%[profiles]',str(target)]).lower())


if __name__ == '__main__':
    unittest.main()
