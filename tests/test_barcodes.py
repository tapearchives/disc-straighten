"""Real decoding, adjacent pairing, collision protection and publication rollback."""
import contextlib
import errno
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import cv2
import numpy as np
import zxingcpp

from discstraight.barcodes import scan, filename_code
from discstraight.barcode_pairs import rename_pair
from discstraight.batch import run_batch
from discstraight.cli import parser
from discstraight.outputs import targets


def report(text=None):
    return dict(status='decoded' if text else 'not_found',readings=[dict(text=text,valid=True)] if text else [])


def record(root,name,code=None):
    paths=targets(root,name)
    result=dict(source=dict(input=name+'.jpg',sha256='original'),barcodes=report(code),
                output=dict(file=paths['image'].relative_to(root).as_posix(),sha256='derivative'),
                finishing=dict(metadata=dict(enabled=True,source_inventory_file=paths['metadata'].name)))
    for key,path in paths.items():path.write_text(json.dumps(result) if key=='log' else key)
    return dict(root=root,input=name+'.jpg',paths=paths,result=result)


class BarcodeTests(unittest.TestCase):
    def test_rotated_code128_preserves_leading_zeros(self):
        pixels=np.asarray(zxingcpp.create_barcode('00104305',zxingcpp.BarcodeFormat.Code128).to_image(scale=3))
        found=scan(np.rot90(pixels))
        self.assertEqual(found['status'],'decoded')
        self.assertEqual(filename_code(found),('00104305','usable'))
        self.assertEqual(found['readings'][0]['format'].replace(' ',''),'Code128')
        self.assertEqual(len(found['readings'][0]['corners_px']),4)

    def test_ambiguous_and_unsafe_values_are_never_filenames(self):
        for value in ['../../escape','123/456',' ','A:B','x'*101]:
            self.assertIsNone(filename_code(report(value))[0])
        codes=report('one');codes['readings'].append(dict(text='two',valid=True))
        self.assertEqual(filename_code(codes),(None,'multiple_barcode_values'))

    def test_pair_moves_every_derivative_and_updates_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=record(root,'front');b=record(root,'back','00104305')
            old=[*a['paths'].values(),*b['paths'].values()]
            changed,reason=rename_pair(a,b)
            self.assertEqual(reason,'paired');self.assertEqual(len(changed),2)
            self.assertEqual(a['paths']['image'].name,'00104305A.png')
            self.assertEqual(b['paths']['image'].name,'00104305B.png')
            self.assertFalse(any(p.exists() for p in old))
            for item,side in [(a,'A'),(b,'B')]:
                saved=json.loads(item['paths']['log'].read_text())
                self.assertEqual(saved['barcode_pair']['side'],side)
                self.assertEqual(saved['source']['sha256'],'original')
                self.assertEqual(saved['output']['sha256'],'derivative')
                self.assertEqual(saved['finishing']['metadata']['source_inventory_file'],'00104305'+side+'-source-metadata.json')

    def test_collision_leaves_both_sets_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=record(root,'front');b=record(root,'back','123')
            target=a['paths']['image'].with_name('123a.png');target.write_text('prior')
            old={p:p.read_bytes() for p in [*a['paths'].values(),*b['paths'].values()]}
            self.assertEqual(rename_pair(a,b),([],'barcode_output_name_collision'))
            self.assertEqual(target.read_text(),'prior')
            self.assertEqual(old,{p:p.read_bytes() for p in old})

    def test_partial_publication_rolls_back_without_losing_old_outputs(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=record(root,'front');b=record(root,'back','123')
            old={p:p.read_bytes() for p in [*a['paths'].values(),*b['paths'].values()]};real=os.link;count=0
            def fail(source,target):
                nonlocal count
                count+=1
                if count==4:raise OSError(errno.ENOSPC,'test disk full')
                real(source,target)
            with patch('discstraight.barcode_pairs.os.link',side_effect=fail):
                changed,reason=rename_pair(a,b)
            self.assertEqual(changed,[]);self.assertTrue(reason.startswith('pair_publication_failed'))
            self.assertEqual(old,{p:p.read_bytes() for p in old})
            self.assertFalse(list(root.rglob('123*')))

    def test_no_skipping_failed_or_already_paired_previous_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=record(root,'front');b=record(root,'back','123')
            self.assertEqual(rename_pair(None,b)[1],'no_successful_immediately_previous_input')
            a['paired']=True
            self.assertEqual(rename_pair(a,b)[1],'previous_input_already_paired')
            a.pop('paired');a['result']['barcodes']=report('999')
            self.assertEqual(rename_pair(a,b)[1],'previous_input_has_barcode_or_unverified_scan')

    def test_preview_worker_runs_while_first_conversion_is_waiting(self):
        from discstraight.imaging import run as real_run
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);sources=[root/'a.png',root/'b.png'];preview_done=threading.Event();threads=[]
            for source in sources:cv2.imwrite(str(source),np.full((40,80,3),180,np.uint8))
            def thumbnail(command,*a,**kw):
                threads.append(threading.current_thread().name)
                value=real_run(command,*a,**kw)
                if str(sources[1])+'[0]' in command:preview_done.set()
                return value
            def process(item,name,args,cache):
                self.assertTrue(preview_done.wait(15),'second preview was blocked by the first conversion')
                return dict(status='accepted',rotation=dict(clockwise_degrees=0),output=dict(file='output-images/'+name+'.png'),warnings=[])
            args=parser().parse_args(['--preview']);out=io.StringIO()
            with contextlib.redirect_stdout(out),patch('discstraight.imaging.run',side_effect=thumbnail):
                self.assertEqual(run_batch([str(p) for p in sources],['a','b'],[root/'output']*2,args,root,process),0)
            events=[json.loads(line) for line in out.getvalue().splitlines()]
            self.assertEqual([e['status'] for e in events[:2]],['queued','queued'])
            self.assertTrue(all(name.startswith('input-previews') for name in threads))
            self.assertEqual(sum(e['status']=='input_preview' for e in events),2)
