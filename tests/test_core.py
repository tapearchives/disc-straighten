from __future__ import annotations

import math
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest
import struct

import numpy as np

from discstraight.cli import circle, expand, parser, source_name
from discstraight.geometry import detect
from discstraight.imaging import mapped_circle, render, run, standardize_png_metadata
from discstraight.orientation import consensus, deduplicate, distance


def text_row(text, correction=0, x=200, y=200, height=24, confidence=1):
    width = max(height,len(text)*height*.5)
    a = math.radians(-correction); c,s = math.cos(a),math.sin(a)
    local = np.array([[-width/2,height/2],[width/2,height/2],
                      [width/2,-height/2],[-width/2,-height/2]])
    polygon = local@np.array([[c,s],[-s,c]])+[x,y]
    return dict(text=text,characters=sum(c.isalnum() for c in text),letters=sum(c.isalpha() for c in text),
                confidence=confidence,correction_clockwise_degrees=correction,
                center_px=[x,y],polygon_px=polygon.tolist(),height_px=height,width_px=width,
                radial_position=.4,observed_tilt_degrees=0,view_clockwise_degrees=0)


class OrientationTests(unittest.TestCase):
    def test_separates_large_diagonal_decoration_from_consensus(self):
        rows = [text_row('MAGAZINE NAME AND DATE',-1,x=200,y=150),
                text_row('Monthly software collection',-1,x=600,y=500),
                text_row('260',44,x=600,y=250,height=140),
                text_row('Programs',44,x=600,y=350,height=65)]
        result = consensus(rows,700)
        self.assertAlmostEqual(result['clockwise_degrees'],-1)
        self.assertGreater(len(result['candidates']),1)

    def test_tiny_dense_legal_block_does_not_overrule_title(self):
        rows = [text_row('THE MAIN TITLE',10,x=350,y=100,height=40),
                text_row('SPECIAL EDITION',10,x=350,y=160,height=35)]
        rows += [text_row('copyright license all rights reserved',90,x=600+i*12,y=600,height=7)
                 for i in range(20)]
        self.assertAlmostEqual(consensus(rows,900)['clockwise_degrees'],10)
        self.assertAlmostEqual(consensus(rows,900,policy='majority')['clockwise_degrees'],90)

    def test_repeated_ocr_views_do_not_multiply_votes(self):
        row = text_row('Same physical line',20)
        self.assertEqual(len(deduplicate([dict(row) for _ in range(8)])),1)

    def test_close_competition_requests_review(self):
        rows = [text_row('AAA BBB CCC',0,x=200),text_row('DDD EEE FFF',90,x=700)]
        result = consensus(rows,900)
        self.assertEqual(result['status'],'review_required')
        self.assertIn('competing_text_directions',result['reasons'])

    def test_wraparound_angles_form_one_family(self):
        result = consensus([text_row('First heading',179,x=200),
                            text_row('Second heading',-179,x=600)],900)
        self.assertEqual(len(result['candidates']),1)
        self.assertLess(distance(result['clockwise_degrees'],180),2)

    def test_no_text_and_numbers_only_request_review(self):
        self.assertEqual(consensus([],500)['status'],'review_required')
        self.assertEqual(consensus([text_row('1234')],500)['status'],'review_required')


class GeometryTests(unittest.TestCase):
    def test_shifted_high_contrast_print_does_not_define_rim(self):
        y,x = np.mgrid[:380,:400]
        physical = np.hypot(x-198.3,y-191.6)
        print_distance = np.hypot(x-202.3,y-188.6)
        hole = np.hypot(x-197.1,y-193.2)
        # Six gray levels: too subtle for the coarse foreground threshold. The
        # outer search must extend past the shifted, high-contrast printed circle.
        gray = 255-6*np.clip((163.5-physical),0,1)
        gray -= 140*np.clip((150-print_distance),0,1)
        gray = np.where(hole<19.8,255,gray)
        fit = detect(gray.astype(np.uint8))
        outer = fit['outer_circle']; inner = fit['spindle_circle']
        self.assertLess(np.linalg.norm(np.array(outer['center_px'])-[198.3,191.6]),.65)
        self.assertLess(abs(outer['radius_px']-163),.7)
        self.assertLess(np.linalg.norm(np.array(inner['center_px'])-[197.1,193.2]),.8)
        self.assertGreater(fit['center_separation_px'],1)

    def test_plain_background_refused(self):
        with self.assertRaises(ValueError):
            detect(np.full((300,300),255,dtype=np.uint8))

    def test_complete_print_does_not_suppress_partly_visible_clear_rim(self):
        y,x=np.mgrid[:380,:400]
        physical=np.hypot(x-198.3,y-191.6)
        printing=np.hypot(x-202.3,y-188.6)
        # About 13 percent of the weak rim is invisible against white; the
        # much stronger offset printed circle remains complete.
        visible=abs(np.arctan2(y-191.6,x-198.3))>.4
        gray=255-6*np.clip(163.5-physical,0,1)*visible-140*np.clip(150-printing,0,1)
        gray=np.where(physical<20.375,255,gray).astype('uint8')
        fit=detect(gray)
        self.assertLess(abs(fit['outer_circle']['radius_px']-163),.7)
        np.testing.assert_allclose(fit['outer_circle']['center_px'],[198.3,191.6],atol=.65)

    def test_quarter_turn_maps_eccentric_hole(self):
        mapped = mapped_circle(dict(center_px=[104,100],radius_px=9),[100,100],90,201)
        np.testing.assert_allclose(mapped['center_px'],[100,104],atol=1e-8)


@unittest.skipUnless(shutil.which('magick'),'ImageMagick required')
class RenderingTests(unittest.TestCase):
    def test_metadata_cleanup_preserves_pixels_and_declares_srgb(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'output.png'
            run(['magick','-size','16x16','xc:#457ab8','-alpha','set',
                 '-set','exif:PixelXDimension','999','-set','comment','stale source text',
                 '-define','png:color-type=6',str(path)])
            before=run(['magick',str(path),'-depth','16','rgba:-'],binary=True)
            standardize_png_metadata(path)
            after=run(['magick',str(path),'-depth','16','rgba:-'],binary=True)
            self.assertEqual(before,after)
            data=path.read_bytes(); offset=8; chunks=[]
            while offset<len(data):
                length,kind=struct.unpack('>I4s',data[offset:offset+8])
                chunks.append(kind);offset+=length+12
            self.assertEqual(set(chunks),{b'IHDR',b'sRGB',b'IDAT',b'IEND'})
            self.assertEqual(chunks.count(b'sRGB'),1)

    def test_alpha_area_and_zero_rgb_survive_rotation(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp); source=path/'source.png'; target=path/'result.png'
            run(['magick','-size','256x256','xc:#457ab8',str(source)])
            outer=dict(center_px=[127.2,126.8],radius_px=110.3)
            hole=dict(center_px=[131.3,124.2],radius_px=14.7)
            mapped=render(source,target,outer,hole,37,size=240,feather=1)
            self.assertEqual(target.read_bytes()[24:26],bytes([16,6]))
            raw=run(['magick',str(target),'-depth','16','-endian','LSB','rgba:-'],binary=True)
            pixels=np.frombuffer(raw,dtype='<u2').reshape(mapped['height'],mapped['width'],4)
            alpha=pixels[:,:,3]/65535
            expected=math.pi*(110.3**2-14.7**2)
            self.assertLess(abs(alpha.sum()/expected-1),.0002)
            self.assertFalse(pixels[:,:,0:3][pixels[:,:,3]==0].any())
            for edge in (alpha[0],alpha[-1],alpha[:,0],alpha[:,-1]):
                self.assertTrue(edge.any(), 'No wholly transparent padding may remain')
            self.assertEqual(mapped['transparent_padding_px'],0)
            x,y=map(round,mapped['spindle_circle']['center_px'])
            self.assertEqual(alpha[y,x],0)
            self.assertEqual(pixels.dtype,np.dtype('<u2'))


class CommandTests(unittest.TestCase):
    def test_invalid_usage_is_failure_not_review_status(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as result:
            from discstraight.cli import main
            main([])
        self.assertEqual(result.exception.code,1)

    def test_nonfinite_geometry_rejected(self):
        for value in ['nan,0,1','0,0,-1','1,2','0,inf,2']:
            with self.assertRaises(Exception):
                circle(value)

    def test_unicode_url_has_safe_filename(self):
        self.assertEqual(source_name('https://example.org/%21Компьютерра%20Архив.jpg'),'Компьютерра-Архив')

    def test_empty_directory_and_duplicate_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(expand([temp]),[])
            p=Path(temp)/'image.jpg';p.touch()
            self.assertEqual(len(expand([str(p),str(p)])),1)


if __name__=='__main__':
    unittest.main()
