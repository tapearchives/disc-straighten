"""ImageMagick I/O and a single alpha-aware, linear-light final warp."""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import subprocess
import struct
import zlib

import cv2
import numpy as np

SRGB = Path('/System/Library/ColorSync/Profiles/sRGB Profile.icc')


def srgb_profile() -> Path:
    candidates=[Path(os.environ.get('DISC_SRGB_PROFILE','__not_configured__')),SRGB,
                Path(os.environ.get('WINDIR','C:/Windows'))/'System32/spool/drivers/color/sRGB Color Space Profile.icm',
                Path('/usr/share/color/icc/colord/sRGB.icc')]
    for path in candidates:
        if path.is_file():return path
    raise ValueError('Embedded ICC input requires an sRGB profile. Set DISC_SRGB_PROFILE to a valid sRGB ICC/ICM file; see WINDOWS.md.')


def run(args: list[str], *, binary: bool = False) -> str | bytes:
    result = subprocess.run(args, capture_output=True, timeout=240)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-3000:])
    return result.stdout if binary else result.stdout.decode()


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def normalize(source: Path, target: Path) -> dict:
    raster=str(source)+('[0]' if source.suffix.lower() in {'.heic','.heif'} else '')
    # The CLI only accepts raster extensions and addresses resolved absolute paths.
    meta = run(['magick', 'identify', '-format',
                '%w|%h|%z|%[colorspace]|%[profiles]|%[orientation]|%[opaque]\n', raster])
    lines = meta.strip().splitlines()
    if len(lines) != 1:
        raise ValueError('Expected a single raster image, not multiple frames/pages')
    w, h, depth, space, profiles, orientation, opaque = lines[0].split('|')
    if int(w)*int(h) > 64_000_000 or min(int(w), int(h)) < 128:
        raise ValueError('Supported dimensions: at least 128 pixels per side, at most 64 MP')
    from .camera import read_camera
    camera = read_camera(source, run)
    args = ['magick', raster, '-auto-orient']
    if 'icc' in profiles.lower() or 'icm' in profiles.lower():
        args += ['-profile', str(srgb_profile())]
        color_note = 'Embedded ICC profile converted to system sRGB profile'
    else:
        color_note = 'Untagged RGB/gray interpreted as sRGB; other color spaces converted by ImageMagick'
    args += ['-colorspace', 'sRGB', '-strip', '-depth', '16', str(target)]
    run(args)
    width, height = map(int, run(['magick', 'identify', '-format', '%w %h', str(target)]).split())
    return dict(width=width, height=height, original_width=int(w), original_height=int(h),
                original_depth=int(depth), original_colorspace=space,
                original_exif_orientation=orientation, color_management=color_note,
                source_has_transparency=opaque.lower()!='true',
                source_alpha_policy='Preserve existing transparency; intersect it with the final geometric mask',
                camera=camera)


def gray_pixels(path: Path, width: int, height: int) -> np.ndarray:
    raw = run(['magick', str(path), '-background', 'white', '-alpha', 'remove',
               '-colorspace', 'Gray', '-depth', '8', 'gray:-'], binary=True)
    return np.frombuffer(raw, dtype=np.uint8).reshape(height, width)


def mapped_circle(circle: dict, pivot: list[float], angle: float, size: int, scale: float = 1) -> dict:
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    x, y = np.array(circle['center_px'])-pivot
    m = (size-1)/2
    return dict(center_px=[float(m+scale*(c*x-s*y)), float(m+scale*(s*x+c*y))],
                radius_px=float(scale*circle['radius_px']))


def alpha_expression(outer: dict, hole: dict, feather: float,
                     matrix: np.ndarray | None = None) -> str:
    ox, oy = outer['center_px']; hx, hy = hole['center_px']
    ro, rh = outer['radius_px'], hole['radius_px']
    prefix = ''; x,y = 'i','j'
    if matrix is not None:
        h = np.asarray(matrix)
        prefix = (f'dnom=({h[2,0]}*i+{h[2,1]}*j+{h[2,2]});'
                  f'xp=({h[0,0]}*i+{h[0,1]}*j+{h[0,2]})/max(1e-9,dnom);'
                  f'yp=({h[1,0]}*i+{h[1,1]}*j+{h[1,2]})/max(1e-9,dnom);')
        x,y = 'xp','yp'
    return (prefix+f'oo=min(1,max(0,({ro+feather/2}-hypot({x}-{ox},{y}-{oy}))/{feather}));'
            f'hh=min(1,max(0,(hypot({x}-{hx},{y}-{hy})-{rh-feather/2})/{feather}));'
            +('dnom<=0?0:' if matrix is not None else '')
            +'oo*oo*(3-2*oo)*hh*hh*(3-2*hh)')


def view_matrix(center: list[float], angle: float, size: int, scale: float = 1) -> np.ndarray:
    c,s = math.cos(math.radians(angle))*scale,math.sin(math.radians(angle))*scale
    x,y = center; m = (size-1)/2
    return np.array([[c,-s,m-c*x+s*y],[s,c,m-s*x-c*y],[0,0,1.]])


def projection_arguments(matrix: np.ndarray) -> str:
    # Logged matrices use integer pixel centers. ImageMagick's distortion API
    # instead uses image coordinates whose first pixel center is (0.5, 0.5).
    half = np.array([[1.,0,.5],[0,1,.5],[0,0,1]])
    h = half@matrix@np.linalg.inv(half)
    h /= h[2,2]
    return ','.join(f'{v:.17g}' for v in h.ravel()[:8])


def standardize_png_metadata(path: Path) -> None:
    """Keep encoded pixels unchanged; declare sRGB and remove stale source metadata."""
    signature = b'\x89PNG\r\n\x1a\n'
    temporary = path.with_suffix('.png-metadata')
    with path.open('rb') as source, temporary.open('wb') as target:
        if source.read(8)!=signature:
            raise ValueError('Renderer did not produce a PNG')
        target.write(signature)
        while True:
            header = source.read(8)
            if len(header)!=8:
                raise ValueError('Truncated rendered PNG')
            length,kind = struct.unpack('>I4s',header)
            body = source.read(length+4)
            if len(body)!=length+4:
                raise ValueError('Truncated rendered PNG chunk')
            if kind==b'IHDR' and (length!=13 or body[9]!=6):
                raise ValueError('Metadata cleanup expects the renderer\'s RGBA PNG')
            if kind in {b'IHDR',b'IDAT',b'IEND'}:
                target.write(header+body)
            if kind==b'IHDR':
                # The renderer has already converted pixels to standard sRGB.
                # An explicit PNG sRGB chunk avoids stripped/legacy ICC and
                # gamma properties changing how a viewer interprets the result.
                chunk = b'sRGB\x00'  # perceptual rendering intent
                target.write(struct.pack('>I',1)+chunk+struct.pack('>I',zlib.crc32(chunk)))
            if kind==b'IEND':
                break
    temporary.replace(path)


def alpha_canvas_bounds(alpha: np.ndarray) -> tuple[int, int, int, int]:
    """Tight canvas around encoded nonzero alpha; never trace or alter an edge."""
    rows = np.flatnonzero(np.any(alpha != 0, axis=1))
    columns = np.flatnonzero(np.any(alpha != 0, axis=0))
    if not len(rows) or not len(columns):
        raise ValueError('Rendered image has no visible pixels')
    return int(columns[0]), int(rows[0]), int(columns[-1]+1), int(rows[-1]+1)


def render(source: Path, target: Path, outer: dict, hole: dict, angle: float,
           *, size: int, feather: float, depth: int = 16,
           rectification_matrix: np.ndarray | None = None) -> dict:
    pivot = outer['center_px']; m = (size-1)/2
    out_outer = mapped_circle(outer, pivot, angle, size)
    out_hole = mapped_circle(hole, pivot, angle, size)
    matrix = view_matrix(pivot,angle,size)
    distortion = ['SRT',f'{pivot[0]+.5},{pivot[1]+.5} 1 {angle} {m+.5},{m+.5}']
    if rectification_matrix is not None:
        matrix = matrix@rectification_matrix
        matrix /= matrix[2,2]
        distortion = ['PerspectiveProjection',projection_arguments(matrix)]
    transparent = run(['magick','identify','-format','%[opaque]',str(source)]).strip().lower()!='true'
    final_alpha=alpha_expression(out_outer,out_hole,feather)
    if transparent:
        # Existing alpha participates in ImageMagick's alpha-aware warp. The
        # analytical annulus can remove pixels but must never fill a missing one.
        final_alpha='sourcealpha=a;'+final_alpha+'*sourcealpha'
    source_mask=[] if transparent else ['-channel','A','-fx',alpha_expression(outer,hole,feather,rectification_matrix),'+channel']
    args = ['magick', str(source), '-colorspace', 'RGB', '-alpha', 'set', *source_mask,
            '-virtual-pixel', 'transparent', '-filter', 'Lanczos', '-define', 'filter:lobes=3',
            '-define', f'distort:viewport={size}x{size}+0+0', '-distort', *distortion, '+repage',
            '-channel', 'A', '-fx', final_alpha, '+channel',
            '-colorspace', 'sRGB', '-channel', 'RGB', '-fx', f'a<=1.0/{2**depth-1}?0:u', '+channel',
            '-depth', str(depth), '-define', f'png:bit-depth={depth}',
            '-define', 'png:color-type=6', str(target)]
    run(args)
    # The warp's working margin is not part of the deliverable. Slice only
    # fully transparent rows/columns; keep every feather and source-alpha pixel.
    pixels = cv2.imread(str(target), cv2.IMREAD_UNCHANGED)
    if pixels is None or pixels.ndim != 3 or pixels.shape[2] != 4:
        raise ValueError('Renderer did not produce an RGBA image')
    left, top, right, bottom = alpha_canvas_bounds(pixels[...,3])
    if (left, top, right, bottom) != (0, 0, size, size):
        if not cv2.imwrite(str(target), pixels[top:bottom,left:right], [cv2.IMWRITE_PNG_COMPRESSION,6]):
            raise RuntimeError('Could not encode tightly framed disc PNG')
    shift = np.array([[1.,0,-left],[0,1,-top],[0,0,1]])
    matrix = shift@matrix
    for circle in (out_outer, out_hole):
        circle['center_px'] = (np.array(circle['center_px'])-[left,top]).tolist()
    standardize_png_metadata(target)
    return dict(outer_circle=out_outer, spindle_circle=out_hole, width=right-left, height=bottom-top,
                transparent_padding_px=0,
                working_canvas_trim_px=dict(left=left,top=top,right=size-right,bottom=size-bottom),
                canvas_policy='Tight nonzero-alpha bounds; no added border; all feather pixels preserved.',
                source_to_output_matrix=matrix.tolist())


def ocr_view(source: Path, target: Path, angle: float, center: list[float], radius: float,
             rectification_matrix: np.ndarray | None = None) -> dict:
    # All OCR trials are temporary views of the normalized original; never final masters.
    size = 1600
    scale = min(2.0, 1520/(2*radius))
    m = (size-1)/2
    distortion = ['SRT',f'{center[0]+.5},{center[1]+.5} {scale} {angle} {m+.5},{m+.5}']
    if rectification_matrix is not None:
        matrix = view_matrix(center,angle,size,scale)@rectification_matrix
        distortion = ['PerspectiveProjection',projection_arguments(matrix)]
    run(['magick', str(source), '-background', 'white', '-alpha', 'remove', '-alpha', 'off',
         '-virtual-pixel', 'white', '-filter', 'Lanczos', '-define', 'filter:lobes=3',
         '-define', f'distort:viewport={size}x{size}+0+0', '-distort', *distortion,
         # Temporary lossless PNGs favor encoding speed. Compression does not
         # change their decoded pixels; master PNG settings remain in render().
         '+repage', '-depth', '8', '-define', 'png:compression-level=1', str(target)])
    return dict(size=size, scale=scale, center=center, angle=angle)
