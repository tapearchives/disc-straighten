"""Outermost coherent rim search, followed by independent subpixel circle fits.

The automatic search assumes one nearly circular disc on a plain light background.
Printing and metallization boundaries are never assumed concentric with the hole.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_closing, gaussian_filter, label
from scipy.optimize import least_squares
from scipy.signal import find_peaks

from .sampling import CubicSampler
from .profiles import select_profile


def fit_circle(points: np.ndarray, seed: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    def residual(p: np.ndarray) -> np.ndarray:
        return np.linalg.norm(points-p[:2], axis=1)-p[2]
    result = least_squares(residual, seed, loss='soft_l1', f_scale=.6)
    return result.x, residual(result.x)


def coarse_disc(gray: np.ndarray) -> tuple[np.ndarray, float, dict]:
    # Connected foreground is only an initializer; it does not define the knockout.
    step = max(1, int(max(gray.shape)/800))
    small = gray[::step, ::step].astype(float)
    h, w = small.shape
    k = max(3, min(h,w)//30)
    corners = np.concatenate([small[:k,:k].ravel(), small[:k,-k:].ravel(),
                              small[-k:,:k].ravel(), small[-k:,-k:].ravel()])
    background = float(np.median(corners))
    noise = float(np.median(abs(corners-background)))
    if background < 180 or noise > 12:
        raise ValueError('Automatic geometry needs a plain light background; supply --outer and --hole')
    mask = binary_closing(small < background-max(7, noise*5), iterations=2)
    components, count = label(mask)
    if not count:
        raise ValueError('No disc foreground found')
    areas = np.bincount(components.ravel()); areas[0] = 0
    ys, xs = np.where(components == np.argmax(areas))
    if len(xs) < .02*h*w:
        raise ValueError('Foreground too small for automatic disc geometry')
    lo = np.array([xs.min(), ys.min()], float)*step
    hi = np.array([xs.max(), ys.max()], float)*step
    center = (lo+hi)/2
    radius = float(np.mean(hi-lo)/2)
    if min(hi-lo)/max(hi-lo) < .85:
        raise ValueError('Foreground is not nearly circular; supply reviewed circle geometry')
    return center, radius, dict(background_gray=background, background_mad=noise,
                               initial_center_px=center.tolist(), initial_radius_px=radius)


def profiles(smooth: CubicSampler, center: np.ndarray, radii: np.ndarray, count: int = 720):
    theta = np.linspace(0, 2*np.pi, count, endpoint=False)
    directions = np.column_stack([np.cos(theta), np.sin(theta)])
    coords = center[:,None,None] + directions.T[:,:,None]*radii
    values = smooth.sample([coords[1], coords[0]])
    valid = ((coords[0]>2)&(coords[0]<smooth.shape[1]-3)&
             (coords[1]>2)&(coords[1]<smooth.shape[0]-3))
    return directions, values, valid


def rim_hypotheses(smooth: CubicSampler, center: np.ndarray, radius: float,
                   background: float, *, extended: bool) -> tuple[np.ndarray, dict]:
    radii = np.arange(radius*.90, radius*(1.20 if extended else 1.055), .5)
    directions, values, valid = profiles(smooth, center, radii)
    gradient = np.gradient(values, .5, axis=1)
    points = []; rays = []
    for ray, (direction, row, bright, ok) in enumerate(zip(directions, gradient, values, valid)):
        peaks, _ = find_peaks(row, height=1.2, prominence=.8, distance=3)
        for p in peaks:
            if ok[p]:
                points.append(center+direction*radii[p]); rays.append(ray)
    if len(points) < 300:
        raise ValueError('Too little physical rim evidence; supply --outer x,y,r')
    points = np.asarray(points); rays = np.asarray(rays)
    tolerance = max(1.5, radius*.003)
    rng = np.random.default_rng(1729)
    models = []
    for _ in range(2400):
        indices = rng.choice(len(points),3,replace=False)
        a,b,c = points[indices]
        matrix = 2*np.array([b-a,c-a])
        if abs(np.linalg.det(matrix)) < radius**2*.15:
            continue
        xy = np.linalg.solve(matrix,np.array([b@b-a@a,c@c-a@a]))
        r = np.linalg.norm(a-xy)
        center_limit = .075 if extended else .045
        radius_limit = 1.18 if extended else 1.025
        if np.linalg.norm(xy-center)>radius*center_limit or not .90*radius<r<radius*radius_limit:
            continue
        errors = abs(np.linalg.norm(points-xy,axis=1)-r)
        keep = errors<tolerance
        support = len(np.unique(rays[keep]))
        if support<300 or len(np.unique(rays[keep]//30))<20:
            continue
        if any(np.linalg.norm(xy-m[:2])<tolerance and abs(r-m[2])<tolerance for m in models):
            continue
        model,_ = fit_circle(points[keep],np.array([*xy,r]))
        models.append(model)
    candidates = []
    for model in models:
        for _ in range(3):
            errors = abs(np.linalg.norm(points-model[:2],axis=1)-model[2])
            keep = errors<tolerance
            model,_ = fit_circle(points[keep],model)
        errors = abs(np.linalg.norm(points-model[:2],axis=1)-model[2])
        keep = errors<tolerance
        coverage = len(np.unique(rays[keep]))/720
        # The exterior of the physical rim should return to the light background.
        _,outside,good = profiles(smooth,model[:2],np.array([model[2]+5,model[2]+9]))
        fraction_background = float(np.mean(outside[good]>background-12)) if good.any() else 0
        if coverage>.70 and good.any() and float(np.median(outside[good]))>180:
            candidates.append((model,coverage,fraction_background))
    if not candidates:
        raise ValueError('No coherent physical rim found; supply --outer x,y,r')
    candidates.sort(key=lambda x:x[0][2],reverse=True)
    # Require broad absolute coverage, not coverage relative to the strongest
    # interior printing circle. A complete printed ring must not raise the bar
    # for a physical clear rim with some weak/missing segments.
    minimum_support = .80
    supported = [m for m,c,b in candidates if c>=minimum_support]
    if not supported:
        raise ValueError('No outer rim has sufficient angular coverage')
    result = supported[0]
    return result, dict(rim_candidates=[dict(center_px=m[:2].tolist(),radius_px=float(m[2]),
                       angular_support_fraction=c,exterior_background_fraction=b) for m,c,b in candidates],
                       minimum_selected_support=minimum_support,
                       selection='outermost light-exterior circle with at least 80 percent angular support')


def rim_seed(smooth: np.ndarray, center: np.ndarray, radius: float, background: float) -> tuple[np.ndarray, dict]:
    # Separate passes keep nearby circle estimates stable when a much wider band
    # adds unrelated background edges to the random-sampling pool. The extension
    # catches a clear-plastic outline beyond the thresholded silkscreen footprint.
    sampler = CubicSampler(smooth)
    fits = []
    for extended in [False,True]:
        try:
            fits.append(rim_hypotheses(sampler,center,radius,background,extended=extended))
        except ValueError:
            fits.append(None)
    primary,extended = fits
    if primary is None and extended is None:
        raise ValueError('No coherent physical rim found; supply --outer x,y,r')
    chosen = primary
    if primary is None or (extended is not None and extended[0][2]>primary[0][2]*1.025):
        chosen = extended
    seed,diagnostics = chosen
    diagnostics['extended_search_selected'] = chosen is extended
    if primary is not None and extended is not None:
        diagnostics['extended_search_radius_px'] = float(extended[0][2])
        diagnostics['primary_search_radius_px'] = float(primary[0][2])
    return seed,diagnostics


def refine_circle(gray: np.ndarray, seed: list[float] | np.ndarray, band: float, sign: int) -> dict:
    smooth = CubicSampler(gaussian_filter(gray.astype(float), .65))
    center = np.array(seed[:2], float); radius = float(seed[2])
    radii = np.arange(max(1,radius-band), radius+band, .125)
    for _ in range(3):
        directions, values, valid = profiles(smooth, center, radii)
        gradient = sign*np.gradient(values, .125, axis=1)
        k = np.argmax(np.where(valid, gradient, -1), axis=1)
        row = np.arange(len(k))
        accepted = (k>0)&(k<len(radii)-1)&(gradient[row,k]>1.5)&valid[row,k]
        k = np.clip(k,1,len(radii)-2)
        ym,y0,yp = gradient[row,k-1], gradient[row,k], gradient[row,k+1]
        denom = ym-2*y0+yp
        offset = np.divide(.5*(ym-yp),denom,out=np.zeros_like(ym),where=abs(denom)>1e-9)
        rr = radii[k]+np.clip(offset,-1,1)*.125
        points = (center+directions*rr[:,None])[accepted]
        if len(points)<180:
            raise ValueError('Insufficient subpixel circle support; supply reviewed geometry')
        fit, errors = fit_circle(points, np.array([*center,radius]))
        center,radius = fit[:2], float(fit[2])
    # A second harmonic reports scan ellipticity without altering the pixels.
    theta = np.arctan2(points[:,1]-center[1],points[:,0]-center[0])
    design = np.column_stack([np.ones(len(theta)),np.cos(2*theta),np.sin(2*theta)])
    harmonic = np.linalg.lstsq(design, errors, rcond=None)[0]
    return dict(center_px=center.tolist(), radius_px=radius,
                edge_rms_px=float(np.sqrt(np.mean(errors**2))),
                edge_residual_p95_px=float(np.percentile(abs(errors),95)),
                profiles_used=len(points), profiles_attempted=720,
                ellipse_radial_amplitude_px=float(np.hypot(*harmonic[1:])),
                refinement_half_band_px=band, selection='automatic')


def detect(gray: np.ndarray, outer_override: list[float] | None = None,
           hole_override: list[float] | None = None, *, disc_size: str = 'auto') -> dict:
    notes = []; diagnostics = {}
    if outer_override:
        outer = dict(center_px=outer_override[:2],radius_px=outer_override[2],selection='user_override')
    else:
        center,radius,diagnostics = coarse_disc(gray)
        seed, detail = rim_seed(gaussian_filter(gray.astype(float),.8),center,radius,diagnostics['background_gray'])
        diagnostics.update(detail)
        outer = refine_circle(gray,seed,max(2,seed[2]*.004),1)
    r = outer['radius_px']; center = outer['center_px']
    if hole_override:
        hole = dict(center_px=hole_override[:2],radius_px=hole_override[2],selection='user_override')
    else:
        # Both 120 and 80 mm discs use the nominal 15 mm aperture. A physical
        # aperture is needed to infer size without an external scale reference.
        candidates = []
        for diameter in ([120,80] if disc_size=='auto' else [int(disc_size)]):
            try:
                preliminary = refine_circle(gray,[*center,r*15/diameter],max(3,r*.012),-1)
                seed = [*preliminary['center_px'],preliminary['radius_px']]
                candidate = refine_circle(gray,seed,max(3,seed[2]*.04),-1)
                profile = select_profile(candidate['radius_px']/r,str(diameter))
                score = (abs(profile['relative_ratio_deviation'])+
                         candidate['edge_residual_p95_px']/candidate['radius_px'])
                candidates.append((score,candidate,diameter))
            except ValueError:
                continue
        if not candidates:
            raise ValueError('No physical aperture supports the requested disc size')
        candidates.sort(key=lambda x:x[0]);hole = candidates[0][1]
        diagnostics['spindle_candidates'] = [dict(diameter_mm=d,score=s,circle=c) for s,c,d in candidates]
        if len(candidates)>1:
            notes.append('disc_size_ambiguous')
    profile = select_profile(hole['radius_px']/r,disc_size)
    h,w = gray.shape
    if not all(0 <= x < limit for x,limit in zip(outer['center_px'],[w,h])):
        raise ValueError('Disc center lies outside the image')
    if np.linalg.norm(np.array(hole['center_px'])-center)+hole['radius_px'] >= r:
        raise ValueError('The spindle aperture does not fit within the disc')
    for name,circle in [('outer',outer),('hole',hole)]:
        tolerance = max(2,circle['radius_px']*.0025) if name=='outer' else 2.5
        if circle.get('edge_residual_p95_px',0)>tolerance:
            notes.append(f'{name}_circle_irregular_or_uncertain')
        if circle.get('profiles_used',720)<500:
            notes.append(f'{name}_circle_incomplete_edge_support')
    if abs(profile['relative_ratio_deviation'])>.025:
        notes.append('physical_ratio_far_from_nominal')
    if np.linalg.norm(np.array(hole['center_px'])-center)>r*.025:
        notes.append('large_spindle_to_rim_center_offset')
    if min(center[0]-r,center[1]-r,w-1-center[0]-r,h-1-center[1]-r) < 1:
        notes.append('source_touches_or_clips_disc_boundary')
    return dict(outer_circle=outer, spindle_circle=hole, disc_profile=profile,diagnostics=diagnostics,
                warnings=notes,
                center_separation_px=float(np.linalg.norm(np.array(hole['center_px'])-center)))
