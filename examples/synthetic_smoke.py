"""Exercise the CLI on original synthetic artwork, without external downloads.

Run with the project's environment: .venv/bin/python examples/synthetic_smoke.py
Optional --output retains a new run directory; otherwise temporary files expire.
"""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from verify_results import verify_nominal_geometry


def smoke(folder: Path) -> dict:
    image = np.full((720, 720, 3), 255, dtype=np.uint8)
    cv2.circle(image, (360, 360), 300, (230, 230, 230), -1, cv2.LINE_AA)
    cv2.circle(image, (360, 360), 283, (65, 70, 80), -1, cv2.LINE_AA)
    cv2.circle(image, (360, 360), 38, (255, 255, 255), -1, cv2.LINE_AA)
    for text, y, scale in [('TAPE ARCHIVES', 230, 1.35), ('DISC ALIGNMENT', 480, 1.15),
                           ('SYNTHETIC TEST', 535, .9)]:
        width = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)[0][0]
        cv2.putText(image, text, (360-width//2, y), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, (245, 245, 245), 2, cv2.LINE_AA)
    # Known 17-degree clockwise input rotation. This is analysis/test generation,
    # not a resampling step in the production pipeline.
    matrix = cv2.getRotationMatrix2D((360, 360), -17, 1)
    rotated = cv2.warpAffine(image, matrix, (720, 720), flags=cv2.INTER_CUBIC,
                             borderValue=(255, 255, 255))
    source = folder / 'synthetic-disc.png'
    if not cv2.imwrite(str(source), rotated):
        raise RuntimeError('Could not write synthetic input')
    output = folder / 'results'
    run = subprocess.run([sys.executable, '-m', 'discstraight', str(source),
                          '-o', str(output), '--media', 'auto', '--disc-size', '120', '--languages', 'en-US',
                          '--ocr',os.environ.get('DISC_TEST_OCR','auto')],
                         cwd=ROOT, capture_output=True, text=True, timeout=180)
    if run.returncode not in (0, 2):
        raise RuntimeError(f'CLI smoke failed: {run.stderr[-4000:]}')
    data = json.loads((output / 'synthetic-disc-straightened.json').read_text())
    assert data['media'] == 'disc', 'Auto selection must retain a disc'
    png = output / data['output']['file']
    payload = png.read_bytes()
    assert payload[24:26] == bytes([16, 6]), 'Expected encoded 16-bit RGBA'
    assert hashlib.sha256(payload).hexdigest() == data['output']['sha256']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == data['source']['sha256']
    pixels = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
    assert pixels is not None and pixels.dtype == np.uint16 and pixels.shape[2] == 4
    alpha = pixels[:, :, 3] / 65535
    assert not pixels[:, :, :3][pixels[:, :, 3] == 0].any(), 'Transparent RGB must be zero'
    nominal = verify_nominal_geometry(data, alpha)
    angle = data['rotation']['clockwise_degrees']
    error = abs((angle + 17 + 180) % 360 - 180)
    assert error < 1, f'OCR failed known orientation: {angle}'
    assert not alpha[0].any() and not alpha[-1].any()
    assert not alpha[:, 0].any() and not alpha[:, -1].any()
    report = dict(tool_version=data['tool']['version'], input='original synthetic disc',
                  clockwise_rotation_degrees=angle, angle_error_degrees=error,
                  status=data['status'], review_reasons=data['warnings'],
                  nominal_geometry=nominal, png_sha256=data['output']['sha256'],
                  result='geometry, OCR, encoded pixels, hashes, and transparent RGB checks passed',
                  limitation='Synthetic disc only; not evidence of cassette or broad real-image accuracy')
    (folder / 'smoke-report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Retain a new run directory')
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        result = smoke(args.output.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='disc-smoke-') as temporary:
            result = smoke(Path(temporary))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
