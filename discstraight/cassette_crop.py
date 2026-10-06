"""Final analytic body crop with a shared circular corner template.

Image colors may help estimate geometry, but never determine output alpha.
"""
from __future__ import annotations

import numpy as np

from .cassette import source_to_plane


def body_crop(gray: np.ndarray, geometry: dict, *, minimum_source_scale: float,
              feather: float = 1., corners: str = 'auto') -> dict:
    """Keep the full corrected frame; do not inset or trace a pixel silhouette."""
    w, h = geometry['plane_size_px']
    residuals = []
    for i, points in enumerate(geometry['diagnostics']['edge_source_points_px']):
        p = source_to_plane(np.asarray(points), geometry)
        axis = 1 if i % 2 == 0 else 0
        expected = 0 if i in [0, 3] else (w, h)[axis]
        residuals.append(float(np.percentile(abs(p[:, axis]-expected), 95)))
    from .cassette_corners import fit_corners
    fits=fit_corners(gray,geometry) if corners=='auto' else []
    return dict(method='analytic_body_crop_with_corner_arcs' if any(f['applied'] for f in fits) else 'analytic_straight_body_crop_after_rectification',
                coordinate_space='corrected_cassette_plane_before_180_flip',
                bounds_px=[0., 0., w, h],
                inset_xy_px=[0., 0.], inset_fraction_per_side=0.,
                corner_radii_xy_px=[f.get('radii_xy_px',[0.,0.]) for f in fits] if fits else [[0.,0.]]*4,
                corner_fits=fits,corner_policy=corners,
                corner_template=fits[0]['shared_template'] if fits else None,
                feather_alignment='centered_on_rectangle', feather_px=feather,
                alpha_depends_on_image_colors=False,
                source_pixels_masked_before_warp=False,
                residual_edge_p95_px=residuals,
                outer_boundary_refitted=bool(geometry.get('outer_boundary')),
                projection_policy='Long main-body edges define the plane; short guide projections outside the final rectangle are cropped.',
                internal_apertures_removed=False, matte_baked_into_master=False,
                note='Warp original pixels first. Apply the body rectangle and four equal tangent circular corners. Only supported steep-view residuals permit at most 8 percent local radius adjustment. Unresolved edges use the logged shared template; no pixel silhouette or color-key alpha.')


def crop_alpha(x: np.ndarray, y: np.ndarray, crop: dict, feather: float = 1.) -> np.ndarray:
    """Four straight sides, with a slight centered transition at their boundary."""
    left, top, right, bottom = crop['bounds_px']
    distance = np.minimum(np.minimum(x-left, right-x), np.minimum(y-top, bottom-y))
    for i,fit in enumerate(crop.get('corner_fits',[])):
        if not fit['applied']:continue
        rx,ry=fit['radii_xy_px']
        if min(rx,ry)<=0:continue
        u=x-left if i in [0,3] else right-x
        v=y-top if i in [0,1] else bottom-y
        qx=(u-rx)/rx;qy=(v-ry)/ry
        norm=np.hypot(qx,qy)
        gradient=np.hypot(qx/rx,qy/ry)/np.maximum(norm,1e-9)
        arc_distance=(1-norm)/np.maximum(gradient,1e-9)
        distance=np.where((u<rx)&(v<ry),np.minimum(distance,arc_distance),distance)
    t = np.clip(distance/feather+.5, 0, 1)
    return (t*t*(3-2*t)).astype('float32')
