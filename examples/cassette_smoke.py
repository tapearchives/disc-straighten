"""Generate a cassette control and exercise auto routing, OCR, mask, and logs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def smoke(folder: Path) -> dict:
    image=np.full((520,780,3),240,np.uint8);image[260:]=18
    cv2.rectangle(image,(70,55),(710,462),(135,150,165),-1)
    for x in [255,525]:
        cv2.circle(image,(x,240),38,(20,20,20),-1)
        cv2.circle(image,(x,240),29,(205,205,205),-1)
    cv2.rectangle(image,(65,350),(70,440),(135,150,165),-1)
    cv2.rectangle(image,(710,350),(715,440),(135,150,165),-1)
    for text,y,size in [('TAPE ARCHIVES',135,1.2),('SYNTHETIC CASSETTE',335,.9),('SIDE A',410,.8)]:
        width=cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,size,2)[0][0]
        cv2.putText(image,text,(390-width//2,y),cv2.FONT_HERSHEY_SIMPLEX,size,(25,25,25),2,cv2.LINE_AA)
    # Clockwise quarter turn makes the body and OCR choose orientation together.
    source=folder/'synthetic-cassette.png';cv2.imwrite(str(source),cv2.rotate(image,cv2.ROTATE_90_CLOCKWISE))
    output=folder/'results'
    run=subprocess.run([sys.executable,'-m','discstraight',str(source),'--media','auto',
                        '--languages','en-US','--ocr',os.environ.get('DISC_TEST_OCR','auto'),'-o',str(output)],cwd=ROOT,capture_output=True,text=True,timeout=120)
    if run.returncode!=2:raise RuntimeError(f'Expected a reviewable cassette derivative: {run.returncode}: {run.stderr}')
    log=json.loads((output/'output-json'/'synthetic-cassette-straightened.json').read_text())
    assert log['media']=='cassette' and log['schema_version']==7
    assert len(log['mask']['corner_fits'])==4
    assert all(f['applied'] for f in log['mask']['corner_fits'])
    assert log['source']['camera']['metadata_status']=='absent'
    assert abs(log['rotation']['clockwise_degrees']+90)<.2
    assert 'cassette_single_plane_approximation' in log['warnings']
    assert not log['geometry']['lens']['applied']
    assert abs(log['output']['body_aspect_ratio']-100.4/63.8)<1e-12
    png=output/log['output']['file'];pixels=cv2.imread(str(png),cv2.IMREAD_UNCHANGED)
    assert pixels.dtype==np.uint16 and pixels.shape[2]==4
    assert not pixels[:,:,:3][pixels[:,:,3]==0].any()
    assert not pixels[0,:,3].any() and not pixels[-1,:,3].any()
    assert hashlib.sha256(png.read_bytes()).hexdigest()==log['output']['sha256']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==log['source']['sha256']
    report=dict(tool_version=log['tool']['version'],media=log['media'],status=log['status'],
                clockwise_rotation_degrees=log['rotation']['clockwise_degrees'],
                png_sha256=log['output']['sha256'],timing=log['timing'],
                result='Auto routing, quarter-turn orientation, encoded alpha, provenance, and review notes passed',
                limitation='Original synthetic control; not a real-photo accuracy benchmark')
    (folder/'smoke-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Retain a new run directory')
    args=parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True,exist_ok=False);result=smoke(args.output.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='cassette-smoke-') as temp:result=smoke(Path(temp))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
