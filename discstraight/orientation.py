"""Multi-view OCR consensus. Scores are evidence weights, not probabilities."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Callable

import numpy as np

from .imaging import ocr_view, render, run


def wrap(angle: float) -> float:
    return (angle+180)%360-180


def distance(a: float, b: float) -> float:
    return abs(wrap(a-b))


def weighted_angle(angles: list[float], weights: list[float]) -> float:
    reference = angles[int(np.argmax(weights))]
    # Weighted median resists a decorative outlier and OCR's snapped rectangles.
    values = np.array([reference+wrap(a-reference) for a in angles])
    order = np.argsort(values)
    cumulative = np.cumsum(np.asarray(weights)[order])
    return wrap(float(values[order[np.searchsorted(cumulative,cumulative[-1]/2)]]))


def helper_binary(cache: Path) -> Path:
    source = Path(__file__).with_name('vision.swift')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    cache.mkdir(parents=True,exist_ok=True)
    target = cache/f'vision-{digest}'
    if not target.is_file():
        temporary = cache/f'vision-{digest}.building'
        run(['swiftc', '-O', str(source), '-o', str(temporary)])
        temporary.replace(target)
    return target


def observation(row: dict, view: dict, radius: float) -> dict | None:
    text = row['text']; letters = sum(c.isalpha() for c in text)
    chars = sum(c.isalnum() for c in text); confidence = float(row['confidence'])
    if chars<2 or confidence<.35:
        return None
    size = view['size']; scale = view['scale']; m = (size-1)/2
    points = np.array([row[k] for k in ['bottom_left','bottom_right','top_right','top_left']])
    points[:,0] *= size; points[:,1] = (1-points[:,1])*size
    baseline = points[1]-points[0]
    tilt = math.degrees(math.atan2(baseline[1],baseline[0]))
    if abs(tilt)>35:
        return None
    height = float(np.linalg.norm(points[3]-points[0])/scale)
    width = float(np.linalg.norm(baseline)/scale)
    if height<max(3,radius*.006) or width<height*.7:
        return None
    a = math.radians(-view['angle']); c,s = math.cos(a),math.sin(a)
    source_points = ((points-m)@np.array([[c,s],[-s,c]]))/scale+view['center']
    center = source_points.mean(axis=0)
    radial = float(np.linalg.norm(center-view['center'])/radius)
    if radial>1.01:
        return None
    return dict(text=text, confidence=confidence, characters=chars, letters=letters,
                correction_clockwise_degrees=wrap(view['angle']-tilt),
                center_px=center.tolist(), polygon_px=source_points.tolist(),
                height_px=height,width_px=width, radial_position=radial,
                observed_tilt_degrees=tilt, view_clockwise_degrees=view['angle'])


def projected_box(row: dict, angle: float) -> np.ndarray:
    a = math.radians(angle); c,s = math.cos(a),math.sin(a)
    points = np.asarray(row['polygon_px'])@np.array([[c,s],[-s,c]])
    return np.array([*points.min(axis=0),*points.max(axis=0)])


def overlap(a: np.ndarray, b: np.ndarray) -> float:
    common = np.prod(np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2])))
    return float(common/max(1,min(np.prod(a[2:]-a[:2]),np.prod(b[2:]-b[:2]))))


def deduplicate(rows: list[dict]) -> list[dict]:
    def quality(row: dict) -> float:
        return row['confidence']**2*(min(row['characters'],32)+2)*(
            1+.4*math.exp(-(row['observed_tilt_degrees']/20)**2))
    unique = []
    for row in sorted(rows,key=quality,reverse=True):
        angle = row['correction_clockwise_degrees']
        if any(distance(angle,old['correction_clockwise_degrees'])<12 and
               overlap(projected_box(row,angle),projected_box(old,angle))>.55 for old in unique):
            continue
        unique.append(row)
    return unique


def consensus(rows: list[dict], radius: float, *, policy: str = 'balanced',
              minimum_margin: float = .20) -> dict:
    rows = deduplicate(rows)
    if not rows:
        return dict(clockwise_degrees=0.0, status='review_required',
                    reasons=['no_readable_text'], mixed_directions=False,
                    relative_margin=0.0, candidates=[], unique_text_regions=[])
    median_height = float(np.median([r['height_px'] for r in rows if r['letters']>=2] or
                                    [r['height_px'] for r in rows]))
    prominent = sorted([r['height_px'] for r in rows if r['letters']>=2],reverse=True)[:3]
    prominence_reference = float(np.median(prominent)) if prominent else median_height
    for row in rows:
        base = min(row['characters'],32)*row['confidence']**2
        if policy == 'balanced':
            prominence = float(np.clip(math.sqrt(row['height_px']/prominence_reference),.35,1.3))
            rim = .3 if row['radial_position']>.86 and row['height_px']<radius*.035 else 1
            numeric = .15 if row['letters']<2 else 1
            base *= prominence*rim*numeric
        row['vote_weight'] = base
    remaining = rows.copy(); candidates = []
    while remaining:
        seed = max(remaining,key=lambda row:sum(r['vote_weight'] for r in remaining
                   if distance(r['correction_clockwise_degrees'],row['correction_clockwise_degrees'])<=7))
        family = [r for r in remaining if distance(r['correction_clockwise_degrees'],
                                                  seed['correction_clockwise_degrees'])<=7]
        ids = {id(r) for r in family}; remaining = [r for r in remaining if id(r) not in ids]
        angle = weighted_angle([r['correction_clockwise_degrees'] for r in family],
                               [r['vote_weight'] for r in family])
        # Nearby lines form one block. Capping a block prevents a legal paragraph
        # from accumulating an unlimited vote simply because it has many lines.
        boxes = [projected_box(r,angle) for r in family]
        parent = list(range(len(family)))
        def root(i: int) -> int:
            while parent[i]!=i:
                i = parent[i]
            return i
        for i,box in enumerate(boxes):
            for j in range(i):
                other = boxes[j]
                gap = np.maximum(0,np.maximum(box[:2],other[:2])-np.minimum(box[2:],other[2:]))
                if gap[0]<median_height*2 and gap[1]<median_height*2.5:
                    parent[root(i)] = root(j)
        blocks = {}
        for i,row in enumerate(family):
            blocks.setdefault(root(i),[]).append(row)
        block_scores = [sum(r['vote_weight'] for r in block) for block in blocks.values()]
        caps = [45*min(1,max(r['height_px'] for r in block)/prominence_reference)
                for block in blocks.values()]
        score = sum(min(cap,s) for cap,s in zip(caps,block_scores)) if policy=='balanced' else sum(block_scores)
        candidates.append(dict(clockwise_degrees=round(angle,4), score=round(score,4),
                          text_regions=len(family), text_blocks=len(blocks),
                          letters=sum(r['letters'] for r in family),
                          examples=[r['text'] for r in sorted(family,key=lambda r:-r['vote_weight'])[:8]],
                          angular_spread_degrees=round(float(np.average([
                            distance(r['correction_clockwise_degrees'],angle) for r in family],
                            weights=[r['vote_weight'] for r in family])),3)))
    candidates.sort(key=lambda c:c['score'],reverse=True)
    best = candidates[0]; runner = candidates[1]['score'] if len(candidates)>1 else 0
    margin = (best['score']-runner)/max(best['score'],1e-9)
    reasons = []
    if margin<minimum_margin:
        reasons.append('competing_text_directions')
    if best['score']<8 or best['letters']<6:
        reasons.append('too_little_readable_text')
    if best['angular_spread_degrees']>3:
        reasons.append('text_baselines_disagree')
    return dict(clockwise_degrees=best['clockwise_degrees'],
                status='review_required' if reasons else 'accepted', reasons=reasons,
                mixed_directions=runner>best['score']*.2,
                relative_margin=round(margin,4), policy=policy, candidates=candidates,
                unique_text_regions=rows,
                confidence_note='Heuristic agreement score; not a probability of primary-text intent')


def orient(source: Path, outer: dict, work: Path, cache: Path, *, languages: str,
           policy: str, minimum_margin: float, progress: Callable[[str],None],
           rectification_matrix: np.ndarray | None = None, spindle: dict | None = None,
           backend: str = 'auto') -> dict:
    from .deskew import orient_without_ocr
    from .ocr import OCRUnavailableError
    try:
        if backend == 'none':
            raise OCRUnavailableError('OCR disabled with --ocr none')
        return _orient_ocr(source, outer, work, cache, languages=languages, policy=policy,
                           minimum_margin=minimum_margin, progress=progress,
                           rectification_matrix=rectification_matrix, spindle=spindle, backend=backend)
    except OCRUnavailableError as error:
        progress('OCR unavailable; searching visual straightness from -45 to +45 degrees')
        return orient_without_ocr(source, outer, work, rectification_matrix=rectification_matrix,
                                  reason=str(error), requested_backend=backend)


def _orient_ocr(source: Path, outer: dict, work: Path, cache: Path, *, languages: str,
                policy: str, minimum_margin: float, progress: Callable[[str],None],
                rectification_matrix: np.ndarray | None = None, spindle: dict | None = None,
                backend: str = 'auto') -> dict:
    from .ocr import recognize
    observations = []
    # No privileged original orientation: the same eight-view search is used for
    # an arbitrary incoming rotation and for mixed-direction artwork.
    for angle in range(0,360,45):
        progress(f'OCR view {angle} degrees')
        path = work/f'ocr-{angle}.png'
        view = ocr_view(source,path,angle,outer['center_px'],outer['radius_px'],rectification_matrix)
        data = recognize(path,languages,cache,backend)
        for row in data['rows']:
            item = observation(row,view,outer['radius_px'])
            if item:
                observations.append(item)
    result = consensus(observations,outer['radius_px'],policy=policy,minimum_margin=minimum_margin)
    if rectification_matrix is not None and spindle is not None and result['candidates']:
        # Perspective changes both letter scale and skew across the source.
        # Recheck the winning family at the actual output scale, since Vision's
        # upscaled boxes can snap to horizontal despite a small residual tilt.
        coarse = result['clockwise_degrees']; angle = coarse; passes = []
        size = math.ceil(2*outer['radius_px']+16); size += size%2
        if size<=2000:
            for iteration in range(2):
                progress(f'Fine text alignment {iteration+1} at output scale')
                path = work/f'fine-orientation-{iteration}.png'
                render(source,path,outer,spindle,angle,size=size,feather=1,depth=8,
                       rectification_matrix=rectification_matrix)
                native = recognize(path,languages,cache,backend)
                view = dict(size=size,scale=1,center=outer['center_px'],angle=angle)
                family = []
                for row in native['rows']:
                    item = observation(row,view,outer['radius_px'])
                    if item and distance(item['correction_clockwise_degrees'],coarse)<4:
                        family.append(item)
                estimate = consensus(family,outer['radius_px'],policy=policy,minimum_margin=minimum_margin)
                proposed = estimate['clockwise_degrees']
                accepted = (estimate['status']=='accepted' and distance(proposed,coarse)<=2)
                passes.append(dict(view_clockwise_degrees=angle,proposed_clockwise_degrees=proposed,
                                   accepted=accepted,candidates=estimate['candidates'],reasons=estimate['reasons']))
                if not accepted:
                    break
                change = distance(proposed,angle); angle = proposed
                if change<.05:
                    break
        result['clockwise_degrees'] = angle
        result['fine_alignment'] = dict(coarse_clockwise_degrees=coarse,passes=passes,
                                        note='Output-scale OCR of the same direction family; bounded to 2 degrees. '
                                             'Skipped above 2000-pixel native width. Temporary views only.')
    result['ocr'] = dict(engine=data['engine'],languages=data['languages'],
                         revision=data['revision'],coarse_views=8,
                         fine_views=len(result.get('fine_alignment',{}).get('passes',[])),language_correction=False)
    result['ocr']['missing_languages']=data['missing_languages']
    if data['missing_languages']:
        result['reasons'].append('requested_ocr_language_unavailable')
        result['status']='review_required'
    result['text_coordinate_space'] = 'rectified_disc_plane' if rectification_matrix is not None else 'normalized_source'
    return result
