"""Local OCR backends with common normalized line polygons and provenance."""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .imaging import run

LANGUAGES={'en':'eng','ru':'rus','de':'deu','fr':'fra','es':'spa','it':'ita','ja':'jpn',
           'ko':'kor','zh':'chi_sim','pt':'por','nl':'nld'}


class OCRUnavailableError(ValueError):
    """The requested local OCR service cannot run with this configuration."""


def ocr_run(args: list[str]) -> str:
    try:
        return run(args)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise OCRUnavailableError(f'Local OCR could not run: {error}') from error


def text_slope(gray: np.ndarray) -> tuple[float,float] | None:
    """Measure letter-center alignment; Tesseract often reports a zero baseline
    for visibly slanted sparse text. This is analysis only, never a color warp.
    """
    if min(gray.shape)<5:return None
    _,binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if np.mean(binary)>127:binary=255-binary
    _,_,stats,centers=cv2.connectedComponentsWithStats(binary)
    stats=stats[1:];centers=centers[1:]
    valid=(stats[:,4]>=5)&(stats[:,4]<gray.size*.2)&(stats[:,2]>1)&(stats[:,3]>3)
    if valid.sum()<4:return None
    height=float(np.median(stats[valid,3]))
    valid&=(stats[:,3]>height*.55)&(stats[:,3]<height*1.6)
    p=centers[valid]
    if len(p)<4 or np.ptp(p[:,0])<gray.shape[1]*.45:return None
    # Pairwise slope median resists punctuation and a disconnected letter dot.
    dx=p[:,None,0]-p[None,:,0];dy=p[:,None,1]-p[None,:,1]
    select=abs(dx)>gray.shape[1]*.2
    slope=float(np.median(dy[select]/dx[select]))
    error=p[:,1]-slope*p[:,0];keep=abs(error-np.median(error))<height*.25
    if keep.mean()<.7 or keep.sum()<4 or abs(slope)>.7:return None
    slope=float(np.polyfit(p[keep,0],p[keep,1],1)[0])
    return slope,height


def select_backend(requested: str = 'auto') -> str:
    if requested=='auto':
        return 'vision' if platform.system()=='Darwin' else 'tesseract'
    if requested=='vision' and platform.system()!='Darwin':
        raise OCRUnavailableError('Apple Vision requires macOS. Use --ocr tesseract on Windows.')
    return requested


@lru_cache(maxsize=1)
def tesseract_info() -> tuple[list[str],str]:
    if not shutil.which('tesseract'):
        raise OCRUnavailableError('Tesseract is unavailable on PATH; see WINDOWS.md. Discs use visual deskew; cassettes require OCR or --angle.')
    languages=ocr_run(['tesseract','--list-langs']).splitlines()[1:]
    version=ocr_run(['tesseract','--version']).splitlines()[0]
    return [s.strip() for s in languages if s.strip()],version


def hocr_rows(document: str, width: int, height: int, gray: np.ndarray | None = None) -> list[dict]:
    root=ET.fromstring(document);rows=[]
    def field(node, name):
        match=re.search(r'(?:^|;)\s*'+re.escape(name)+r'\s+([^;]+)',node.get('title',''))
        return match.group(1).split() if match else []
    def point(x,y):return [float(x/width),float(1-y/height)]
    for node in root.iter():
        if 'ocr_line' not in node.get('class','').split():continue
        bbox=field(node,'bbox');baseline=field(node,'baseline')
        words=[n for n in node.iter() if 'ocrx_word' in n.get('class','').split()]
        if len(bbox)!=4 or not words:continue
        x0,y0,x1,y1=map(float,bbox)
        slope,intercept=map(float,baseline[:2]) if len(baseline)>=2 else (0.,0.)
        confidences=[float(field(n,'x_wconf')[0])/100 for n in words if field(n,'x_wconf')]
        word_heights=[float(field(n,'bbox')[3])-float(field(n,'bbox')[1]) for n in words if len(field(n,'bbox'))==4]
        line_height=float(np.median(word_heights)) if word_heights else y1-y0
        if gray is not None:
            estimate=text_slope(gray[max(0,int(y0)):min(height,int(y1)),max(0,int(x0)):min(width,int(x1))])
            if estimate is not None:
                slope,line_height=estimate
                intercept=-(slope*(x1-x0))/2-(y1-y0-line_height)/2
        left=y1+intercept;right=left+slope*(x1-x0)
        rows.append(dict(text=' '.join(''.join(n.itertext()).strip() for n in words),
                         confidence=float(np.mean(confidences)) if confidences else 0.,
                         bottom_left=point(x0,left),bottom_right=point(x1,right),
                         top_left=point(x0,left-line_height),top_right=point(x1,right-line_height)))
    return rows


def recognize(path: Path, languages: str, cache: Path, backend: str = 'auto') -> dict:
    backend=select_backend(backend)
    if backend=='none':
        raise OCRUnavailableError('OCR disabled with --ocr none. For cassettes supply --angle 0 or --angle 180.')
    if backend=='vision':
        from .orientation import helper_binary
        try:
            helper=helper_binary(cache)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            raise OCRUnavailableError(f'Apple Vision helper is unavailable: {error}') from error
        data=json.loads(ocr_run([str(helper),str(path),languages]))
        data.update(engine='Apple Vision accurate',languages=languages.split(','),missing_languages=[])
        return data
    available,version=tesseract_info()
    requested=list(dict.fromkeys(LANGUAGES.get(s.split('-')[0],s) for s in languages.split(',')))
    selected=[s for s in requested if s in available];missing=[s for s in requested if s not in available]
    if not selected:
        raise OCRUnavailableError(f'No requested Tesseract language is installed: {requested}. Available: {available}')
    document=ocr_run(['tesseract',str(path),'stdout','-l','+'.join(selected),'--oem','1','--psm','11','hocr'])
    image=cv2.imread(str(path));height,width=image.shape[:2]
    return dict(rows=hocr_rows(document,width,height,cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)),revision=version,engine='Tesseract LSTM',
                languages=selected,missing_languages=missing)
