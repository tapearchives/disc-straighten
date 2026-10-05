"""Independent angle controls and automatic no-OCR routing contracts."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from discstraight.deskew import estimate
from discstraight.ocr import OCRUnavailableError, recognize, tesseract_info
from discstraight.orientation import orient


def artwork() -> np.ndarray:
    image = np.full((720, 720), 240, np.uint8)
    cv2.circle(image, (360, 360), 300, 50, -1)
    cv2.circle(image, (360, 360), 38, 240, -1)
    for text, y, scale in [('TAPE ARCHIVES', 230, 1.35), ('DISC ALIGNMENT', 480, 1.15),
                           ('SYNTHETIC TEST', 535, .9)]:
        width = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)[0][0]
        cv2.putText(image, text, (360-width//2, y), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, 245, 2, cv2.LINE_AA)
    return image


class DeskewTests(unittest.TestCase):
    def test_corrects_both_directions_and_fractional_angles(self):
        for angle in (-44., -30., -17.35, 0., 12.65, 30., 44.):
            with self.subTest(angle=angle):
                image = cv2.warpAffine(artwork(), cv2.getRotationMatrix2D((360, 360), -angle, 1),
                                       (720, 720), borderValue=240)
                result = estimate(image, (360, 360), 300)
                self.assertAlmostEqual(result['clockwise_degrees'], -angle, delta=.3)
                self.assertEqual(result['status'], 'review_required')
                self.assertIn('ocr_free_upright_direction_unverified', result['reasons'])

    def test_blank_and_rings_do_not_acquire_a_direction(self):
        for rings in (False, True):
            image = np.full((720, 720), 240, np.uint8)
            if rings:
                for radius in (295, 280, 170, 70, 38):
                    cv2.circle(image, (360, 360), radius, 20, 3, cv2.LINE_AA)
            result = estimate(image, (360, 360), 300)
            self.assertEqual(result['clockwise_degrees'], 0.)
            self.assertIn('insufficient_text_like_marks_kept_original_angle', result['reasons'])

    def test_search_never_exceeds_requested_range(self):
        image = cv2.warpAffine(artwork(), cv2.getRotationMatrix2D((360, 360), -60, 1),
                               (720, 720), borderValue=240)
        result = estimate(image, (360, 360), 300)
        self.assertLessEqual(abs(result['clockwise_degrees']), 45.)
        self.assertTrue(all(abs(r['clockwise_degrees']) <= 45 for r in result['candidates']))

    def test_conflicting_equal_text_directions_are_not_silently_accepted(self):
        image = artwork()
        opposite = cv2.warpAffine(image, cv2.getRotationMatrix2D((360, 360), -30, 1),
                                  (720, 720), borderValue=50)
        image = np.maximum(image, opposite)
        result = estimate(image, (360, 360), 300)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['clockwise_degrees'], 0.)
        self.assertIn('ambiguous_straightness_kept_original_angle', result['reasons'])
        self.assertTrue(result['mixed_directions'])


class FallbackRoutingTests(unittest.TestCase):
    def call(self, **kwargs):
        return orient(Path('source.png'), dict(center_px=[360, 360], radius_px=300),
                      Path('.'), Path('.'), languages='en-US', policy='balanced',
                      minimum_margin=.2, progress=lambda _: None, **kwargs)

    def test_default_auto_falls_back_when_ocr_is_missing(self):
        with patch('discstraight.orientation._orient_ocr', side_effect=OCRUnavailableError('missing engine')), \
             patch('discstraight.deskew.orient_without_ocr', return_value={'clockwise_degrees': -12.}) as fallback:
            self.assertEqual(self.call()['clockwise_degrees'], -12.)
            self.assertEqual(fallback.call_args.kwargs['requested_backend'], 'auto')
            self.assertEqual(fallback.call_args.kwargs['reason'], 'missing engine')

    def test_explicit_none_does_not_attempt_ocr(self):
        with patch('discstraight.orientation._orient_ocr') as ocr, \
             patch('discstraight.deskew.orient_without_ocr', return_value={'clockwise_degrees': 0.}):
            self.call(backend='none')
            ocr.assert_not_called()

    def test_unrelated_image_errors_are_not_hidden(self):
        with patch('discstraight.orientation._orient_ocr', side_effect=ValueError('invalid image')), \
             self.assertRaisesRegex(ValueError, 'invalid image'):
            self.call()

    def test_missing_executable_and_missing_language_are_ocr_unavailability(self):
        tesseract_info.cache_clear()
        with patch('discstraight.ocr.shutil.which', return_value=None), \
             self.assertRaises(OCRUnavailableError):
            tesseract_info()
        with patch('discstraight.ocr.tesseract_info', return_value=(['eng'], 'test')), \
             self.assertRaisesRegex(OCRUnavailableError, 'No requested Tesseract language'):
            recognize(Path('unused.png'), 'ru-RU', Path('.'), 'tesseract')

    def test_engine_failure_is_classified_for_fallback(self):
        with patch('discstraight.ocr.tesseract_info', return_value=(['eng'], 'test')), \
             patch('discstraight.ocr.run', side_effect=RuntimeError('engine initialization failed')), \
             self.assertRaisesRegex(OCRUnavailableError, 'initialization failed'):
            recognize(Path('unused.png'), 'en-US', Path('.'), 'tesseract')

    def test_sparse_tesseract_retries_level_views_but_keeps_ocr_as_evidence(self):
        angles = []
        def view(source, target, angle, center, radius, matrix):
            angles.append(angle)
            return dict(size=720, scale=1, center=center, angle=angle)
        row = dict(text='TAPE ARCHIVES', confidence=.95, bottom_left=[.2,.55],
                   bottom_right=[.8,.55], top_left=[.2,.61], top_right=[.8,.61])
        def recognize(*args):
            return dict(rows=[row] if len(angles)==9 else [], engine='Tesseract LSTM',
                        languages=['eng'], revision='test', missing_languages=[])
        visual = dict(clockwise_degrees=-17., reasons=['ocr_free_upright_direction_unverified'], search={})
        with patch('discstraight.orientation.ocr_view', side_effect=view), \
             patch('discstraight.ocr.recognize', side_effect=recognize), \
             patch('discstraight.deskew.analyze_visual', return_value=visual):
            result = self.call(backend='tesseract')
        self.assertEqual(result['clockwise_degrees'], -17.)
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['candidates'][0]['examples'], ['TAPE ARCHIVES'])
        self.assertEqual(result['ocr']['visually_seeded_views'], 4)
        self.assertNotIn('ocr_unavailable', result['reasons'])

    def test_ambiguous_visual_marks_do_not_add_ocr_seed_views(self):
        data = dict(rows=[], engine='Tesseract LSTM', languages=['eng'], revision='test', missing_languages=[])
        visual = dict(clockwise_degrees=0., reasons=['ambiguous_straightness_kept_original_angle'], search={})
        with patch('discstraight.orientation.ocr_view'), \
             patch('discstraight.ocr.recognize', return_value=data) as ocr, \
             patch('discstraight.deskew.analyze_visual', return_value=visual):
            result = self.call(backend='tesseract')
        self.assertEqual(ocr.call_count, 8)
        self.assertEqual(result['clockwise_degrees'], 0.)
        self.assertEqual(result['reasons'], ['no_readable_text'])
