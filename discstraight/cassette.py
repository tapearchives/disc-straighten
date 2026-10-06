"""Cassette face geometry: long body edges, measured bow, and explicit depth limits."""
from __future__ import annotations

import itertools
import math

import cv2
import numpy as np
from scipy.optimize import least_squares, minimize_scalar

from .sampling import CubicSampler
from .perspective import transform

BODY_MM = np.array([100.4, 63.8])


def ordered_quad(points: np.ndarray) -> np.ndarray:
    q = np.asarray(points, dtype=float).reshape(4, 2)
    q = q[np.argsort(np.arctan2(q[:, 1]-q[:, 1].mean(), q[:, 0]-q[:, 0].mean()))]
    q = np.roll(q, -int(np.argmin(q.sum(axis=1))), axis=0)
    # A right-handed image-coordinate TL, TR, BR, BL ordering, with the long
    # body direction mapped to canonical x. OCR later chooses 0/180 degrees.
    if np.linalg.norm(q[1]-q[0])+np.linalg.norm(q[3]-q[2]) < np.linalg.norm(q[2]-q[1])+np.linalg.norm(q[0]-q[3]):
        q = np.roll(q, -1, axis=0)
    return q


def line(points: np.ndarray) -> np.ndarray:
    p = np.asarray(points); center = np.median(p, axis=0)
    _, _, vectors = np.linalg.svd(p-center, full_matrices=False)
    normal = vectors[-1]
    return np.r_[normal, -normal@center]


def intersect(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    point = np.cross(a, b)
    if abs(point[2]) < 1e-8:
        raise ValueError('Cassette body lines do not form stable corners')
    return point[:2]/point[2]


def curved_corners(groups: list[np.ndarray], initial: np.ndarray) -> np.ndarray:
    models=[]
    for i, points in enumerate(groups):
        origin=initial[i]; delta=initial[(i+1)%4]-origin
        length=np.linalg.norm(delta); tangent=delta/length; normal=np.array([-tangent[1],tangent[0]])
        t=(points-origin)@tangent/length
        design=np.column_stack([np.ones(len(t)),t,t*t])
        values=(points-origin)@normal
        fit=least_squares(lambda c:design@c-values,np.linalg.lstsq(design,values,rcond=None)[0],loss='soft_l1',f_scale=.7)
        models.append((origin,tangent,normal,length,fit.x))
    def residual(point, model):
        origin,tangent,normal,length,c=model
        t=(point-origin)@tangent/length
        return (point-origin)@normal-(c[0]+c[1]*t+c[2]*t*t)
    result=[]
    for i in range(4):
        fit=least_squares(lambda p:[residual(p,models[i-1]),residual(p,models[i])],initial[i])
        result.append(fit.x)
    q=np.array(result)
    if not cv2.isContourConvex(q.astype('float32')) or np.max(np.linalg.norm(q-initial,axis=1))>np.sqrt(abs(cv2.contourArea(initial.astype('float32'))))*.05:
        raise ValueError('Curved body edges do not give a stable corner intersection')
    return q


def curve_consensus(t: np.ndarray, offsets: np.ndarray, valid: np.ndarray,
                    tolerance: float) -> tuple[np.ndarray, np.ndarray]:
    """Fit the broadly supported edge, excluding short guide-rail excursions.

    A smooth curve through *all* samples can mistake a protruding rail for lens
    bow. Deterministic quadratic consensus requires support over most of the
    edge before robust refinement. Rejected pieces remain in the silhouette.
    """
    design = np.column_stack([np.ones(len(t)), t-.5, (t-.5)**2])
    indices = np.flatnonzero(valid)
    initial = np.linalg.lstsq(design[valid], offsets[valid], rcond=None)[0]
    candidates = [initial]
    rng = np.random.default_rng(0)
    for _ in range(160):
        chosen = np.sort(rng.choice(indices, 3, replace=False))
        if min(np.diff(t[chosen])) < .12 or np.ptp(t[chosen]) < .55:
            continue
        candidates.append(np.linalg.solve(design[chosen], offsets[chosen]))
    best = valid.copy(); best_score = -np.inf
    for coefficients in candidates:
        error = abs(design@coefficients-offsets)
        supported = valid & (error < tolerance)
        if supported.sum() < len(indices)*.55 or np.ptp(t[supported]) < .60:
            continue
        score = supported.sum()-.1*np.sum(np.minimum(error[valid]/tolerance, 1))
        if score > best_score:
            best, initial, best_score = supported, coefficients, score
    fit = least_squares(lambda c: design[best]@c-offsets[best], initial,
                        loss='soft_l1', f_scale=tolerance*.45)
    inliers = valid & (abs(offsets-design@fit.x) < tolerance*1.25)
    return fit.x, inliers


def proposals(gray: np.ndarray) -> list[np.ndarray]:
    h, w = gray.shape; area = h*w; seeds = []
    smooth = cv2.GaussianBlur(gray, (3, 3), .7)
    for low, high in [(5, 15), (15, 45), (40, 120)]:
        edges = cv2.Canny(smooth, low, high)
        for kernel in [3, 7]:
            closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((kernel, kernel), np.uint8))
            contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                if cv2.contourArea(contour) < area*.18:
                    continue
                for tolerance in [.018, .035]:
                    poly = cv2.approxPolyDP(contour, cv2.arcLength(contour, True)*tolerance, True)
                    if len(poly) == 4 and cv2.isContourConvex(poly):
                        seeds.append(ordered_quad(poly[:, 0]))
                # minAreaRect is a seed only; projections do not define the fit.
                seeds.append(ordered_quad(cv2.boxPoints(cv2.minAreaRect(contour))))
    detected = cv2.createLineSegmentDetector().detect(smooth)[0]
    if detected is not None:
        lines = detected.reshape(-1, 4)
        delta = lines[:, 2:]-lines[:, :2]; lengths = np.linalg.norm(delta, axis=1)
        chosen = lengths > min(h, w)*.16
        lines, lengths, delta = lines[chosen], lengths[chosen], delta[chosen]
        if len(lines):
            theta = np.arctan2(delta[:, 1], delta[:, 0])
            angle = np.angle(np.sum(lengths*np.exp(4j*theta)))/4
            axes = np.array([[math.cos(angle), math.sin(angle)], [-math.sin(angle), math.cos(angle)]])
            center = np.array([w/2, h/2]); middle = (lines[:, :2]+lines[:, 2:])/2-center
            positions = middle@axes.T
            directions = delta@axes.T
            groups = []
            for normal_axis in [0, 1]:
                select = abs(directions[:, normal_axis]) < lengths*.15
                values = positions[select, normal_axis]
                # Long segment locations supply bounded candidates without
                # assuming one background color or a complete closed contour.
                clustered = []
                for value in sorted(values):
                    if not clustered or value-clustered[-1] > 4:
                        clustered.append(float(value))
                neg = [v for v in clustered if v < -min(h, w)*.22][:3]
                pos = [v for v in clustered if v > min(h, w)*.22][-3:]
                groups.append((neg, pos))
            for left, right, top, bottom in itertools.product(*groups[0], *groups[1]):
                local = np.array([[left, top], [right, top], [right, bottom], [left, bottom]])
                seeds.append(ordered_quad(local@axes+center))
    # Border-adjacent objects may have broken contours. These are proposals,
    # never accepted without four supported body traces and reel evidence.
    for inset in [.015, .055, .105]:
        seeds.append(ordered_quad(np.array([[w*inset, h*inset], [w*(1-inset), h*inset],
                                           [w*(1-inset), h*(1-inset)], [w*inset, h*(1-inset)]])))
    seeds.extend(straight_line_proposals(gray))
    unique = []
    for q in seeds:
        side = np.linalg.norm(np.roll(q, -1, axis=0)-q, axis=1)
        ratio = (side[0]+side[2])/(side[1]+side[3])
        if not 1.05 < ratio < 2.7 or min(side) < min(h, w)*.25:
            continue
        if not .16*area < abs(cv2.contourArea(q.astype('float32'))) < 1.08*area:
            continue
        if any(np.sqrt(np.mean((q-old)**2)) < 4 for old in unique):
            continue
        unique.append(q)
    return unique


def straight_line_proposals(gray: np.ndarray) -> list[np.ndarray]:
    """Intersect observed long lines, including off-center objects in a scene.

    Rounded corners and transparent shells often have no closed contour. These
    are proposals only: edge spans and paired reels must still validate them.
    """
    h,w = gray.shape
    segments = cv2.createLineSegmentDetector().detect(cv2.GaussianBlur(gray,(3,3),.7))[0]
    segments=np.empty((0,4)) if segments is None else segments.reshape(-1,4)
    # Hough segments bridge interruptions along a clear plastic edge; unlike
    # connected contours they do not require one uniform background.
    joined=cv2.HoughLinesP(cv2.Canny(cv2.GaussianBlur(gray,(0,0),1),8,25),1,np.pi/720,
                           threshold=int(min(h,w)*.13),minLineLength=min(h,w)*.32,
                           maxLineGap=min(h,w)*.12)
    if joined is not None:segments=np.vstack([segments,joined.reshape(-1,4)])
    if not len(segments):return []
    delta = segments[:,2:]-segments[:,:2]
    lengths = np.linalg.norm(delta,axis=1)
    keep = lengths > min(h,w)*.14
    segments,delta,lengths = segments[keep],delta[keep],lengths[keep]
    theta = np.arctan2(delta[:,1],delta[:,0])
    angle = np.angle(np.sum(lengths*np.exp(4j*theta)))/4
    groups = [[],[]]
    for j in np.argsort(-lengths):
        direction = np.array([math.cos(angle),math.sin(angle)])
        group = 0 if abs(delta[j]@direction)/lengths[j] > .94 else 1
        expected = direction if group==0 else np.array([-direction[1],direction[0]])
        if abs(delta[j]@expected)/lengths[j] < .94:
            continue
        l = line(segments[j].reshape(2,2))
        normal = np.array([-expected[1],expected[0]])
        if l[:2]@normal<0:l=-l
        if not any(abs(l[2]-old[2])<5 for old in groups[group]):
            groups[group].append(l)
        groups[group] = groups[group][:12]
    edges = cv2.Canny(gray,10,35)
    distance = cv2.distanceTransform(255-edges,cv2.DIST_L2,3)
    sampler = CubicSampler(distance)
    ranked=[]
    for a,b in itertools.combinations(groups[0],2):
        if abs(a[2]-b[2])<min(h,w)*.22:continue
        for c,d in itertools.combinations(groups[1],2):
            if abs(c[2]-d[2])<min(h,w)*.22:continue
            try:q=ordered_quad(np.array([intersect(a,c),intersect(a,d),intersect(b,d),intersect(b,c)]))
            except ValueError:continue
            area=abs(cv2.contourArea(q.astype('float32')))
            sides=np.linalg.norm(np.roll(q,-1,axis=0)-q,axis=1)
            ratio=(sides[0]+sides[2])/(sides[1]+sides[3])
            if not 1.15<ratio<2.3 or not .16*h*w<area<h*w:continue
            if q.min()<0 or np.any(q[:,0]>=w) or np.any(q[:,1]>=h):continue
            t=np.linspace(.08,.92,70)
            points=q[:,None]+(np.roll(q,-1,axis=0)-q)[:,None]*t[None,:,None]
            support=np.mean(sampler.sample([points[...,1],points[...,0]])<2,axis=1)
            if support.min()<.45:continue
            ranked.append((float(support.mean())+.12*area/(h*w),q))
    ranked.sort(key=lambda v:-v[0])
    return [q for _,q in ranked[:40]]


def trace_edge(sampler: CubicSampler, a: np.ndarray, b: np.ndarray, *, band: float,
               count: int = 220, step: float = .5, strength_scale: float = 1.) -> dict:
    t = np.linspace(.055, .945, count)
    direction = b-a; normal = np.array([-direction[1], direction[0]])/np.linalg.norm(direction)
    base = a+t[:, None]*direction
    offsets = np.arange(-band, band+step/2, step)
    coords = base[:, None, :]+offsets[None, :, None]*normal
    inside = ((coords[..., 0] > 1) & (coords[..., 1] > 1) &
              (coords[..., 0] < sampler.shape[1]-2) & (coords[..., 1] < sampler.shape[0]-2))
    plus = coords+normal*.7; minus = coords-normal*.7
    gradient = (sampler.sample([plus[..., 1], plus[..., 0]])-
                sampler.sample([minus[..., 1], minus[..., 0]]))/1.4
    strength = abs(gradient)
    score = np.log1p(strength)-.8*(offsets[None, :]/max(band, 1))**2
    score[~inside] = -1e4
    # Dynamic programming joins weak/split-polarity boundaries and penalizes
    # abrupt jumps to label texture, shadows, or a neighboring physical layer.
    moves = np.arange(-3, 4); history = np.zeros(score.shape, dtype=np.int8)
    previous = score[0].copy()
    for i in range(1, count):
        shifted = np.array([np.roll(previous, int(move))-.10*(move*step)**2 for move in moves])
        for j, move in enumerate(moves):
            if move > 0: shifted[j, :move] = -np.inf
            if move < 0: shifted[j, move:] = -np.inf
        best = np.argmax(shifted, axis=0)
        history[i] = moves[best]
        previous = score[i]+shifted[best, np.arange(len(offsets))]
    indices = np.empty(count, dtype=int); indices[-1] = np.argmax(previous)
    for i in range(count-1, 0, -1):
        indices[i-1] = indices[i]-history[i, indices[i]]
    shifts = offsets[indices].copy()
    # Quadratic gradient-peak localization around the traced ridge.
    valid = (indices > 0) & (indices < len(offsets)-1)
    rows = np.arange(count)[valid]; cols = indices[valid]
    left, middle, right = strength[rows, cols-1], strength[rows, cols], strength[rows, cols+1]
    denominator = left-2*middle+right
    correction = np.divide(.5*(left-right), denominator, out=np.zeros_like(middle), where=abs(denominator)>1e-8)
    shifts[valid] += np.clip(correction, -.5, .5)*step
    weight = strength[np.arange(count), indices]
    valid = inside[np.arange(count), indices] & (weight > max(.3,1.8*strength_scale,np.median(weight)*.13))
    points = base+shifts[:, None]*normal
    if valid.sum() < count*.4:
        raise ValueError('Insufficient physical cassette edge support')
    coefficients, inliers = curve_consensus(t, shifts, valid, max(.8, np.linalg.norm(direction)*.0008))
    if inliers.sum() < count*.4:
        raise ValueError('Insufficient consistent main-body edge support')
    return dict(t=t, points=points, inliers=inliers, strengths=weight, normal=normal,
                offsets=shifts, polynomial=coefficients, coverage=float(inliers.mean()),
                median_strength=float(np.median(weight[inliers])),
                clipped_fraction=float((~inside[np.arange(count), indices]).mean()))


def refine(gray: np.ndarray, q: np.ndarray, *, band: float, step: float = .5) -> tuple[np.ndarray, list[dict]]:
    sampler = CubicSampler(cv2.GaussianBlur(gray.astype('float32'), (0, 0), .8))
    traces = [trace_edge(sampler, q[i], q[(i+1)%4], band=band, step=step) for i in range(4)]
    lines = [line(trace['points'][trace['inliers']]) for trace in traces]
    corners = np.array([intersect(lines[i-1], lines[i]) for i in range(4)])
    return corners, traces


def reel_evidence(gray: np.ndarray, q: np.ndarray) -> dict:
    target = np.array([[0, 0], [599, 0], [599, 380.6], [0, 380.6]], dtype='float32')
    matrix = cv2.getPerspectiveTransform(q.astype('float32'), target)
    view = cv2.warpPerspective(gray, matrix, (600, 382), flags=cv2.INTER_AREA)
    # Circle evidence after provisional rectification; rotating hub teeth and
    # wound tape never supply the body scale. No assumed hole diameter is fitted.
    edges = cv2.Canny(cv2.GaussianBlur(view, (3, 3), 1), 15, 55)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    ellipses = []
    for contour in contours:
        if len(contour) < 30: continue
        center, axes, angle = cv2.fitEllipse(contour)
        if not 35 < min(axes) < 105 or not .82 < min(axes)/max(axes) <= 1:
            continue
        if not .30*382 < center[1] < .69*382: continue
        ellipses.append((np.array(center), float(np.mean(axes))))
    best = None
    for (a, da), (b, db) in itertools.combinations(ellipses, 2):
        if a[0] > b[0]: a, b, da, db = b, a, db, da
        spacing = (b[0]-a[0])/599
        errors = [2*abs(spacing-42.5/100.4), abs(a[1]-b[1])/382,
                  abs((a[0]+b[0])/2/599-.5), abs(da-db)/max(da, db)*.1]
        cost = sum(errors)
        if best is None or cost < best['cost']:
            best = dict(cost=float(cost), centers_canonical_px=[a.tolist(), b.tolist()],
                        spacing_body_fraction=float(spacing), diameter_similarity=float(min(da, db)/max(da, db)))
    if best is None:
        return dict(score=0., cost=1., centers_canonical_px=[])
    best['score'] = max(0., 1-best['cost']/.15)
    return best


def division_undistort(points: np.ndarray, k: float, center: np.ndarray, scale: float) -> np.ndarray:
    p = (np.asarray(points)-center)/scale
    return center+scale*p/(1+k*np.sum(p*p, axis=-1, keepdims=True))


def division_distort(points: np.ndarray, k: float, center: np.ndarray, scale: float) -> np.ndarray:
    p = (np.asarray(points)-center)/scale
    discriminant = 1-4*k*np.sum(p*p, axis=-1, keepdims=True)
    if np.any(discriminant <= 0):
        raise ValueError('Radial mapping would fold or become nonreal')
    return center+scale*p*2/(1+np.sqrt(discriminant))


def plumb_line_fit(traces: list[dict], shape: tuple[int, int], mode: str) -> dict:
    center = np.array([(shape[1]-1)/2, (shape[0]-1)/2]); scale = max(shape)/2
    if mode=='off':
        return dict(model='none',coefficient=0.,estimated_coefficient=None,
                    center_source_px=center.tolist(),scale_px=scale,applied=False,
                    policy=mode,supported_edges=0,calibrated=False,
                    reason='No calibrated lens profile; perspective-only policy.',
                    assumptions='No lens distortion or residual bow estimated in this mode.')
    groups = [t['points'][t['inliers']] for t in traces]
    def errors(k: float, heldout: bool = False) -> np.ndarray:
        values=[]
        for points in groups:
            p = division_undistort(points, k, center, scale)
            reference = line(p[::2])
            sample = p[1::2] if heldout else p
            values.append(np.sqrt(np.mean((sample@reference[:2]+reference[2])**2)))
        return np.array(values)
    fit = minimize_scalar(lambda k: float(np.mean(errors(k)**2)), bounds=(-.12, .12), method='bounded')
    before, after = errors(0, True), errors(float(fit.x), True)
    improvement = float(np.mean(before)-np.mean(after))
    supported = sum((after < before*.80) & (before-after > .25))
    applied = bool(mode == 'auto' and supported >= 3 and improvement > .35 and
                   np.mean(after) < np.mean(before)*.70 and abs(fit.x) < .115)
    return dict(model='one_parameter_division', coefficient=float(fit.x) if applied else 0.,
                estimated_coefficient=float(fit.x), center_source_px=center.tolist(), scale_px=scale,
                applied=applied, policy=mode, supported_edges=int(supported),
                heldout_edge_rms_before_px=before.tolist(), heldout_edge_rms_after_candidate_px=after.tolist(),
                reason=('consistent_curvature_reduction' if applied else
                        'disabled' if mode=='off' else 'conformance_only_requested' if mode=='conform' else
                        'insufficient_independent_edge_agreement'),
                calibrated=False,
                assumptions='Straight body edges; optical center fixed at image center. Not camera calibration or 3D de-parallax.')


def straight_trace_edge(sampler: CubicSampler, a: np.ndarray, b: np.ndarray, *, band: float, proposal: bool = False, strength_scale: float = 1.) -> dict:
    """Choose a broadly supported straight ridge, then refine its sample peaks.

    Several parallel ridges can describe a clear rim. Prefer the outermost one
    with near-best long-span support, rather than a curved background fringe.
    """
    t=np.linspace(.08,.92,90 if proposal else 180);direction=b-a
    normal=np.array([-direction[1],direction[0]])/np.linalg.norm(direction)
    base=a+t[:,None]*direction;step=.5 if proposal else .25
    offsets=np.arange(-band,band+step/2,step)
    points=base[:,None]+offsets[None,:,None]*normal
    plus=points+normal*.6;minus=points-normal*.6
    strength=abs(sampler.sample([plus[...,1],plus[...,0]])-sampler.sample([minus[...,1],minus[...,0]]))/1.2
    inside=((points[...,0]>.5)&(points[...,0]<sampler.shape[1]-1.5)&
            (points[...,1]>.5)&(points[...,1]<sampler.shape[0]-1.5))
    peaks=(strength>np.maximum(max(.3,1.5*strength_scale),strength.max(axis=1,keepdims=True)*.2))&inside
    peaks[:,1:-1]&=(strength[:,1:-1]>strength[:,:-2])&(strength[:,1:-1]>=strength[:,2:])
    peaks[:,[0,-1]]=False
    support=cv2.dilate(peaks.astype('uint8'),np.ones((1,3 if proposal else 5),np.uint8))
    intercept,slope=np.meshgrid(offsets,np.arange(-band*1.5,band*1.5+step/2,step))
    hypotheses=intercept.ravel()[:,None]+slope.ravel()[:,None]*(t-.5)
    indices=np.rint((hypotheses+band)/step).astype(int)
    valid=(indices>=0)&(indices<len(offsets))
    scores=np.mean(support[np.arange(len(t)),np.clip(indices,0,len(offsets)-1)]*valid,axis=1)
    best=float(scores.max())
    if best<.5:raise ValueError(f'Insufficient long straight body-edge support ({best:.0%})')
    eligible=np.flatnonzero(scores>=max(.5,best-.035))
    chosen=eligible[np.argmin(intercept.ravel()[eligible])]
    target=hypotheses[chosen]
    distances=np.where(peaks,abs(offsets[None,:]-target[:,None]),np.inf)
    idx=distances.argmin(axis=1);rows=np.arange(len(t))
    inliers=distances[rows,idx]<.7
    values=strength[rows,idx];lo=strength[rows,np.maximum(0,idx-1)];hi=strength[rows,np.minimum(len(offsets)-1,idx+1)]
    denominator=lo-2*values+hi
    adjustment=np.divide(.5*(lo-hi),denominator,out=np.zeros_like(values),where=abs(denominator)>1e-8)
    shifts=offsets[idx]+np.clip(adjustment,-.5,.5)*step
    design=np.column_stack([np.ones(len(t)),t-.5])
    fit=least_squares(lambda c:(design@c-shifts)[inliers],np.linalg.lstsq(design[inliers],shifts[inliers],rcond=None)[0],loss='soft_l1',f_scale=.25)
    inliers &= abs(design@fit.x-shifts)<.7
    if inliers.mean()<.45 or np.ptp(t[inliers])<.60:
        raise ValueError('Straight edge does not span enough of the main body')
    return dict(points=base+shifts[:,None]*normal,inliers=inliers,coverage=float(inliers.mean()),
                median_strength=float(np.median(values[inliers])),selection='straight_ridge_consensus')


def detect_cassette(gray: np.ndarray, *, debow: str = 'off', corners: np.ndarray | None = None) -> dict:
    factor = min(1., 900/max(gray.shape))
    small = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    seeds = [ordered_quad(corners)*factor] if corners is not None else proposals(small)
    if corners is None:
        seeds.extend(reel_body_proposals(small,seeds))
    ranked=[]
    sampler=CubicSampler(cv2.GaussianBlur(small.astype('float32'),(0,0),.65))
    for seed in seeds:
        try:
            try:
                q, traces = refine(small, seed, band=max(3, min(small.shape)*.019))
            except ValueError:
                if debow!='off':raise
                try:
                    q,traces=refine(small,seed,band=max(5,min(small.shape)*.065))
                except ValueError:
                    traces=[straight_trace_edge(sampler,seed[i],seed[(i+1)%4],
                             band=max(5,min(small.shape)*.065),proposal=True) for i in range(4)]
                    lines=[line(t['points'][t['inliers']]) for t in traces]
                    q=np.array([intersect(lines[i-1],lines[i]) for i in range(4)])
            coverage=min(t['coverage'] for t in traces)
            strength=float(np.mean([min(25, t['median_strength']) for t in traces]))
            reel=reel_evidence(small, q)
            sides=np.linalg.norm(np.roll(q,-1,axis=0)-q,axis=1)
            ratio=(sides[0]+sides[2])/(sides[1]+sides[3])
            # Interior labels often share the reel x-spacing but clip half of
            # the shell height. The body ratio is a soft prior, not a forced
            # source rectangle: perspective is still allowed and measured.
            shape_penalty=.75*abs(math.log(ratio/(BODY_MM[0]/BODY_MM[1])))
            score=coverage*.25+strength/25*.20+reel['score']*.55-shape_penalty
            ranked.append((score, q, reel, traces))
        except (ValueError, np.linalg.LinAlgError):
            continue
    ranked.sort(key=lambda item:-item[0])
    if not ranked or (corners is None and (ranked[0][0] < .47 or ranked[0][2]['score'] < .30)):
        raise ValueError('No supported cassette body with a compatible reel pair; use reviewed --cassette-corners')
    score, seed, reel, _ = ranked[0]
    # A low-resolution valid line can cross a transparent double edge at full
    # resolution. Refine its straight ridge directly; don't require a curved
    # trace to succeed before the default straight-line method can run.
    if debow=='off':
        q=seed/factor
        sampler=CubicSampler(cv2.GaussianBlur(gray.astype('float32'),(0,0),max(.65,.65/factor)))
        traces=[]
        for i in range(4):
            try:t=straight_trace_edge(sampler,q[i],q[(i+1)%4],band=max(4,6/factor),strength_scale=factor)
            except ValueError as error:
                t=trace_edge(sampler,q[i],q[(i+1)%4],band=max(4,6/factor),step=.125,strength_scale=factor)
                t['selection']='straight_line_fit_to_traced_boundary'
                t['selection_note']=str(error)
            traces.append(t)
    else:
        q, traces=refine(gray, seed/factor, band=max(3, 6/factor), step=.125)
    recovery=dict(applied=False,reason='luminance_lines_sufficient_or_explicit_geometry')
    if (debow=='off' and corners is None and
            sum(t.get('selection')=='straight_line_fit_to_traced_boundary' for t in traces)>=2):
        # Clear shells can expose a stronger internal seam while attenuating a
        # textured background at their real outside edge. Do not silently use
        # that inner seam just because it has a plausible reel pair.
        from .cassette_texture import texture_boundary_traces
        try:
            recovered,recovery=texture_boundary_traces(gray,q)
            lines=[line(t['points'][t['inliers']]) for t in recovered]
            candidate=np.array([intersect(lines[i-1],lines[i]) for i in range(4)])
            candidate_reel=reel_evidence(small,candidate*factor)
            if candidate_reel['score']<max(.55,reel['score']*.75):
                raise ValueError('Texture rectangle lacks a compatible reel pair')
            traces=recovered
            reel=candidate_reel
        except ValueError as error:
            recovery=dict(applied=False,reason=str(error))
    diagnostics=dict(candidate_count=len(seeds),usable_candidates=len(ranked),
                     candidates=[dict(score=v[0],corners_analysis_px=v[1].tolist(),reels=v[2]) for v in ranked[:5]])
    geometry=geometry_from_traces(gray.shape, traces, score, reel, diagnostics, debow=debow)
    geometry['texture_boundary_recovery']=recovery
    from .cassette_corners import aspect_ratio_tag
    geometry['aspect_ratio']=aspect_ratio_tag(np.array(geometry['undistorted_source_corners_px']))
    return geometry


def reel_body_proposals(gray: np.ndarray, seeds: list[np.ndarray]) -> list[np.ndarray]:
    """Let paired hubs propose the missing clear shell beyond a printed label.

    This never supplies the final corner coordinates: all four external lines
    must be measured again. Both possible long-edge orientations are proposed.
    """
    target=np.array([[0,0],[599,0],[599,380.6],[0,380.6]],np.float32)
    candidates=[]
    for q in seeds:
        evidence=reel_evidence(gray,q)
        if evidence['cost']>.18:continue
        a,b=np.array(evidence['centers_canonical_px'])
        inverse=np.linalg.inv(cv2.getPerspectiveTransform(q.astype('float32'),target))
        a,b=transform(np.array([a,b]),inverse)
        tangent=(b-a)/np.linalg.norm(b-a);normal=np.array([-tangent[1],tangent[0]])
        center=(a+b)/2
        for width_factor in [.98,1.02]:
            width=np.linalg.norm(b-a)*100.4/42.5*width_factor;height=width*63.8/100.4
            for relative_y in [.43,.48,.52,.57]:
                origin=center-tangent*width/2-normal*relative_y*height
                body=np.array([origin,origin+tangent*width,origin+tangent*width+normal*height,origin+normal*height])
                if body.min()<0 or np.any(body[:,0]>=gray.shape[1]) or np.any(body[:,1]>=gray.shape[0]):continue
                if any(np.sqrt(np.mean((body-old)**2))<5 for _,old in candidates):continue
                candidates.append((evidence['cost'],body))
    candidates.sort(key=lambda v:v[0])
    return [q for _,q in candidates[:60]]


def geometry_from_traces(shape: tuple[int, int], traces: list[dict], score: float,
                         reel: dict, diagnostics: dict, *, debow: str) -> dict:
    """Fit the plane and optional bow from already selected physical boundaries."""
    lens=plumb_line_fit(traces, shape, debow)
    k=lens['coefficient']; center=np.array(lens['center_source_px']); scale=lens['scale_px']
    groups=[division_undistort(t['points'][t['inliers']], k, center, scale) for t in traces]
    lines=[line(p) for p in groups]
    q=np.array([intersect(lines[i-1], lines[i]) for i in range(4)])
    if debow!='off':
        q=curved_corners(groups,q)
    ppm=math.sqrt(abs(cv2.contourArea(q.astype('float32')))/np.prod(BODY_MM))
    plane=np.array([[0,0],[BODY_MM[0]*ppm,0],BODY_MM*ppm,[0,BODY_MM[1]*ppm]],dtype='float32')
    h=cv2.getPerspectiveTransform(q.astype('float32'),plane)
    edge_stats=[]; coefficients=[]
    for i, points in enumerate(groups):
        mapped=transform(points,h); axis=0 if i%2==0 else 1; other=1-axis
        length=plane[2,axis]; coordinate=mapped[:,axis]/length
        desired=0 if i in [0,3] else plane[2,other]
        error=mapped[:,other]-desired
        base=coordinate*(1-coordinate)
        design=np.column_stack([base,base*(coordinate-.5)])
        robust=least_squares(lambda c:design@c-error,np.linalg.lstsq(design,error,rcond=None)[0],loss='soft_l1',f_scale=.65)
        # Curvature only, zero at the virtual corners: A*t*(1-t).
        amplitude=float(robust.x[0])
        coefficients.append(robust.x.tolist())
        rms=float(np.sqrt(np.mean(error**2)))
        edge_stats.append(dict(side=['top','right','bottom','left'][i],rms_after_projective_px=rms,
                               midpoint_bow_px=amplitude/4,coverage=traces[i]['coverage'],
                               selection=traces[i].get('selection','traced_boundary'),
                               selection_note=traces[i].get('selection_note'),
                               gradient_domain=traces[i].get('gradient_domain','luminance'),
                               median_gradient=traces[i]['median_strength']))
    sample_t=np.linspace(0,1,65)
    c=np.array(coefficients)
    bow=float(np.max(abs(sample_t*(1-sample_t)*(c[:,0,None]+c[:,1,None]*(sample_t-.5)))))
    conform=bool(debow=='conform' or (debow=='auto' and bow>.8))
    if bow > min(plane[2])*.025:
        conform=False
    warnings=['cassette_single_plane_approximation']
    if min(shape)<400:warnings.append('low_resolution_boundary_uncertainty')
    if score<.65:warnings.append('cassette_boundary_evidence_weak')
    if any(t['coverage']<.70 for t in traces):warnings.append('cassette_edge_incomplete')
    if lens['applied']:warnings.append('uncalibrated_radial_correction')
    elif bow>.8 and debow!='off':warnings.append('edge_bow_cause_unresolved')
    if conform:warnings.append('edge_conformance_is_2d_approximation')
    border=float(np.min(np.column_stack([q[:,0],q[:,1],shape[1]-1-q[:,0],shape[0]-1-q[:,1]])))
    if border<max(shape)*.008:warnings.append('shell_near_image_boundary')
    # Weak-perspective inclination proxy, not a calibrated camera pose.
    mid=BODY_MM/2*ppm; inverse=np.linalg.inv(h)
    p=transform(np.array([mid,mid+[1,0],mid+[0,1]]),inverse)
    singular=np.linalg.svd(np.column_stack([p[1]-p[0],p[2]-p[0]]),compute_uv=False)
    tilt=math.acos(float(np.clip(min(singular)/max(singular),0,1)))
    displacement=1.7*math.tan(tilt)
    return dict(media='cassette',body_dimensions_mm=BODY_MM.tolist(),pixels_per_mm=ppm,
                corner_method='intersections_of_fitted_straight_lines' if debow=='off' else 'intersections_of_fitted_curves',
                fitted_source_lines=[v.tolist() for v in lines],
                plane_size_px=plane[2].tolist(),undistorted_source_corners_px=q.tolist(),
                source_to_plane_matrix=h.tolist(),lens=lens,
                conformance=dict(applied=conform,amplitudes_px=coefficients if conform else [[0.,0.]]*4,
                                 candidate_amplitudes_px=coefficients,
                                 maximum_candidate_bow_px=bow,
                                 model='boundary_normal_cubic_blend',
                                 meaning='Approximate straight-edge derivative, not inferred camera optics or recovered 3D'),
                edges=edge_stats,reel_evidence=reel,detection_score=score,
                warnings=list(dict.fromkeys(warnings)),
                depth=dict(detected_3d_geometry=False,model='known_cassette_has_multiple_depth_planes',
                           weak_perspective_tilt_proxy_degrees=math.degrees(tilt),
                           raised_front_step_nominal_mm=1.7,
                           estimated_front_plane_displacement_mm=displacement,
                           estimated_front_plane_displacement_output_px=displacement*ppm,
                           note='Main face is rectified. Raised lip, recessed hubs and hole walls retain parallax; hidden surfaces are not recovered. Tilt estimate assumes square pixels and negligible lens distortion.'),
                diagnostics=dict(**{k:v for k,v in diagnostics.items() if k!='edge_source_points_px'},
                                 edge_source_points_px=[t['points'][t['inliers']].tolist() for t in traces]))


def plane_to_source(points: np.ndarray, geometry: dict) -> np.ndarray:
    p=np.asarray(points,dtype=float).copy(); w,h=geometry['plane_size_px']
    u=p[...,0]/w; v=p[...,1]/h
    top,right,bottom,left=np.array(geometry['conformance']['amplitudes_px'])
    curve=lambda t,c:t*(1-t)*(c[0]+c[1]*(t-.5))
    p[...,0]+=curve(v,left)*(1-u)+curve(v,right)*u
    p[...,1]+=curve(u,top)*(1-v)+curve(u,bottom)*v
    source=transform(p.reshape(-1,2),np.linalg.inv(geometry['source_to_plane_matrix'])).reshape(p.shape)
    lens=geometry['lens']
    return division_distort(source,lens['coefficient'],np.array(lens['center_source_px']),lens['scale_px'])


def source_to_plane(points: np.ndarray, geometry: dict) -> np.ndarray:
    lens=geometry['lens']
    undistorted=division_undistort(points,lens['coefficient'],np.array(lens['center_source_px']),lens['scale_px'])
    observed=transform(np.asarray(undistorted).reshape(-1,2),np.array(geometry['source_to_plane_matrix']))
    estimate=observed.copy();w,h=geometry['plane_size_px']
    top,right,bottom,left=np.array(geometry['conformance']['amplitudes_px'])
    curve=lambda t,c:t*(1-t)*(c[0]+c[1]*(t-.5))
    for _ in range(12):
        u=estimate[:,0]/w;v=estimate[:,1]/h
        delta=np.column_stack([curve(v,left)*(1-u)+curve(v,right)*u,
                               curve(u,top)*(1-v)+curve(u,bottom)*v])
        estimate=observed-delta
    return estimate.reshape(np.asarray(points).shape)
