"""Optional derivative finishing; geometry and alpha are never changed here."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np

from .imaging import standardize_png_metadata


def linearize(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)


def adjust(path: Path, *, contrast: bool, brightness: bool, color: bool) -> dict:
    requested=dict(contrast=contrast,brightness=brightness,color=color)
    if not any(requested.values()):
        return dict(enabled=False,requested=requested)
    pixels=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
    if pixels is None or pixels.ndim!=3 or pixels.shape[2]!=4:
        raise ValueError('Finishing requires an RGBA derivative')
    maximum=np.iinfo(pixels.dtype).max
    step=max(1,int(np.ceil(max(pixels.shape[:2])/1200)))
    small=pixels[::step,::step]
    rgb=small[...,:3][...,::-1].astype('float32')/maximum
    visible=small[...,3]>=maximum*.99
    samples=linearize(rgb[visible])
    if len(samples)<100:
        return dict(enabled=False,requested=requested,reason='insufficient_opaque_pixels')
    weights=np.array([.2126,.7152,.0722],np.float32)
    gains=np.ones(3,np.float32)
    color_reason='disabled'
    if color:
        high=samples.max(axis=1);low=samples.min(axis=1)
        neutral=(high-low<.18)&(high>.10)&(high<.9)
        if neutral.sum()>=max(100,len(samples)*.01):
            mean=samples[neutral].mean(axis=0)
            gains=np.clip(mean.mean()/np.maximum(mean,1e-6),.9,1.1)
            color_reason='neutral_pixel_balance_with_10_percent_gain_limit'
        else:
            color_reason='no_reliable_neutral_sample_color_unchanged'
    luminance=(samples*gains)@weights
    exposure=float(np.clip(.25/max(float(np.median(luminance)),.001),.5,2.)) if brightness else 1.
    black,white=np.percentile(luminance*exposure,[.5,99.5])
    black=float(np.clip(black,0,.06)) if contrast else 0.
    slope=float(np.clip(1/max(float(white)-black,.01),1.,1.8)) if contrast else 1.
    for start in range(0,len(pixels),64):
        block=pixels[start:start+64]
        values=linearize(block[...,:3][...,::-1].astype('float32')/maximum)*gains*exposure
        luma=values@weights
        target=np.clip((luma-black)*slope,0,1)
        values*=np.divide(target,np.maximum(luma,1e-6))[...,None]
        values=np.clip(values,0,1)
        encoded=np.where(values<=.0031308,12.92*values,1.055*values**(1/2.4)-.055)
        block[...,:3]=np.rint(encoded[...,::-1]*maximum).astype(pixels.dtype)
        block[...,:3][block[...,3]==0]=0
    if not cv2.imwrite(str(path),pixels,[cv2.IMWRITE_PNG_COMPRESSION,6]):
        raise RuntimeError('Could not save adjusted derivative')
    standardize_png_metadata(path)
    return dict(enabled=True,requested=requested,analysis='opaque cropped pixels only; linear sRGB',
                exposure_multiplier=exposure,contrast_black_point=black,contrast_slope=slope,
                color_gains_rgb=gains.tolist(),color_reason=color_reason,
                alpha_changed=False,order=['color','brightness','contrast'],
                note='Optional visual adjustment, not colorimetric restoration; the original remains unchanged.')


def keep_metadata(source: Path, output: Path, sidecar: Path) -> dict:
    """Copy writable source metadata, correcting fields made stale by the warp.

    PNG cannot represent every HEIF/JPEG container field. Preserve ExifTool's
    complete readable inventory separately and report its copy warnings.
    """
    executable=shutil.which('exiftool')
    if executable is None:
        raise ValueError('--keep-metadata requires ExifTool on PATH (macOS: brew install exiftool)')
    inventory=subprocess.run([executable,'-j','-G1','-a','-u','-struct',str(source)],
                             capture_output=True,check=True,timeout=60)
    records=json.loads(inventory.stdout)
    for record in records:
        record.pop('SourceFile',None)
        for key in list(record):
            if key.startswith(('File:Directory','File:FileName','System:Directory','System:FileName')):
                record.pop(key,None)
    sidecar.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    image=cv2.imread(str(output),cv2.IMREAD_UNCHANGED)
    h,w=image.shape[:2]
    result=subprocess.run([executable,'-overwrite_original','-TagsFromFile',str(source),'-all:all',
        '--ICC_Profile:all','--ColorSpace','--Orientation','--ExifImageWidth','--ExifImageHeight',
        '--ThumbnailImage','--PreviewImage','--JpgFromRaw','--OtherImage',
        '-EXIF:Orientation#=1','-EXIF:ExifImageWidth='+str(w),'-EXIF:ExifImageHeight='+str(h),
        '-EXIF:ColorSpace#=1','-XMP-tiff:Orientation#=1',
        '-XMP-tiff:ImageWidth='+str(w),'-XMP-tiff:ImageHeight='+str(h),
        '-XMP-exif:ExifImageWidth='+str(w),'-XMP-exif:ExifImageHeight='+str(h),str(output)],
        capture_output=True,timeout=60)
    if result.returncode:
        raise RuntimeError('Metadata copy failed: '+result.stderr.decode(errors='replace'))
    return dict(enabled=True,tool='ExifTool',source_inventory_file=sidecar.name,
                policy='Copy writable EXIF/XMP/IPTC and other supported tags; keep output sRGB; update orientation and dimensions; omit stale embedded previews.',
                copy_warnings=result.stderr.decode(errors='replace').strip(),
                includes_sensitive_tags=True,
                limitation='Container-only/read-only tags cannot all be re-embedded in PNG; readable originals are retained in the metadata JSON inventory.')


def finish(source: Path, output: Path, args, work: Path) -> dict:
    all_adjustments=getattr(args,'auto_adjust',False)
    adjustment=adjust(output,contrast=all_adjustments or getattr(args,'auto_contrast',False),
                      brightness=all_adjustments or getattr(args,'auto_brightness',False),
                      color=all_adjustments or getattr(args,'auto_color',False))
    metadata=(keep_metadata(source,output,work/'source-metadata.json') if getattr(args,'keep_metadata',False)
              else dict(enabled=False,policy='Source metadata stripped; sRGB encoding declared'))
    return dict(adjustments=adjustment,metadata=metadata)
