"""Repeatable wall-clock attribution without changing production algorithm choices."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discstraight import __version__, cli, imaging, orientation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('inputs',nargs='+',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeat',type=int,default=3)
    parser.add_argument('--label',default=__version__)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    if args.repeat<1:
        parser.error('--repeat must be at least 1')
    measurements=[]; stages=defaultdict(list); calls=defaultdict(list)
    original_run=imaging.run
    def measured_run(command,**kwargs):
        start=time.perf_counter()
        try:
            return original_run(command,**kwargs)
        finally:
            if Path(command[0]).name.startswith('vision-'):
                category='Vision OCR subprocess'
            elif command[0]=='swiftc':
                category='Swift compile'
            elif command[0]=='magick':
                if any('ocr-' in arg and arg.endswith('.png') for arg in command):
                    category='OCR view rendering'
                elif any('fine-orientation-' in arg for arg in command):
                    category='Fine view rendering'
                elif command[-1].endswith('/output.png'):
                    category='Final ImageMagick rendering'
                else:
                    category='Other ImageMagick IO'
            else:
                category=Path(command[0]).name
            calls[category].append(time.perf_counter()-start)
    imaging.run=measured_run; orientation.run=measured_run; cli.run=measured_run
    def wrap(name,function):
        def timed(*a,**kw):
            start=time.perf_counter()
            try: return function(*a,**kw)
            finally: stages[name].append(time.perf_counter()-start)
        return timed
    for name in ['acquire','normalize','gray_pixels','measure_geometry','orient','render']:
        setattr(cli,name,wrap(name,getattr(cli,name)))
    cache=Path.home()/'.cache/disc-straighten'
    for repeat in range(args.repeat):
        for source in args.inputs:
            stages.clear(); calls.clear()
            folder=args.output/f'run-{repeat+1}'/source.stem;folder.mkdir(parents=True,exist_ok=True)
            options=cli.parser().parse_args([str(source),'-o',str(folder),'--preview','--overwrite'])
            start=time.perf_counter()
            result=cli.process(str(source.resolve()),source.stem,options,cache)
            elapsed=time.perf_counter()-start
            row=dict(label=args.label,source=source.name,repeat=repeat+1,seconds=elapsed,
                     stages={k:sum(v) for k,v in stages.items()},
                     subprocesses={k:dict(seconds=sum(v),count=len(v)) for k,v in calls.items()},
                     status=result['status'],angle=result['rotation']['clockwise_degrees'],
                     image_sha256=result['output']['sha256'],
                     source_sha256=result['source']['sha256'],
                     source_dimensions=[result['source']['width'],result['source']['height']],
                     runtime=result['runtime'])
            measurements.append(row)
            report=dict(label=args.label,tool_version=__version__,python=platform.python_version(),
                        platform=platform.platform(),scope='Warm dependencies and OCR helper; local inputs; '
                        'no download or initial installation; includes PNG, JSON, and preview output.',
                        measurements=measurements)
            (args.output/'timings.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(row),flush=True)
    for source in args.inputs:
        rows=[r['seconds'] for r in measurements if r['source']==source.name]
        print(f'{source.name}: median {statistics.median(rows):.3f}s; range {min(rows):.3f}–{max(rows):.3f}s',flush=True)


if __name__=='__main__':
    main()
