"""Catalog identity, sequence accounting and explicitly synthetic gap images."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import re

from .imaging import run, sha256
from . import __version__

RASTERS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp', '.bmp', '.heic', '.heif'}
MAX_RANGE = 10000
MAX_AUTOMATIC_GAPS = 1000


def sequence(codes: list[str], start: str | None = None, end: str | None = None) -> list[str]:
    """Only expand one bounded, fixed-width decimal namespace; never UPC ranges."""
    bounds = [x for x in (start, end) if x]
    values = codes + bounds
    if not values or any(not re.fullmatch(r'[0-9]{1,12}', x) for x in values):
        raise ValueError('Catalog sequences need numeric IDs (1–12 digits). Barcode strings are still preserved.')
    if len({len(x) for x in values}) != 1:
        raise ValueError('Catalog IDs and range limits must have the same digit width, including leading zeros.')
    low = int(start) if start else min(map(int, codes))
    high = int(end) if end else max(map(int, codes))
    count = high - low + 1
    if count < 1 or count > MAX_RANGE:
        raise ValueError(f'Choose an ascending catalog range of at most {MAX_RANGE:,} numbers.')
    found = sum(low <= int(x) <= high for x in set(codes))
    if count - found > MAX_AUTOMATIC_GAPS and not (start and end):
        raise ValueError('More than 1,000 gaps: set explicit catalog start/end limits before creating placeholders.')
    return [str(x).zfill(len(values[0])) for x in range(low, high + 1)]


def inventory(folder: Path, start: str | None = None, end: str | None = None) -> dict:
    """Read only named masters, not previews/logs; ambiguous duplicates block."""
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise ValueError('Choose an existing output folder or a folder of catalog-named images.')
    images = folder / 'output-images' if (folder / 'output-images').is_dir() else folder
    found: dict[str, dict[str, dict]] = {}
    ignored = []; superseded = []
    for path in sorted(images.iterdir(), key=lambda p: p.name.casefold()):
        if not path.is_file() or path.name.startswith('.') or path.suffix.lower() not in RASTERS:
            continue
        match = re.fullmatch(r'([0-9]{1,12})([AB])?(?:[- _]+(.*))?', path.stem, re.I)
        if not match:
            ignored.append(path.name)
            continue
        code, side, extra = match.groups()
        missing = bool(extra and re.search(r'\bMISSING\b', extra, re.I))
        # Do not silently promote "MISLABELED", alternates or arbitrary suffixes.
        if extra and not missing and extra.lower() != 'straightened':
            ignored.append(path.name)
            continue
        side = (side or '').upper()
        if not side and not missing:
            ignored.append(path.name)
            continue
        item = dict(catalog=code, side=side or None, kind='missing' if missing else 'image',
                    path=str(path), reason='existing_placeholder' if missing else None)
        slots = found.setdefault(code, {})
        if side in slots:
            raise ValueError(f'Duplicate catalog slot {code}{side}: {Path(slots[side]["path"]).name} and {path.name}. Resolve it first.')
        slots[side] = item
    log_folder = folder.parent / 'output-json' if folder.name == 'output-images' else folder / 'output-json'
    anchor_path = log_folder / 'catalog-anchors.json'
    anchors = json.loads(anchor_path.read_text(encoding='utf-8')).get('references', []) if anchor_path.is_file() else []
    for anchor in anchors:
        code = anchor['catalog']
        if not re.fullmatch(r'[0-9]{1,12}', code):
            continue
        found.setdefault(code, {})
    if not found and not (start and end):
        raise ValueError('No catalog-named images found. Enable Name barcode pairs first, or use names such as 104001A.png and 104001B.png.')
    codes = sequence(list(found), start, end)
    entries = []
    for code in codes:
        slots = found.get(code, {})
        if '' in slots and len(slots) > 1:
            # A real side is stronger evidence than an older whole-number dummy.
            superseded.append(slots.pop('')['path'])
        if not slots or '' in slots:
            entries.append(slots.get('', dict(catalog=code, side=None, kind='missing', path=None,
                                              reason='barcode_reference_media_unverified' if any(a['catalog']==code for a in anchors)
                                              else 'catalog_sequence_gap')))
        else:
            for side in ('A', 'B'):
                entries.append(slots.get(side, dict(catalog=code, side=side, kind='missing', path=None,
                                                    reason='side_image_unavailable')))
    for item in entries:
        item['caption'] = (item['catalog'] + (item['side'] or '') +
                           (' MISSING -\nPLACEHOLDER' if item['kind'] == 'missing' else ''))
    return dict(schema=1, folder=str(folder), image_folder=str(images), start=codes[0], end=codes[-1],
                catalog_count=len(codes), image_count=sum(x['kind'] == 'image' for x in entries),
                missing_count=sum(x['kind'] == 'missing' for x in entries), entries=entries,
                ignored_files=ignored, superseded_placeholders=superseded,
                barcode_references=anchors,
                excluded_catalog_ids=sorted(set(found)-set(codes)))


def placeholder(path: Path) -> None:
    """A documented dummy image, not an alteration or reconstruction of a photo."""
    from PIL import Image, ImageDraw, ImageFont
    import reportlab
    font = ImageFont.truetype(str(Path(reportlab.__file__).parent / 'fonts' / 'VeraBd.ttf'), 152)
    image = Image.new('RGB', (1200, 780), '#ffff00')
    draw = ImageDraw.Draw(image)
    for text, y in zip(('MISSING', 'MEDIA', 'IMAGE'), (120, 306, 492)):
        draw.text((600, y), text, font=font, fill='#0000ff', anchor='mt', stroke_width=2)
    with path.open('xb') as stream:
        image.save(stream, format='PNG')


def materialize_gaps(root: Path, start: str | None = None, end: str | None = None) -> dict:
    """Run after barcode naming, in a fresh derivative folder. Originals untouched."""
    report = inventory(root, start, end)
    made = []
    for entry in report['entries']:
        if entry['path'] is not None:
            continue
        stem = entry['catalog'] + (entry['side'] or '') + ' MISSING - PLACEHOLDER'
        image = root / 'output-images' / (stem + '.png')
        log = root / 'output-json' / (stem + '.json')
        # Both filenames must be free before creating this two-file record.
        if image.exists() or log.exists():
            raise FileExistsError(f'Placeholder already exists: {stem}')
        image.parent.mkdir(parents=True, exist_ok=True); log.parent.mkdir(parents=True, exist_ok=True)
        placeholder(image)
        entry.update(path=str(image), generated=True)
        try:
            with log.open('x', encoding='utf-8') as stream:
                json.dump(dict(schema=1, status='placeholder', synthetic=True,
                               message='MISSING MEDIA IMAGE', catalog=entry['catalog'], side=entry['side'],
                               reason=entry['reason'], source=None,
                               created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                               output=dict(file=image.relative_to(root).as_posix()),
                               limitation='Image unavailable in this batch; this does not prove the physical media is missing.'),
                          stream, ensure_ascii=False, indent=2)
        except OSError:
            image.unlink(missing_ok=True)
            raise
        made.append(str(image))
    report['generated_placeholders'] = made
    # A successful final manifest is the sequence-accounting commit marker.
    path = root / 'output-json' / 'catalog-sequence.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return report


def process_catalog_copy(item: str, stem: str, args, cache: Path) -> dict:
    """Prepare already-composed photos for cataloging, without geometric resampling."""
    import tempfile
    from .cli import acquire
    from .imaging import gray_pixels, normalize
    from .barcodes import scan
    from .outputs import targets
    from .media_presence import catalog_reference
    paths = targets(args.output, stem)
    with tempfile.TemporaryDirectory(prefix='.catalog-copy-', dir=args.output) as directory:
        work = Path(directory)
        source, source_log = acquire(item, work)
        normalized = work / 'normalized.miff'
        meta = normalize(source, normalized); source_log.update(meta)
        gray = gray_pixels(normalized, meta['width'], meta['height'])
        barcodes = scan(gray)
        source_log['barcodes'] = barcodes
        reference = catalog_reference(gray, barcodes, args)
        return write_catalog_copy(source, normalized, source_log, args, work, paths, reference)


def write_catalog_copy(source, normalized, source_log, args, work, paths, reference=None) -> dict:
    """Keep catalog compositions or uncertain barcode references without inventing geometry."""
    from .cli import write_json
    from .outputs import before_preview, after_preview
    from .finishing import finish
    staged = work / 'image.png'
    run(['magick', str(normalized), '-depth', str(args.depth), str(staged)])
    finishing = finish(source, staged, args, work)
    if args.keep_metadata:
        finishing['metadata']['source_inventory_file'] = paths['metadata'].name
        (work/'source-metadata.json').replace(paths['metadata'])
    staged.replace(paths['image'])
    if args.preview:
        if not getattr(args, 'background_previews', False):
            before_preview(normalized, paths['before'])
        after_preview(paths['image'], paths['preview'])
    result = dict(schema=1, tool='de-askew', version=__version__, status='review_required', source=source_log,
                  barcodes=source_log['barcodes'], created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  rotation=dict(clockwise_degrees=0), geometry=dict(mode='catalog_copy', applied=False), finishing=finishing,
                  output=dict(file=paths['image'].relative_to(args.output).as_posix(), sha256=sha256(paths['image']),
                              width=source_log['width'], height=source_log['height'], depth=args.depth),
                  warnings=['catalog_copy_no_geometry_correction', 'barcode_side_pairing_assumes_adjacent_front_back'])
    if reference:
        result['catalog_reference'] = reference
        result['warnings'].append('barcode_reference_media_unverified')
    write_json(paths['log'], result)
    return result


def preserve_reference(record: dict) -> dict:
    """Keep evidence outside the media slots; never consume the preceding side."""
    import os
    import shutil
    import errno
    from .cli import write_json
    result = record['result']; paths = record['paths']; root = record['root']
    reference = result['catalog_reference']
    old = paths['image']
    destination = root / 'output-references' / (record['name'] + '-reference.png')
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(old, destination)
    except OSError as error:
        if error.errno not in (errno.EPERM, errno.EXDEV, errno.ENOTSUP, errno.EACCES):
            raise
        with destination.open('xb') as output, old.open('rb') as source:
            shutil.copyfileobj(source, output)
    result['output']['file'] = destination.relative_to(root).as_posix()
    result['barcode_pair'] = dict(status='reference_only', barcode=reference['catalog'],
                                 side=None, reason=reference['reason'])
    write_json(paths['log'], result)
    paths['image'] = destination
    old.unlink()
    return dict(**reference, input=record['input'], image=str(destination), log=str(paths['log']))
