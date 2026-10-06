"""Sequence gaps must not shift identity or erase originals; PDF grid is stable."""
import json
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
import hashlib

from PIL import Image, ImageDraw
import pypdfium2 as pdfium

from discstraight.catalog import inventory, materialize_gaps, sequence
from discstraight.contact_sheet import create
from discstraight.barcode_pairs import rename_back
from test_barcodes import record


class CatalogTests(unittest.TestCase):
    def media_photo(self):
        photo=Image.new('RGB',(800,550),'white');draw=ImageDraw.Draw(photo)
        draw.rounded_rectangle((50,52,750,498),radius=18,fill='#777777',outline='black',width=4)
        for x in (250,548):draw.ellipse((x-46,193,x+46,285),fill='white',outline='black',width=5)
        draw.rectangle((359,210,439,266),fill='black')
        return photo

    def photo(self, folder, name):
        folder.mkdir(parents=True, exist_ok=True)
        path=folder/name
        Image.new('RGB',(300,192),(30,140,170)).save(path)
        return path

    def test_missing_whole_number_is_one_cell_missing_side_is_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); images=root/'output-images'
            for name in ['001A.png','001B.png','003B.png']:
                self.photo(images,name)
            report=inventory(root)
            self.assertEqual([(x['catalog'],x['side'],x['kind']) for x in report['entries']],
                             [('001','A','image'),('001','B','image'),('002',None,'missing'),
                              ('003','A','missing'),('003','B','image')])
            before={p.name:p.read_bytes() for p in images.iterdir()}
            manifest=materialize_gaps(root)
            self.assertEqual(len(manifest['generated_placeholders']),2)
            self.assertEqual(before,{name:(images/name).read_bytes() for name in before})
            with Image.open(images/'002 MISSING - PLACEHOLDER.png') as image:
                self.assertEqual(image.getpixel((0,0)),(255,255,0))
                self.assertIn((0,0,255),image.get_flattened_data())
            log=json.loads((root/'output-json'/'003A MISSING - PLACEHOLDER.json').read_text())
            self.assertTrue(log['synthetic']);self.assertIsNone(log['source'])

    def test_range_width_and_sparse_safety(self):
        self.assertEqual(sequence(['0001','0003']),['0001','0002','0003'])
        for values in [(['01','2'],None,None),(['x','y'],None,None),(['000000000001','999999999999'],None,None),(['0001','2000'],None,None)]:
            with self.assertRaises(ValueError):sequence(*values)
        self.assertEqual(len(sequence(['0001','2000'],'0001','2000')),2000)
        self.assertEqual(sequence([],'01','02'),['01','02'])

    def test_duplicate_real_slots_block_and_old_dummy_is_superseded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.photo(root,'001A.png');self.photo(root,'001 MISSING - PLACEHOLDER.png')
            report=inventory(root)
            self.assertEqual(len(report['superseded_placeholders']),1)
            self.assertEqual(report['entries'][0]['kind'],'image')
            self.photo(root,'001A.jpg')
            with self.assertRaisesRegex(ValueError,'Duplicate'):inventory(root)

    def test_first_back_keeps_its_number_and_preserves_old_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);back=record(root,'first','001')
            changed,reason=rename_back(back)
            self.assertEqual(reason,'back_only');self.assertEqual(changed,[back])
            self.assertEqual(back['paths']['image'].name,'001B.png')
            self.assertIsNone(back['result']['barcode_pair']['partner_input'])
            duplicate=record(root,'duplicate','001')
            self.assertEqual(rename_back(duplicate)[1],'barcode_output_name_collision')
            self.assertTrue(duplicate['paths']['image'].exists())

    def test_twenty_cells_per_letter_page_and_missing_text_in_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);images=root/'output-images'
            for i in range(1,22):
                if i in (11,14):continue
                for side in ('A','B'):self.photo(images,f'{i:06}{side}.png')
            # 42 side slots minus two pairs plus two placeholders = 40 cells.
            result=create(root,title='Catalog test',start='000001',end='000021')
            self.assertEqual((result['pages'],result['catalogs'],result['missing']),(2,21,2))
            with pdfium.PdfDocument(result['pdf']) as pdf:
                self.assertEqual(len(pdf),2)
                page=pdf[1];self.assertEqual(page.get_size(),(612,792))
                textpage=page.get_textpage();text=textpage.get_text_range()
                self.assertIn('MISSING',text);self.assertIn('000021B',text)
                textpage.close();page.close()
            manifest=json.loads(Path(result['log']).read_text())
            self.assertEqual(manifest['entries'][20]['catalog'],'000011')
            self.assertTrue(manifest['complete'])
            self.assertEqual(len(result['previews']),2)

    def test_invalid_folder_and_conflict_do_not_publish_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):create(Path(tmp))
            self.assertFalse((Path(tmp)/'contact-sheet').exists())

    def test_nonstandard_names_are_reported_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.photo(root,'001A.png');self.photo(root,'001B MISLABELED AS 002.png')
            report=inventory(root)
            self.assertEqual(report['ignored_files'],['001B MISLABELED AS 002.png'])
            self.assertEqual(report['entries'][1]['kind'],'missing')

    def test_full_cli_handles_first_back_missing_number_failed_front_and_trailing_unknown(self):
        import numpy as np
        import zxingcpp
        from discstraight.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'inputs';source.mkdir()
            for name,code in [('00-back.png','0001'),('01-front.png',None),('02-back.png','0003'),
                              ('04-back.png','0005'),('05-unassigned.png',None)]:
                photo=self.media_photo()
                if code:
                    barcode=Image.fromarray(np.asarray(zxingcpp.create_barcode(code,zxingcpp.BarcodeFormat.Code128).to_image(scale=4)))
                    photo.paste(barcode,(100,350))
                photo.save(source/name)
            (source/'03-invalid.jpg').write_bytes(b'not an image')
            original={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                status=main([str(source),'--catalog-only','--name-barcode-pairs','-o',str(root/'output')])
            self.assertEqual(status,1)
            manifest=json.loads((root/'output/output-json/catalog-sequence.json').read_text())
            self.assertEqual((manifest['catalog_count'],manifest['image_count'],manifest['missing_count']),(5,4,4))
            self.assertEqual(manifest['ignored_files'],['05-unassigned-straightened.png'])
            self.assertTrue((root/'output/output-images/0005B.png').is_file())
            self.assertTrue((root/'output/output-images/0005A MISSING - PLACEHOLDER.png').is_file())
            self.assertFalse((root/'output/output-images/0005A.png').exists())
            self.assertEqual(original,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()})
            events=[json.loads(line) for line in out.getvalue().splitlines()]
            self.assertEqual(events[-1]['status'],'catalog_complete')
            self.assertEqual(sum(e['status']=='failed' for e in events),1)

    def test_barcode_only_reference_anchors_missing_number_without_consuming_front(self):
        import numpy as np
        import zxingcpp
        from discstraight.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'inputs';source.mkdir()
            self.media_photo().save(source/'00-unassigned.png')
            reference=Image.new('RGB',(800,550),'white')
            barcode=Image.fromarray(np.asarray(zxingcpp.create_barcode('0007',zxingcpp.BarcodeFormat.Code128).to_image(scale=4)))
            reference.paste(barcode,(100,120));reference.save(source/'01-empty-case.png')
            back=self.media_photo()
            barcode=Image.fromarray(np.asarray(zxingcpp.create_barcode('0008',zxingcpp.BarcodeFormat.Code128).to_image(scale=4)))
            back.paste(barcode,(100,350));back.save(source/'02-back.png')
            before={p.name:p.read_bytes() for p in source.iterdir()}
            with contextlib.redirect_stdout(io.StringIO()):
                main([str(source),'--catalog-only','--name-barcode-pairs','-o',str(root/'output')])
            result=inventory(root/'output')
            self.assertEqual([(x['catalog'],x['side'],x['kind']) for x in result['entries']],
                             [('0007',None,'missing'),('0008','A','missing'),('0008','B','image')])
            self.assertEqual(result['ignored_files'],['00-unassigned-straightened.png'])
            self.assertEqual(len(result['barcode_references']),1)
            self.assertTrue(Path(result['barcode_references'][0]['image']).is_file())
            self.assertFalse((root/'output/output-images/0007B.png').exists())
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})

    def test_presence_supports_disc_and_reviewed_geometry_bypasses_coarse_gate(self):
        import numpy as np
        from argparse import Namespace
        from discstraight.media_presence import evidence, catalog_reference
        from test_barcodes import report
        photo=Image.new('L',(800,600),255);draw=ImageDraw.Draw(photo)
        draw.ellipse((150,50,650,550),fill=130)
        self.assertEqual(evidence(np.asarray(photo))['media'],'disc')
        args=Namespace(name_barcode_pairs=True,gap_placeholders=True,cassette_corners=[(0,0)]*4,outer=None)
        self.assertIsNone(catalog_reference(np.full((500,800),255,dtype=np.uint8),report('0007'),args))


if __name__=='__main__':unittest.main()
