"""Nominal disc dimensions; classification is conditional on a physical aperture."""
from __future__ import annotations

import math


def select_profile(ratio: float, requested: str = 'auto') -> dict:
    if requested not in {'auto','120','80'}:
        raise ValueError('Disc size must be auto, 120, or 80 mm')
    choices = [120,80] if requested=='auto' else [int(requested)]
    diameter = min(choices,key=lambda d:abs(ratio/(15/d)-1))
    nominal = 15/diameter
    if not math.isfinite(ratio) or abs(ratio/nominal-1)>.15:
        raise ValueError('Aperture ratio does not support the requested 120 mm / 80 mm disc model')
    return dict(outer_diameter_mm=diameter,spindle_diameter_mm=15,
                nominal_radius_ratio=nominal,measured_radius_ratio=float(ratio),
                relative_ratio_deviation=float(ratio/nominal-1),requested_size=requested,
                selection='inferred_from_physical_aperture_ratio' if requested=='auto' else 'user_selected',
                note='Nominal output dimensions, not a measurement in millimeters or a media-format identification')
