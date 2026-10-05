"""Independent controls for recursive batches, radiometry, metadata, and HEIC."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from discstraight.cli import expand, parser
from discstraight.finishing import adjust,keep_metadata
from discstraight.imaging import normalize,run
from discstraight.outputs import reserve_folder
from discstraight.cassette_corners import fit_corners
from test_cassette import simple_geometry


class BatchTests(unittest.TestCase):
    def test_recursive_selection_deduplicates_and_ignores_generated_trees(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            for name in ['a.jpg','nested/b.HEIC','nested/c.heif','output/old.jpg',
                         'archive/old.jpg','nested/a-preview.png','.hidden/no.jpg','readme.txt']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
            (root/'archive'/'.un-askew-output').touch()
            found=expand([str(root),str(root/'nested'),str(root/'a.jpg')])
            self.assertEqual(set(found),{str(root/p) for p in ['a.jpg','nested/b.HEIC','nested/c.heif']})
            self.assertEqual(len(found),3)

    def test_fresh_folders_never_replace_a_previous_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)/'output'
            first=reserve_folder(base);(first/'keep.txt').write_text('original')
            second=reserve_folder(base);third=reserve_folder(base)
            self.assertEqual(first,base.resolve())
            self.assertEqual(len({first,second,third}),3)
            self.assertTrue(second.name.startswith('output_'))
            self.assertEqual((first/'keep.txt').read_text(),'original')
            self.assertEqual(reserve_folder(base,overwrite=True),first)

    def test_defaults_are_auto_and_finishing_is_off(self):
        args=parser().parse_args(['photo.HEIC'])
        self.assertEqual(args.media,'auto')
        self.assertFalse(any([args.auto_adjust,args.auto_contrast,args.auto_brightness,args.auto_color,args.keep_metadata]))

    def test_all_four_unresolved_corners_have_explicit_inference_provenance(self):
        geometry=simple_geometry()
        fits=fit_corners(np.full((90,130),128,np.uint8),geometry)
        self.assertEqual(len(fits),4)
        self.assertTrue(all(f['applied'] and f['evidence']=='inferred' for f in fits))
        for fit in fits:np.testing.assert_allclose(fit['radii_xy_px'],[2,2],atol=1e-8)


class FinishingTests(unittest.TestCase):
    def test_disabled_is_byte_identical_and_adjustment_preserves_alpha(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'image.png'
            y,x=np.indices((180,220));a=np.where((x>20)&(x<200)&(y>20)&(y<160),65535,0).astype('uint16')
            rgb=np.stack([np.full(x.shape,7000),np.full(x.shape,12000),5000+x*25],axis=-1).astype('uint16')
            image=np.dstack([rgb,a]);cv2.imwrite(str(path),image)
            original=path.read_bytes()
            self.assertFalse(adjust(path,contrast=False,brightness=False,color=False)['enabled'])
            self.assertEqual(original,path.read_bytes())
            result=adjust(path,contrast=True,brightness=True,color=True)
            changed=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
            self.assertTrue(result['enabled']);np.testing.assert_array_equal(changed[...,3],a)
            self.assertFalse(np.array_equal(changed[50,50,:3],image[50,50,:3]))
            self.assertFalse(changed[...,:3][a==0].any())

    @unittest.skipUnless(shutil.which('exiftool') and shutil.which('magick'),'ExifTool and ImageMagick required')
    def test_metadata_preserves_camera_gps_and_title_but_fixes_geometry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source.jpg';output=root/'output.png'
            run(['magick','-size','260x180','xc:gray',str(source)])
            run(['exiftool','-overwrite_original','-Make=Example Camera','-Model=Unit Test',
                 '-Orientation#=6','-GPSLatitude=12.5','-GPSLatitudeRef=N','-XMP-dc:Title=Archive example',str(source)])
            run(['magick','-size','300x200','xc:gray','-alpha','set','-define','png:color-type=6',str(output)])
            before=cv2.imread(str(output),cv2.IMREAD_UNCHANGED)
            report=keep_metadata(source,output,root/'metadata.json')
            tags=json.loads(run(['exiftool','-j','-n',str(output)]))[0]
            self.assertEqual(tags['Make'],'Example Camera');self.assertEqual(tags['Orientation'],1)
            self.assertEqual(tags['ExifImageWidth'],300);self.assertEqual(tags['ExifImageHeight'],200)
            self.assertAlmostEqual(tags['GPSLatitude'],12.5)
            self.assertEqual(tags['Title'],'Archive example')
            np.testing.assert_array_equal(cv2.imread(str(output),cv2.IMREAD_UNCHANGED),before)
            self.assertTrue(report['enabled']);self.assertTrue((root/'metadata.json').is_file())
            self.assertNotIn('not defined',report['copy_warnings'])

    @unittest.skipUnless(shutil.which('magick'),'ImageMagick required')
    def test_heic_primary_image_normalizes(self):
        if 'HEIC' not in run(['magick','-list','format']):self.skipTest('HEIC delegate unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source.heic';target=root/'normalized.miff'
            run(['magick','-size','256x192','gradient:#234567-#eeeeee',str(source)])
            result=normalize(source,target)
            self.assertEqual((result['width'],result['height']),(256,192))
            self.assertTrue(target.is_file())

@unittest.skipUnless(shutil.which('magick'),'ImageMagick required')
class TransparentDerivativeTests(unittest.TestCase):
    def test_disc_preserves_missing_source_pixels_and_partial_alpha(self):
        from discstraight.imaging import render
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'input.png';output=root/'output.png'
            pixels=np.full((256,256,4),255,np.uint8)
            pixels[80:100,80:100,3]=0;pixels[150:180,150:180,3]=128
            cv2.imwrite(str(source),pixels)
            render(source,output,dict(center_px=[127.5,127.5],radius_px=110),
                   dict(center_px=[127.5,127.5],radius_px=13.75),0,size=256,feather=1)
            result=cv2.imread(str(output),cv2.IMREAD_UNCHANGED)
            self.assertEqual(result[90,90,3],0)
            self.assertLess(abs(int(result[165,165,3])-32896),100)
            self.assertEqual(result[128,128,3],0)
            self.assertEqual(result[0,0,3],0)
            self.assertFalse(result[...,:3][result[...,3]==0].any())
