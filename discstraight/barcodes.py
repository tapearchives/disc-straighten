"""Decode photographed barcodes without OCR guesses or numeric coercion."""
from __future__ import annotations

from importlib.metadata import version
import re

import numpy as np


def scan(pixels: np.ndarray) -> dict:
    try:
        import zxingcpp
    except ImportError:
        return dict(status='unavailable',backend='zxing-cpp',readings=[],reason='decoder_not_installed')
    try:
        codes=zxingcpp.read_barcodes(np.ascontiguousarray(pixels,dtype=np.uint8),
                                     try_rotate=True,try_downscale=True,try_invert=True)
        readings=[]
        for code in codes:
            if not code.valid:continue
            position=code.position
            readings.append(dict(text=code.text,format=str(code.format),valid=True,
                                 corners_px=[[getattr(position,key).x,getattr(position,key).y]
                                             for key in ['top_left','top_right','bottom_right','bottom_left']]))
        return dict(status='decoded' if readings else 'not_found',backend='zxing-cpp',
                    version=version('zxing-cpp'),coordinate_space='EXIF-normalized source pixels',readings=readings)
    except (RuntimeError,ValueError) as error:
        return dict(status='error',backend='zxing-cpp',readings=[],reason=str(error))


def filename_code(report: dict) -> tuple[str | None,str]:
    values={r['text'] for r in report.get('readings',[]) if r.get('valid')}
    if len(values)!=1:
        return None,'multiple_barcode_values' if values else report.get('status','not_found')
    value=values.pop()
    # Literal text is retained in logs, even when unsafe for portable filenames.
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value):
        return None,'barcode_not_safe_for_filename'
    return value,'usable'
