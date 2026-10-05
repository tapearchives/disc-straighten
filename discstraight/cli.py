"""Batch command, provenance logs, and explicit review outcomes."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import datetime
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import numpy as np
import scipy
import cv2

from . import __version__
from .geometry import detect
from .imaging import gray_pixels, normalize, render, run, sha256
from .orientation import orient
from .perspective import detect_perspective, detect_scan_pair, PerspectiveDetectionError
from .preferences import OutputPreferences, load_preferences, output_folder, preferences_path, save_preferences

EXTENSIONS = {'.jpg','.jpeg','.png','.tif','.tiff','.webp','.bmp'}


class CommandParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1,f'{self.prog}: error: {message}\n')


def circle(value: str) -> list[float]:
    try:
        numbers = [float(v) for v in value.split(',')]
        if len(numbers)!=3 or not all(math.isfinite(v) for v in numbers) or numbers[2]<=0:
            raise ValueError()
        return numbers
    except ValueError:
        raise argparse.ArgumentTypeError('Use finite x,y,r values with positive radius') from None


def finite(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError('Value must be finite')
    return number


def cassette_corners(value: str) -> np.ndarray:
    try:
        points=np.array([float(v) for v in value.split(',')]).reshape(4,2)
        if (not np.isfinite(points).all() or abs(cv2.contourArea(points.astype('float32')))<100
                or not cv2.isContourConvex(points.astype('float32'))):
            raise ValueError()
        return points
    except ValueError:
        raise argparse.ArgumentTypeError('Use eight finite numbers: x1,y1,x2,y2,x3,y3,x4,y4 around the main body') from None


def parser() -> argparse.ArgumentParser:
    p = CommandParser(prog='disc-straighten',description='Flatten optical discs and compact cassettes; save transparent PNGs and geometry logs. Originals are preserved.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''Examples (Windows CMD: use disc-straighten.cmd):
  disc-straighten "tape photos" --media auto --preview
  disc-straighten --set-output-relative output
  disc-straighten --set-output-fixed "/Volumes/Archive/Prepared Images"
  disc-straighten --show-preferences
  disc-straighten "tape photos" --media cassette -o processed --preview
  disc-straighten photo.jpg --media cassette --cassette-crop rectangle -o reviewed
  disc-straighten disc.jpg --media auto --ocr tesseract --languages eng -o processed
  disc-straighten disc.jpg --ocr none -o visual-deskew
  disc-straighten mini-cd.jpg --disc-size 80 -o processed
  disc-straighten tape.jpg --media cassette --angle 0 -o manual

Cassettes: fit straight sides, intersect corners, rectify to 100.4:63.8,
then crop with measured corner arcs when source AR is within 5%.
Lens correction is off by default. Unsupported corners remain square.
Discs automatically try -45 to +45 degree visual deskew if OCR cannot run.
Exit codes: 0 = completed; 2 = images saved, review needed; 1 = failure.
Default destination: output beside each input; images and JSON logs stay together.
Saved preferences change that default. -o overrides them for this run only.
See README.md, WINDOWS.md and USAGE.md for setup and examples.''')
    p.add_argument('inputs',nargs='*',help='Raster files, directories (nonrecursive), or HTTP(S) image URLs')
    p.add_argument('-o','--output',type=Path,help='Override saved destination for this run; default: output beside each input')
    preferences = p.add_mutually_exclusive_group()
    preferences.add_argument('--show-preferences',action='store_true',help='Print shared app/CLI output preferences as JSON')
    preferences.add_argument('--set-output-relative',metavar='FOLDER',help='Save a destination relative to each input folder (default: output)')
    preferences.add_argument('--set-output-fixed',type=Path,metavar='FOLDER',help='Save a fixed destination for all inputs')
    p.add_argument('--media',choices=['disc','cassette','auto'],default='disc',help='Disc is the compatibility default; cassette and auto enable the reviewed cassette beta')
    p.add_argument('--debow',choices=['auto','off','conform'],default='off',help='Cassette geometry: straight-line perspective only (default off), or explicit experimental auto/conform')
    p.add_argument('--cassette-corners',type=cassette_corners,help='Reviewed main-body corners in EXIF-normalized source pixels; excludes guide projections')
    p.add_argument('--cassette-crop',choices=['auto','rectangle'],default='auto',help='Auto fits measured corner arcs for compact cassette AR; rectangle retains square virtual corners')
    p.add_argument('--ocr',choices=['auto','vision','tesseract','none'],default='auto',help='Auto uses Vision on macOS, Tesseract elsewhere; unavailable OCR defaults to +/-45 degree visual disc deskew. None forces that fallback; cassettes then need --angle')
    p.add_argument('--languages',default='en-US,ru-RU',help='Comma-separated languages: en-US,ru-RU; Tesseract also accepts eng,rus')
    p.add_argument('--orientation-policy',choices=['balanced','majority'],default='balanced',help='Balanced favors prominent text; majority counts all capped text votes')
    p.add_argument('--min-margin',type=finite,default=.20,help='Review if orientation score margin is below this fraction')
    p.add_argument('--angle',type=finite,help='Bypass OCR; clockwise for discs, 0 or 180 after body rectification for cassettes')
    p.add_argument('--perspective',choices=['auto','on','off'],default='auto',
                   help='Auto-detect perspective (default); on requires a measured rim/aperture pair')
    p.add_argument('--disc-size',choices=['auto','120','80'],default='auto',
                   help='Nominal outer diameter in mm; auto compares both 15 mm aperture ratios')
    p.add_argument('--geometry-policy',choices=['nominal','measured'],default='nominal',
                   help='Nominal enforces concentric circles and the exact 15/120 or 15/80 ratio')
    p.add_argument('--outer',type=circle,help='Reviewed physical outer circle x,y,r in EXIF-normalized source pixels')
    p.add_argument('--hole',type=circle,help='Reviewed spindle circle x,y,r; independent of outer circle')
    p.add_argument('--feather',type=finite,default=1,help='Smoothstep transition width in output pixels; cassette minimum 1, centered on the final rectangle')
    p.add_argument('--outer-inset',type=finite,default=0,help='Disc outer-radius reduction in pixels (default: 0)')
    p.add_argument('--hole-expansion',type=finite,default=0,help='Disc hole-radius increase in pixels (default: 0)')
    p.add_argument('--depth',type=int,choices=[8,16],default=16,help='PNG bits per channel (default: 16)')
    p.add_argument('--preview',action='store_true',help='Also export a small preview (white background for cassettes)')
    p.add_argument('--overwrite',action='store_true',help='Replace this tool\'s existing outputs')
    p.add_argument('--version',action='version',version=__version__)
    return p


def expand(inputs: list[str]) -> list[str]:
    expanded = []
    for item in inputs:
        if urlsplit(item).scheme.lower() in {'http','https'}:
            expanded.append(item)
        elif Path(item).is_dir():
            expanded.extend(str(p.resolve()) for p in sorted(Path(item).iterdir())
                            if p.is_file() and p.suffix.lower() in EXTENSIONS)
        else:
            expanded.append(str(Path(item).resolve()))
    return list(dict.fromkeys(expanded))


def source_name(item: str) -> str:
    part = unquote(urlsplit(item).path) if urlsplit(item).scheme in {'http','https'} else item
    name = re.sub(r'[^\w.-]+','-',Path(part).stem,flags=re.UNICODE).strip('.-')[:100]
    while len(name.encode('utf-8'))>180:
        name = name[:-1]
    return name or 'disc'


def acquire(item: str, work: Path) -> tuple[Path,dict]:
    parts = urlsplit(item)
    remote = parts.scheme.lower() in {'http','https'}
    suffix = Path(unquote(parts.path) if remote else item).suffix.lower()
    if suffix not in EXTENSIONS:
        raise ValueError('Expected JPEG, PNG, TIFF, WebP, or BMP input')
    source = work/f'input{suffix}'
    if remote:
        url = urlunsplit((parts.scheme,parts.netloc,quote(unquote(parts.path),safe='/'),parts.query,''))
        request = Request(url,headers={'User-Agent':f'DiscStraighten/{__version__}'})
        size = 0
        with urlopen(request,timeout=30) as response, source.open('wb') as stream:
            while chunk := response.read(1024*1024):
                size += len(chunk)
                if size>100*1024*1024:
                    raise ValueError('Image download exceeds 100 MiB')
                stream.write(chunk)
    else:
        original = Path(item)
        if not original.is_file():
            raise ValueError(f'Input does not exist: {item}')
        shutil.copyfile(original,source)
    return source, dict(input=item,sha256=sha256(source),bytes=source.stat().st_size)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def measure_geometry(gray: np.ndarray, args: argparse.Namespace) -> tuple[dict,dict,np.ndarray | None]:
    """Normalize both rings, or retain measured geometry when explicitly selected."""
    if args.geometry_policy=='nominal' and (args.perspective=='off' or args.outer or args.hole):
        raise ValueError('Source-circle overrides and --perspective off require --geometry-policy measured; '
                         'nominal geometry needs both measured physical ellipses')
    mode = args.perspective
    if args.outer or args.hole:
        mode = 'off'
    attempt = dict(requested_mode=args.perspective,applied=False,
                   reason='manual_source_circles' if args.outer or args.hole else 'disabled')
    pair = None; suspected = False
    if mode!='off':
        try:
            pair = detect_perspective(gray,disc_size=args.disc_size,geometry_policy=args.geometry_policy)
            attempt.update(reason='below_rectification_threshold',
                           source_axis_ratio=pair['rectification']['source_axis_ratio'],
                           perspective_strength=pair['rectification']['perspective_strength'])
        except PerspectiveDetectionError as error:
            suspected = error.suspected
            attempt.update(reason='no_usable_concentric_pair',detail=str(error))
            if args.geometry_policy=='nominal':
                pair = detect_scan_pair(gray,disc_size=args.disc_size)
                attempt['reason'] = 'scan_seeded_physical_ellipse_pair'
            elif mode=='on':
                raise
    if pair is None or (mode=='auto' and not pair['needs_rectification']):
        try:
            geometry = detect(gray,args.outer,args.hole,disc_size=args.disc_size)
        except ValueError:
            if pair is None:
                raise
            attempt['reason'] = 'pair_supported_but_circle_detector_failed'
        else:
            geometry['coordinate_space'] = 'normalized_source'
            if suspected:
                geometry['warnings'].append('possible_perspective_without_usable_spindle_pair')
            return geometry,attempt,None
    rectification = pair['rectification']
    geometry = dict(outer_circle=rectification['plane_outer_circle'],
                    spindle_circle=rectification['plane_spindle_circle'],
                    source_outer_ellipse=pair['outer_ellipse'],source_spindle_ellipse=pair['spindle_ellipse'],
                    projected_physical_center_px=rectification['projected_physical_center_px'],
                    disc_profile=rectification['disc_profile'],
                    coordinate_space='rectified_disc_plane',center_separation_px=0.,
                    source_ellipse_center_separation_px=float(np.linalg.norm(
                        np.array(pair['outer_ellipse']['center_px'])-pair['spindle_ellipse']['center_px'])),
                    warnings=pair['warnings'],diagnostics=pair['diagnostics'])
    attempt.update(applied=True,reason='nominal_annulus_normalization' if args.geometry_policy=='nominal' else
                   ('forced' if mode=='on' else 'measured_projective_geometry'),
                   **rectification)
    return geometry,attempt,np.array(rectification['source_to_plane_matrix'])


def process(item: str, stem: str, args: argparse.Namespace, cache: Path) -> dict:
    targets = {key:args.output/f'{stem}{suffix}' for key,suffix in
               [('image','-straightened.png'),('log','-straightened.json'),
                ('orientation','-orientation.json'),('preview','-preview.png')]}
    if not args.overwrite and any(path.exists() for path in targets.values()):
        raise FileExistsError(f'Output already exists for {stem}; use --overwrite or a new output folder')
    if any(Path(item).resolve()==path.resolve() for path in targets.values()):
        raise ValueError('Refusing to overwrite the input image')
    progress = lambda message: print(f'[{stem}] {message}',file=sys.stderr,flush=True)
    with tempfile.TemporaryDirectory(prefix='.disc-work-',dir=args.output) as directory:
        work = Path(directory)
        progress('Reading and normalizing the source image')
        source,source_log = acquire(item,work)
        normalized = work/'normalized.miff'
        metadata = normalize(source,normalized); source_log.update(metadata)
        gray = gray_pixels(normalized,metadata['width'],metadata['height'])
        cassette_geometry=None;selected_media=args.media;selection_seconds=0.
        if selected_media=='auto':
            from .cassette import detect_cassette
            selection_started=time.perf_counter()
            try:
                candidate=detect_cassette(gray,debow=args.debow,corners=args.cassette_corners)
            except ValueError:
                selected_media='disc'
            else:
                selected_media='cassette' if candidate['detection_score']>=.65 else 'disc'
                cassette_geometry=candidate if selected_media=='cassette' else None
            selection_seconds=time.perf_counter()-selection_started
        if selected_media=='cassette':
            from .cassette_workflow import process_cassette
            return process_cassette(normalized,source_log,gray,args,work,cache,targets,progress,
                                    geometry=cassette_geometry,selection_seconds=selection_seconds)
        geometry,perspective,matrix = measure_geometry(gray,args)
        del gray
        if matrix is not None:
            progress('Physical rings normalized; reading text in the rectified disc plane')
        if args.angle is None:
            orientation = orient(normalized,geometry['outer_circle'],work,cache,
                                 languages=args.languages,policy=args.orientation_policy,
                                 minimum_margin=args.min_margin,progress=progress,
                                 rectification_matrix=matrix,spindle=geometry['spindle_circle'],backend=args.ocr)
        else:
            orientation = dict(clockwise_degrees=args.angle,status='user_override',
                               reasons=[],candidates=[],mixed_directions=None)
        angle = orientation['clockwise_degrees']
        orientation['rotation_coordinate_space'] = geometry['coordinate_space']
        outer = dict(center_px=geometry['outer_circle']['center_px'],
                     radius_px=geometry['outer_circle']['radius_px']-args.outer_inset)
        hole = dict(center_px=geometry['spindle_circle']['center_px'],
                    radius_px=geometry['spindle_circle']['radius_px']+args.hole_expansion)
        if outer['radius_px']<=hole['radius_px']+args.feather or hole['radius_px']<=args.feather/2:
            raise ValueError('Knockout offsets leave invalid circle geometry')
        size = math.ceil(outer['radius_px']*2+16)
        size += size%2
        if size**2>40_000_000:
            raise ValueError('Output would exceed 40 MP; review circle geometry')
        progress(f'Rendering one final warp, {angle:+.3f} degrees clockwise')
        output = work/'output.png'
        mapped = render(normalized,output,outer,hole,angle,size=size,feather=args.feather,depth=args.depth,
                        rectification_matrix=matrix)
        preview = work/'preview.png'
        make_preview = args.preview or (args.overwrite and targets['preview'].exists())
        if make_preview:
            run(['magick',str(output),'-background','#20252c','-alpha','remove','-alpha','off',
                 '-resize','900x900>','-depth','8',str(preview)])
        warnings = geometry['warnings']+orientation.get('reasons',[])
        summary = {k:v for k,v in orientation.items() if k!='unique_text_regions'}
        profile = geometry['disc_profile']
        applied_ratio = hole['radius_px']/outer['radius_px']
        result = dict(schema_version=4,tool=dict(name='disc-straighten',version=__version__),
                      created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),media='disc',
                      status='review_required' if warnings else 'accepted',warnings=warnings,
                      source=source_log,
                      coordinates='Pixel centers: top-left=(0,0), x right, y down. Source is EXIF-normalized. '
                                  'Rectified-disc-plane coordinates, when used, have the physical center at (0,0). '
                                  'Source ellipse fields and projected physical center always refer to source pixels.',
                      measurements={k:v for k,v in geometry.items() if k not in {'warnings','diagnostics'}},
                      geometry_method=('Robust physical-ellipse edges and two-concentric-circle projective rectification'
                                       if matrix is not None else
                                       'RANSAC rim hypotheses, independent radial subpixel edge fits, soft-L1 circle residuals'),
                      geometry_selection=geometry['diagnostics'].get('selection',
                                        'outermost coherent ellipse and compatible physical aperture' if matrix is not None else 'user_override'),
                      perspective=perspective,
                      lens_distortion=dict(applied=False,estimated=False,
                                           note='Disc branch does not estimate lens distortion; round output rings do not establish undistorted interior artwork.'),
                      geometry_policy=args.geometry_policy,
                      knockouts=dict(coordinate_space=geometry['coordinate_space'],
                                     outside_outer_circle=outer,inside_spindle_circle=hole,
                                     outer_inset_px=args.outer_inset,hole_expansion_px=args.hole_expansion,
                                     spindle_to_outer_radius_ratio=applied_ratio,
                                     nominal_ratio_preserved=math.isclose(applied_ratio,profile['nominal_radius_ratio'],rel_tol=1e-12),
                                     feather_full_width_px=args.feather,
                                     radius_definition='50 percent alpha contour; cubic smoothstep'),
                      rotation=summary,
                      output=dict(file=targets['image'].name,sha256=sha256(output),depth=args.depth,
                                  color_space='sRGB',alpha='straight/unassociated RGBA',
                                  circle_definition='Analytic Euclidean circles sampled on the output pixel grid; '
                                                    'radius is the continuous 50 percent alpha contour',**mapped),
                      resampling='one final EWA Lanczos3 warp in linear RGB; rectification and rotation composed; '
                                 'analytical output alpha; plane radius is geometric mean of source ellipse semiaxes',
                      limits=['Heuristics do not establish designer intent or absolute physical accuracy.',
                              'Nominal normalization requires visible, coplanar physical rim and 15 mm aperture of a 120 or 80 mm disc.',
                              'Exact output circles are an idealization; manufactured media and measured edges have tolerances.',
                              'Clear plastic inside the footprint remains opaque; only exterior and aperture are removed.',
                              'No calibrated lens correction, image synthesis, sharpening, or recovery of hidden/blurry detail.',
                              'Rim and hole fit residuals measure model agreement, not certified physical accuracy.',
                              'A review_required PNG uses the best current estimate and is provisional.'],
                      runtime=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,opencv=cv2.__version__,
                                   macOS=platform.mac_ver()[0],imagemagick=run(['magick','-version']).splitlines()[0]))
        write_json(work/'orientation.json',dict(**orientation,geometry_diagnostics=geometry['diagnostics']))
        write_json(work/'result.json',result)
        # Stage all artifacts before publishing the completed result log last.
        output.replace(targets['image'])
        (work/'orientation.json').replace(targets['orientation'])
        if make_preview:
            preview.replace(targets['preview'])
        (work/'result.json').replace(targets['log'])
        return result


def main(argv: list[str] | None = None) -> int:
    p = parser(); args = p.parse_args(argv)
    preference_action = args.show_preferences or args.set_output_relative is not None or args.set_output_fixed is not None
    if preference_action and args.inputs:
        p.error('Change or show preferences separately from processing images')
    try:
        if args.set_output_relative is not None:
            save_preferences(OutputPreferences(relative_folder=args.set_output_relative))
        elif args.set_output_fixed is not None:
            save_preferences(OutputPreferences(output_mode='fixed', fixed_folder=str(args.set_output_fixed.expanduser().resolve())))
        preferences = load_preferences() if args.output is None or preference_action else OutputPreferences()
        if preference_action:
            print(json.dumps(dict(schema=1, **asdict(preferences), preferences_file=str(preferences_path()))))
            return 0
    except (ValueError, OSError) as error:
        p.error(str(error))
    if not args.inputs:
        p.error('Provide images or a folder, or use -h for examples')
    args.languages=','.join(s.strip() for s in args.languages.split(',') if s.strip())
    if not args.languages:p.error('--languages must contain at least one language code')
    if not shutil.which('magick'):
        p.error('ImageMagick 7 must be on PATH. See README.md or WINDOWS.md for installation.')
    if not 0<args.feather<=20 or not 0<=args.min_margin<=1:
        p.error('--feather must be in (0,20]; --min-margin must be in [0,1]')
    if args.cassette_corners is not None and args.media!='cassette':
        p.error('--cassette-corners requires --media cassette')
    if args.media=='disc' and args.debow!='off':
        p.error('--debow auto/conform is a cassette option; disc lens correction is not implemented')
    if args.media=='cassette' and (args.perspective!='auto' or args.disc_size!='auto' or args.geometry_policy!='nominal'):
        p.error('--perspective, --disc-size, and --geometry-policy configure discs; cassette body rectification is always applied')
    if args.perspective=='on' and (args.outer or args.hole):
        p.error('--perspective on cannot use source-circle overrides; use automatic ellipses or --perspective off')
    if args.geometry_policy=='nominal' and (args.perspective=='off' or args.outer or args.hole):
        p.error('Source-circle overrides and --perspective off require --geometry-policy measured')
    items = expand(args.inputs)
    if not items:
        p.error('No supported raster images found')
    if len(items)>1 and any(v is not None for v in [args.outer,args.hole,args.angle,args.cassette_corners]):
        p.error('Explicit geometry or angle overrides apply to one input at a time')
    names = [source_name(item) for item in items]
    destinations = [output_folder(item,args.output,preferences) for item in items]
    keys = [(str(folder).casefold(),name.casefold()) for folder,name in zip(destinations,names)]
    if len(set(keys))!=len(keys):
        p.error('Inputs have colliding output names in the same destination; use separate folders or unique filenames')
    cache = Path(os.environ.get('DISC_STRAIGHTEN_CACHE',Path.home()/'.cache'/'disc-straighten'))
    status = 0
    for item,name,destination in zip(items,names,destinations):
        try:
            args.output = destination
            args.output.mkdir(parents=True,exist_ok=True)
            result = process(item,name,args,cache)
            if result['status']=='review_required' and status==0:
                status = 2
            print(json.dumps(dict(input=item,status=result['status'],
                                  clockwise_degrees=result['rotation']['clockwise_degrees'],
                                  image=str(args.output/result['output']['file']),warnings=result['warnings'])))
        except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as error:
            status = 1
            print(json.dumps(dict(input=item,status='failed',error=str(error))),file=sys.stderr)
    return status
