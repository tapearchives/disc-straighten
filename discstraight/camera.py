"""Capture identity is provenance, not a substitute for lens calibration."""
from __future__ import annotations

from pathlib import Path
from typing import Callable


# Deliberately exclude GPS, timestamps, serial numbers, owner and MakerNote blobs.
EXIF_FIELDS = {
    'make': 'Make', 'model': 'Model', 'lens_make': 'LensMake',
    'lens_model': 'LensModel', 'focal_length_mm': 'FocalLength',
    'focal_length_35mm_equivalent': 'FocalLengthIn35mmFilm',
    'digital_zoom_ratio': 'DigitalZoomRatio', 'f_number': 'FNumber',
    'software': 'Software',
}


def describe_camera(tags: dict[str, str | None]) -> dict:
    tags = {key: tags.get(key) or None for key in EXIF_FIELDS}
    make = (tags['make'] or '').strip().casefold()
    model = (tags['model'] or '').strip().casefold()
    models = {'iphone 7 plus': 'iPhone 7 Plus', 'iphone 15 pro max': 'iPhone 15 Pro Max'}
    family = models.get(model) if make in {'', 'apple'} else None
    lens = (tags['lens_model'] or '').casefold()
    # A zoom setting / equivalent focal length does not identify a physical lens:
    # e.g. 2x on the 15 Pro Max can be a Main-camera sensor crop.
    role = 'unknown'
    for name, needles in [('front', ('front', 'truedepth')),
                          ('ultra_wide', ('ultra wide', 'ultra-wide', 'ultrawide')),
                          ('telephoto', ('telephoto',)), ('wide', ('wide',))]:
        if any(word in lens for word in needles):
            role = name
            break
    return dict(metadata_status='identified' if tags['model'] else 'partial' if any(tags.values()) else 'absent',
                exif=tags, recognized_family=family, lens_role_from_explicit_label=role,
                prior_software_lens_correction='unknown',
                model_specific_profile_applied=False,
                policy='Measure residual curvature; never apply coefficients based on phone name or zoom alone.',
                calibration_status='No matching per-capture calibration is loaded; EXIF identity is not calibration.',
                apple_lens_correction_setting=(
                    'Available for Ultra Wide and front camera; default on. Actual capture setting unknown.'
                    if family == 'iPhone 15 Pro Max' else None),
                privacy='Only allowlisted camera/lens/exposure-software fields retained; no GPS, dates or serials.')


def read_camera(source: Path, run: Callable) -> dict:
    # Read before auto-orient / color normalization removes source profiles.
    # One delimiter per field, including absent properties; no shell evaluation.
    separator = '\x1f'
    fmt = separator.join(f'%[EXIF:{tag}]' for tag in EXIF_FIELDS.values())
    raw = run(['magick', 'identify', '-quiet', '-format', fmt, str(source)])
    values = raw.split(separator)
    if len(values) != len(EXIF_FIELDS):
        raise ValueError('Malformed camera metadata fields')
    cleaned = [''.join(c for c in value if c.isprintable()).strip()[:256] or None for value in values]
    return describe_camera(dict(zip(EXIF_FIELDS, cleaned)))
