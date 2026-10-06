"""Use the nominal body ratio to look beyond a stronger interior label edge.

The prior proposes a search region, never an invented final boundary. Restricted
to nearly parallel opposite sides; perspective foreshortening remains possible.
"""
from __future__ import annotations

import cv2
import numpy as np

from .sampling import CubicSampler


def recover_faint_body_edge(gray: np.ndarray, traces: list[dict]) -> tuple[list[dict], dict]:
    from .cassette import BODY_MM, intersect, line, reel_evidence, straight_trace_edge
    lines=[line(t['points'][t['inliers']]) for t in traces]
    q=np.array([intersect(lines[i-1],lines[i]) for i in range(4)])
    edges=np.roll(q,-1,axis=0)-q
    lengths=np.linalg.norm(edges,axis=1);unit=edges/lengths[:,None]
    nominal=float(BODY_MM[0]/BODY_MM[1])
    ratio=float((lengths[0]+lengths[2])/(lengths[1]+lengths[3]))
    cross=lambda a,b: a[0]*b[1]-a[1]*b[0]
    parallel=max(abs(cross(unit[0],unit[2])),abs(cross(unit[1],unit[3])))
    note=dict(applied=False,observed_ratio=ratio,nominal_ratio=nominal,
              reason='ratio_or_perspective_outside_bounded_search')
    if not 1.025 < ratio/nominal < 1.20 or parallel>.075:
        return traces,note
    factor=min(1.,900/max(gray.shape));small=cv2.resize(gray,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
    sampler=CubicSampler(cv2.GaussianBlur(small.astype('float32'),(0,0),.65))
    before=reel_evidence(small,q*factor)['score'];candidates=[]
    height=(lengths[0]+lengths[2])/(2*nominal)
    for side in (0,2):
        opposite=(side+2)%4
        # The opposite long line supplies direction; good short sides supply
        # the virtual intersections. Test both long edges independently.
        tangent=-unit[opposite];normal=np.array([-tangent[1],tangent[0]])
        midpoint=(q[opposite]+q[(opposite+1)%4])/2-normal*height
        expected=np.r_[normal,-normal@midpoint]
        a=intersect(lines[(side-1)%4],expected);b=intersect(expected,lines[(side+1)%4])
        try:
            trace=straight_trace_edge(sampler,a*factor,b*factor,band=max(3,height*factor*.022),
                                      proposal=True,strength_scale=.2,relative_threshold=.035)
            points=trace['points']/factor
            replacement=line(points[trace['inliers']]);trial=lines.copy();trial[side]=replacement
            candidate=np.array([intersect(trial[i-1],trial[i]) for i in range(4)])
            if not cv2.isContourConvex(candidate.astype('float32')):continue
            if candidate.min()<0 or np.any(candidate[:,0]>=gray.shape[1]) or np.any(candidate[:,1]>=gray.shape[0]):continue
            sizes=np.linalg.norm(np.roll(candidate,-1,axis=0)-candidate,axis=1)
            newratio=(sizes[0]+sizes[2])/(sizes[1]+sizes[3])
            support=trace['coverage'];evidence=reel_evidence(small,candidate*factor);reels=evidence['score']
            # The hub row lies near the face's middle, on either side of it
            # after a 180-degree flip. This broad, non-exact design prior helps
            # reject extending the already-correct bottom into faint backdrop
            # texture when the missing edge is above the label.
            centers=evidence.get('centers_canonical_px')
            hub_y=float(np.mean(np.array(centers)[:,1])/382) if centers is not None else .5
            if abs(newratio/nominal-1)>.025 or support<.50 or reels<max(.70,before*.90) or not .43<hub_y<.57:continue
            candidates.append((support-abs(newratio/nominal-1)*3,side,candidate,newratio,support))
        except (ValueError,np.linalg.LinAlgError):
            continue
    if not candidates:
        note['reason']='no_measured_outer_line_supporting_nominal_ratio'
        return traces,note
    _,side,candidate,newratio,analysis_support=max(candidates,key=lambda item:item[0])
    sampler=CubicSampler(cv2.GaussianBlur(gray.astype('float32'),(0,0),max(.65,.65/factor)))
    try:
        trace=straight_trace_edge(sampler,candidate[side],candidate[(side+1)%4],
                                  band=max(3,3/factor),strength_scale=.04*factor,relative_threshold=.035,
                                  minimum_peak=.06,minimum_support=.35)
    except ValueError:
        note['reason']='proposed_outer_line_failed_full_resolution_check'
        return traces,note
    trace['selection']='aspect_guided_measured_outer_line'
    refined=lines.copy();refined[side]=line(trace['points'][trace['inliers']])
    final=np.array([intersect(refined[i-1],refined[i]) for i in range(4)])
    sides=np.linalg.norm(np.roll(final,-1,axis=0)-final,axis=1)
    final_ratio=float((sides[0]+sides[2])/(sides[1]+sides[3]))
    if abs(final_ratio/nominal-1)>.03:
        note['reason']='full_resolution_line_disagrees_with_body_prior'
        return traces,note
    result=traces.copy();result[side]=trace
    note.update(applied=True,side=['top','right','bottom','left'][side],candidate_ratio=float(newratio),
                final_ratio=final_ratio,analysis_coverage=analysis_support,
                coverage=trace['coverage'],reason='faint_outer_line_supported_by_other_sides_and_nominal_ratio',
                limitation='Near-parallel image prior; not a camera calibration or an exact source-plane aspect constraint.')
    return result,note
