"""Compare temporary PNG compression; pixel hashes must match for every view."""
from pathlib import Path
import hashlib
import json
import statistics
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from discstraight import imaging


def main():
    source,log_path,output = map(Path,sys.argv[1:])
    data = json.loads(log_path.read_text())
    outer = data['measurements']['outer_circle']
    matrix = np.array(data['perspective']['source_to_plane_matrix']) if data['perspective']['applied'] else None
    original = imaging.run
    rows = []
    with tempfile.TemporaryDirectory() as td:
        source_copy = Path(td)/'source.miff'
        imaging.normalize(source.resolve(),source_copy)
        for repeat in range(3):
            for angle in [0,45,135]:
                for level in ['default','0','1']:
                    target = Path(td)/f'view-{level}.png'
                    def run(args,**kwargs):
                        # Test the original default even after production starts
                        # specifying a temporary-file compression level.
                        args = list(args)
                        for index in range(len(args)-1,0,-1):
                            if args[index].startswith('png:compression-level='):
                                del args[index-1:index+1]
                        if level!='default':
                            args = args[:-1]+['-define',f'png:compression-level={level}']+args[-1:]
                        return original(args,**kwargs)
                    imaging.run = run
                    start = time.perf_counter()
                    imaging.ocr_view(source_copy,target,angle,outer['center_px'],outer['radius_px'],matrix)
                    elapsed = time.perf_counter()-start
                    raw = original(['magick',str(target),'-depth','8','rgb:-'],binary=True)
                    rows.append(dict(repeat=repeat+1,angle=angle,compression=level,seconds=elapsed,
                                     bytes=target.stat().st_size,pixel_sha256=hashlib.sha256(raw).hexdigest()))
        imaging.run = original
    for angle in [0,45,135]:
        assert len({r['pixel_sha256'] for r in rows if r['angle']==angle})==1
    for level in ['default','0','1']:
        subset = [r for r in rows if r['compression']==level]
        print(level,'median seconds',statistics.median(r['seconds'] for r in subset),
              'median bytes',statistics.median(r['bytes'] for r in subset),flush=True)
    output.write_text(json.dumps(dict(source=str(source),log=str(log_path),measurements=rows,
                                    all_decoded_pixels_identical=True),indent=2)+'\n')


if __name__=='__main__':
    main()
