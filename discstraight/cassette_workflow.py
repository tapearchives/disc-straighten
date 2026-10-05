"""Cassette branch of the shared local CLI; explicit, reproducible 2D approximations."""
from __future__ import annotations

import datetime
import math
from pathlib import Path
import platform
import time

import cv2
import numpy as np

from . import __version__
from .cassette import detect_cassette, source_to_plane
from .cassette_raster import analyze_orientation, render_cassette, map_metrics
from .cassette_crop import body_crop
from .cassette_boundary import refine_outer_boundary
from .imaging import run, sha256


def process_cassette(normalized: Path, source_log: dict, gray: np.ndarray, args,
                     work: Path, cache: Path, targets: dict, progress, *, geometry: dict | None = None,
                     selection_seconds: float = 0.) -> dict:
    from .cli import write_json
    times={};start=time.perf_counter()
    if args.outer or args.hole or args.outer_inset or args.hole_expansion:
        raise ValueError('Disc circle and knockout options do not apply to a cassette')
    if args.feather<1:
        raise ValueError('Cassette feather must be at least 1 output pixel')
    if args.angle is not None and abs(args.angle/180-round(args.angle/180))>1e-8:
        raise ValueError('Cassette --angle selects 0 or 180 degrees after body rectification; arbitrary fine text rotation would tilt the body')
    progress('Tracing cassette body; excluding projections from calibration')
    if geometry is None:
        geometry=detect_cassette(gray,debow=args.debow,corners=args.cassette_corners)
    times['geometry_seconds']=time.perf_counter()-start+selection_seconds
    width,height=source_log['width'],source_log['height']
    raw=run(['magick',str(normalized),'-colorspace','sRGB','-depth','8','rgb:-'],binary=True)
    rgb=np.frombuffer(raw,dtype=np.uint8).reshape(height,width,3)
    start=time.perf_counter()
    if args.cassette_corners is None:
        geometry=refine_outer_boundary(rgb,geometry,debow=args.debow)
    from .cassette_corners import aspect_ratio_tag
    geometry['aspect_ratio']=aspect_ratio_tag(np.array(geometry['undistorted_source_corners_px']))
    times['geometry_seconds']+=time.perf_counter()-start
    start=time.perf_counter();progress('Setting final rectangular crop in the corrected body plane')
    mask=body_crop(gray,geometry,minimum_source_scale=map_metrics(geometry)['minimum_source_pixels_per_output_pixel'],feather=args.feather,corners=args.cassette_crop)
    times['crop_analysis_seconds']=time.perf_counter()-start
    start=time.perf_counter();progress('Comparing opposed text orientations in the flattened face')
    orientation=(analyze_orientation(rgb,geometry,work,cache,args.languages,minimum_margin=args.min_margin,policy=args.orientation_policy,backend=args.ocr)
                 if args.angle is None else dict(clockwise_degrees=args.angle%360,status='user_override',reasons=[],candidates=[]))
    times['orientation_seconds']=time.perf_counter()-start
    flip=orientation['clockwise_degrees']%360==180
    start=time.perf_counter();progress('Warping original pixels once, then applying the feathered rectangle')
    output=work/'output.png'
    mapped=render_cassette(normalized,output,gray.shape,geometry,mask,flip=flip,feather=args.feather,depth=args.depth)
    times['render_seconds']=time.perf_counter()-start
    preview=work/'preview.png';make_preview=args.preview or (args.overwrite and targets['preview'].exists())
    if make_preview:
        run(['magick',str(output),'-background','white','-alpha','remove','-alpha','off','-resize','1100x800>','-depth','8',str(preview)])
    for edge,points in zip(geometry['edges'],geometry['diagnostics']['edge_source_points_px']):
        corrected=source_to_plane(np.array(points),geometry)
        i=['top','right','bottom','left'].index(edge['side']);axis=1 if i%2==0 else 0
        expected=0 if i in [0,3] else geometry['plane_size_px'][axis]
        residual=corrected[:,axis]-expected
        edge['rms_after_correction_px']=float(np.sqrt(np.mean(residual**2)))
        edge['p95_absolute_error_after_correction_px']=float(np.percentile(abs(residual),95))
    q=np.array(geometry['undistorted_source_corners_px']);delta=q[1]-q[0]
    source_angle=-math.degrees(math.atan2(delta[1],delta[0]))+orientation['clockwise_degrees']
    source_angle=(source_angle+180)%360-180
    warnings=list(dict.fromkeys(geometry['warnings']+orientation.get('reasons',[])))
    if mapped['source_boundary_clipped_pixels']:
        warnings.append('rectified_frame_reaches_original_photo_boundary')
    if max(mask['residual_edge_p95_px']) > 1.:
        warnings.append('residual_edge_alignment_requires_review')
    if mask['corner_fits'] and any(not f['applied'] for f in mask['corner_fits']):
        warnings.append('some_corner_arcs_unresolved_kept_square')
    result=dict(schema_version=7,tool=dict(name='disc-straighten',version=__version__),
                created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),media='cassette',
                media_selection=dict(requested=args.media,selected='cassette',score=geometry['detection_score'],
                                     calibrated_probability=False),
                status='review_required' if warnings else 'accepted',warnings=warnings,source=source_log,
                geometry={k:v for k,v in geometry.items() if k!='diagnostics'},
                rotation=dict(clockwise_degrees=source_angle,canonical_flip_degrees=orientation['clockwise_degrees'],
                              note='Source long-axis rotation summary; the full transform is projective and may include nonlinear bow correction.'),
                output=dict(file=targets['image'].name,sha256=sha256(output),depth=args.depth,color_space='sRGB',alpha='straight/unassociated RGBA',**mapped),
                mask=mask,
                transform_notes=['Main shell face is corner-pinned to nominal 100.4 by 63.8 mm.',
                                 'All original pixels are warped before the final feathered body crop and supported measured corner arcs. No guessed radii, color-key or pixel silhouette alpha.',
                                 'Raised front, recessed reels and visible sidewalls retain depth parallax.',
                                 'Closed transparent material and photographed content behind openings are retained.',
                                 'No hidden geometry, texture, or sharp detail is synthesized.']+
                                (['Measured edge bow is conformed using a 2D boundary blend; its cause is not proven to be lens distortion.'] if geometry['conformance']['applied'] else []),
                timing=times,runtime=dict(python=platform.python_version(),opencv=cv2.__version__,macOS=platform.mac_ver()[0]))
    write_json(work/'orientation.json',dict(**orientation,geometry_diagnostics=geometry['diagnostics'],body_crop=mask))
    write_json(work/'result.json',result)
    output.replace(targets['image']);(work/'orientation.json').replace(targets['orientation'])
    if make_preview:preview.replace(targets['preview'])
    (work/'result.json').replace(targets['log'])
    return result
