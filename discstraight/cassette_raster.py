"""Cassette orientation and one continuous-coordinate final color warp."""
from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

from .cassette import plane_to_source
from .cassette_crop import crop_alpha
from .imaging import run, standardize_png_metadata
from .ocr import recognize


def analyze_orientation(rgb: np.ndarray, geometry: dict, work: Path, cache: Path, languages: str,
                        *, minimum_margin: float = .2, policy: str = 'balanced', backend: str = 'auto') -> dict:
    w,h=geometry['plane_size_px']; scale=min(1,1400/w)
    ow,oh=math.ceil(w*scale),math.ceil(h*scale)
    y,x=np.mgrid[:oh,:ow];points=np.stack([x/scale,y/scale],axis=-1)
    source=plane_to_source(points,geometry)
    view=cv2.remap(rgb,source[...,0].astype('float32'),source[...,1].astype('float32'),cv2.INTER_CUBIC,
                   borderMode=cv2.BORDER_CONSTANT,borderValue=(255,255,255))
    candidates=[]
    for angle in [0,180]:
        image=view if angle==0 else view[::-1,::-1]
        path=work/f'cassette-ocr-{angle}.png';cv2.imwrite(str(path),cv2.cvtColor(image,cv2.COLOR_RGB2BGR))
        data=recognize(path,languages,cache,backend);rows=[]
        for row in data['rows']:
            text=row['text'];letters=sum(c.isalpha() for c in text)
            p=np.array([row['bottom_left'],row['bottom_right'],row['top_right'],row['top_left']])*[ow,oh]
            baseline=p[1]-p[0];tilt=math.degrees(math.atan2(baseline[1],baseline[0]))
            height=float(np.linalg.norm(p[3]-p[0]));confidence=float(row['confidence'])
            if letters<2 or confidence<.35 or abs(tilt)>25:continue
            score=min(32,letters)*confidence**2
            if policy=='balanced':score*=min(1.5,math.sqrt(height/max(8,oh*.035)))
            rows.append(dict(text=text,score=score,confidence=confidence,height_px=height,baseline_tilt_degrees=tilt))
        # Saturation limits the advantage of long legal blocks; final rotation
        # stays locked to body geometry, not an artistic text baseline.
        weights=sorted([r['score'] for r in rows],reverse=True)
        score=sum(weights[:5])+sum(weights[5:])*.2 if policy=='balanced' else sum(weights)
        candidates.append(dict(clockwise_degrees=angle,score=score,rows=rows))
    candidates.sort(key=lambda c:-c['score']);best=candidates[0];second=candidates[1]
    margin=(best['score']-second['score'])/max(best['score'],1e-9)
    reasons=[]
    if best['score']<8:reasons.append('too_little_readable_text')
    if margin<minimum_margin:reasons.append('competing_text_directions')
    if data.get('missing_languages'):reasons.append('requested_ocr_language_unavailable')
    if best['rows'] and np.median([abs(r['baseline_tilt_degrees']) for r in best['rows']])>3:
        reasons.append('text_slant_differs_from_shell_edges')
    return dict(clockwise_degrees=best['clockwise_degrees'],status='review_required' if reasons else 'accepted',
                reasons=reasons,relative_margin=margin,candidates=candidates,
                rotation_coordinate_space='rectified_cassette_plane',
                policy=policy,
                ocr={k:data.get(k) for k in ['engine','revision','languages','missing_languages']},
                fine_text_rotation_applied=False,
                note='Two opposed OCR views. Body long edges stay horizontal; decorative text and depth-induced slant are preserved.')


def lanczos_sample(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Separable Lanczos3, floating-point phases (no 1/32-pixel map quantization)."""
    ix=np.floor(x).astype('int32');iy=np.floor(y).astype('int32')
    shifts=np.arange(-2,4)
    wx=np.sinc(x[...,None]-(ix[...,None]+shifts))*np.sinc((x[...,None]-(ix[...,None]+shifts))/3)
    wy=np.sinc(y[...,None]-(iy[...,None]+shifts))*np.sinc((y[...,None]-(iy[...,None]+shifts))/3)
    wx=wx.astype('float32');wy=wy.astype('float32')
    wx/=wx.sum(axis=-1,keepdims=True);wy/=wy.sum(axis=-1,keepdims=True)
    result=np.zeros((*x.shape,image.shape[2]),dtype='float32')
    for j,dy in enumerate(shifts):
        yy=iy+dy;row_valid=(yy>=0)&(yy<image.shape[0]);yy=np.clip(yy,0,image.shape[0]-1)
        for i,dx in enumerate(shifts):
            xx=ix+dx;valid=row_valid&(xx>=0)&(xx<image.shape[1]);xx=np.clip(xx,0,image.shape[1]-1)
            weight=wx[...,i]*wy[...,j]*valid
            result+=image[yy,xx]*weight[...,None]
    return result


def map_metrics(geometry: dict) -> dict:
    w,h=geometry['plane_size_px'];y,x=np.mgrid[0:h:17j,0:w:25j];points=np.stack([x,y],axis=-1)
    center=plane_to_source(points,geometry)
    dx=plane_to_source(points+[.5,0],geometry)-plane_to_source(points-[.5,0],geometry)
    dy=plane_to_source(points+[0,.5],geometry)-plane_to_source(points-[0,.5],geometry)
    jac=np.stack([dx,dy],axis=-1);det=np.linalg.det(jac)
    if not np.isfinite(center).all() or np.min(det)<=0:
        raise ValueError('Combined cassette mapping folds or is nonfinite')
    singular=np.linalg.svd(jac,compute_uv=False)
    maximum=float(singular.max())
    if maximum>3:raise ValueError('Cassette correction exceeds supported local minification')
    return dict(minimum_jacobian_determinant=float(det.min()),maximum_source_pixels_per_output_pixel=maximum,
                minimum_source_pixels_per_output_pixel=float(singular.min()),
                footprint_samples_per_axis=1 if maximum<=1.05 else math.ceil(maximum))


def render_cassette(normalized: Path, target: Path, source_shape: tuple[int,int], geometry: dict,
                    crop: dict, *, flip: bool, feather: float = 1, depth: int = 16) -> dict:
    h,w=source_shape;metrics=map_metrics(geometry)
    raw=run(['magick',str(normalized),'-colorspace','RGB','-depth','16','-endian','LSB','rgb:-'],binary=True)
    rgb=np.frombuffer(raw,dtype='<u2').reshape(h,w,3).astype('float32')/65535;del raw
    # Every original pixel participates. This fourth channel records source
    # image availability only; no object mask or color key precedes the warp.
    image=np.dstack([rgb,np.ones(source_shape,np.float32)]);del rgb
    bw,bh=geometry['plane_size_px']
    left,top,right,bottom=crop['bounds_px'];pad=max(2,math.ceil(feather/2)+1)
    if flip:
        left,top,right,bottom=bw-right,bh-bottom,bw-left,bh-top
    # Two transparent pixels for file consumers, no millimeter-wide dark frame.
    origin=np.array([left-pad,top-pad])
    ow,oh=math.ceil(right-left)+2*pad+1,math.ceil(bottom-top)+2*pad+1
    if ow*oh>40_000_000:raise ValueError('Cassette output would exceed 40 MP')
    output=np.zeros((oh,ow,4),np.uint16)
    samples=metrics['footprint_samples_per_axis'];offsets=(np.arange(samples)+.5)/samples-.5
    source_clipped = 0
    for start in range(0,oh,48):
        y,x=np.mgrid[start:min(oh,start+48),:ow]
        total=np.zeros((*x.shape,image.shape[2]),np.float32)
        for sy in offsets:
            for sx in offsets:
                px=x+origin[0]+sx;py=y+origin[1]+sy
                if flip:px=bw-px;py=bh-py
                source=plane_to_source(np.stack([px,py],axis=-1),geometry)
                total+=lanczos_sample(image,source[...,0],source[...,1])/(samples*samples)
        px=x+origin[0];py=y+origin[1]
        if flip:px=bw-px;py=bh-py
        a=crop_alpha(px,py,crop,feather)
        # A tightly framed photograph may lack pixels at a virtual corner.
        # This is source-canvas coverage, never a traced object silhouette.
        source=plane_to_source(np.stack([px,py],axis=-1),geometry)
        coverage=np.clip(np.minimum.reduce([source[...,0]+.5,w-.5-source[...,0],
                                            source[...,1]+.5,h-.5-source[...,1]]),0,1)
        source_clipped += int(np.count_nonzero((a>0)&(coverage<1)))
        a *= coverage
        if np.any((a>1e-4)&(total[...,3]<=1e-6)):
            raise ValueError('Straight crop contains pixels without source color support')
        linear=np.divide(total[...,:3],total[...,3,None],out=np.zeros_like(total[...,:3]),where=total[...,3,None]>1e-6)
        linear=np.clip(linear,0,1)
        srgb=np.where(linear<=.0031308,12.92*linear,1.055*np.power(linear,1/2.4)-.055)
        output[start:start+len(y),:,:3]=np.rint(np.clip(srgb,0,1)*65535).astype('uint16')
        output[start:start+len(y),:,3]=np.rint(a*65535).astype('uint16')
    output[:,:,:3][output[:,:,3]==0]=0
    bgra=output[:,:,[2,1,0,3]]
    if depth==8:bgra=np.rint(bgra.astype(float)/257).astype('uint8')
    bgra[:,:,:3][bgra[:,:,3]==0]=0
    if not cv2.imwrite(str(target),bgra,[cv2.IMWRITE_PNG_COMPRESSION,6]):raise RuntimeError('Could not encode cassette PNG')
    standardize_png_metadata(target)
    return dict(width=ow,height=oh,source_boundary_clipped_pixels=source_clipped,
                exterior_background_removal='final body rectangle and supported measured corner arcs',
                source_pixels_masked_before_warp=False,
                alpha_depends_on_image_colors=False,
                body_frame_px=dict(left=-origin[0],top=-origin[1],width=bw,height=bh),
                alpha_frame_px=dict(left=pad,top=pad,width=right-left,height=bottom-top),
                output_origin_in_rectified_plane_px=origin.tolist(),transparent_padding_px=pad,
                pixels_per_mm=geometry['pixels_per_mm'],body_aspect_ratio=100.4/63.8,
                source_to_output_is_homography_only=not(geometry['lens']['applied'] or geometry['conformance']['applied']),
                flip_180_degrees=flip,source_to_plane_matrix=geometry['source_to_plane_matrix'],
                map_metrics=metrics,
                resampling='One warp of unmasked original pixels in linear RGB; continuous-phase Lanczos3 with bounded footprint supersampling; analytic body and measured-corner alpha applied only after warp.',
                mapping='Output plus logged plane origin -> optional 180-degree flip -> logged boundary blend -> inverse homography -> inverse division lens model -> source',
                feather_policy='Centered transition at the final body rectangle and fitted corner arcs; no color key, pixel silhouette, or body inset.')
