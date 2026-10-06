"""Fit a shared rounded-rectangle template after perspective correction.

All corners begin as identical circles. Only supported steep-view residuals
can make small local changes. Image contrast never directly determines alpha.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.signal import find_peaks

from .cassette import plane_to_source
from .sampling import CubicSampler


def aspect_ratio_tag(corners: np.ndarray, tolerance: float = .05) -> dict:
    sides=np.linalg.norm(np.roll(corners,-1,axis=0)-corners,axis=1)
    measured=float((sides[0]+sides[2])/(sides[1]+sides[3]))
    nominal=100.4/63.8;error=abs(measured/nominal-1)
    return dict(tag='compact cassette AR' if error<=tolerance else None,
                nominal_ratio=nominal,observed_ratio=measured,relative_error=error,
                tolerance_fraction=tolerance,matched=bool(error<=tolerance),
                measured_before_rectification=True,
                note='Mean opposite main-body edge lengths; perspective can change this ratio. Reel/edge evidence is required separately.')


def _observe_arc(sample, directions: np.ndarray, radius: float, ppm: float) -> dict:
    """Measure near a template arc without granting it an independent shape."""
    band=max(1.,ppm*.12);offsets=np.linspace(-band,band,33)
    points=radius*(1-directions)
    candidates=points[:,None]+offsets[None,:,None]*directions[:,None]
    delta=max(.75,ppm*.04)
    strength=np.nan_to_num(abs(sample(candidates+directions[:,None]*delta)-
                              sample(candidates-directions[:,None]*delta))/(2*delta),nan=0.)
    objective=np.log1p(strength)-.05*(offsets[None]/band)**2
    ids=objective.argmax(axis=1);rows=np.arange(len(ids));values=strength[rows,ids]
    valid=(ids>0)&(ids<len(offsets)-1)&(values>.2)
    observed=points+offsets[ids,None]*directions
    if valid.mean()<.55 or min(valid[:20].mean(),valid[-20:].mean())<.5:
        return dict(supported=False,coverage=float(valid.mean()),reason='incomplete_template_arc')
    def residual(r):
        return np.linalg.norm(observed-r,axis=1)-r
    fitted=least_squares(lambda r:residual(r)[valid],[radius],bounds=([radius*.65],[radius*1.35]),
                        loss='soft_l1',f_scale=max(.35,ppm*.025))
    measured=float(fitted.x[0]);errors=residual(measured)
    inliers=valid&(abs(errors)<max(.6,ppm*.055))
    rms=float(np.sqrt(np.mean(errors[inliers]**2))) if inliers.any() else 999.
    supported=bool(inliers.mean()>=.65 and min(inliers[:20].mean(),inliers[-20:].mean())>=.5
                   and rms<max(.45,ppm*.035))
    return dict(supported=supported,coverage=float(inliers.mean()),rms_px=rms,
                measured_radius_px=measured,
                template_rms_px=float(np.sqrt(np.mean(residual(radius)[inliers]**2))) if inliers.any() else 999.,
                plane_points=observed[inliers],reason='measured_near_template' if supported else 'arc_disagrees_with_template')


def fit_corners(gray: np.ndarray, geometry: dict) -> list[dict]:
    w,h=geometry['plane_size_px'];ppm=w/100.4
    sampler=CubicSampler(cv2.GaussianBlur(gray.astype('float32'),(0,0),max(.65,ppm*.045)))
    directions=np.column_stack([np.cos(np.deg2rad(np.linspace(12,78,65))),
                                np.sin(np.deg2rad(np.linspace(12,78,65)))])
    # A documented size prior, not a universal cassette manufacturing standard.
    radii_mm=np.arange(.8,4.5+.0125,.025);radii=radii_mm*ppm;prior_mm=2.
    corners=[(np.array([0.,0.]),np.array([1.,1.])),(np.array([w,0.]),np.array([-1.,1.])),
             (np.array([w,h]),np.array([-1.,-1.])),(np.array([0.,h]),np.array([1.,-1.]))]
    samplers=[];profiles=[]
    for origin,sign in corners:
        def sample(local,origin=origin,sign=sign):
            points=plane_to_source(origin+sign*local,geometry)
            inside=((points[...,0]>=1)&(points[...,0]<gray.shape[1]-2)&
                    (points[...,1]>=1)&(points[...,1]<gray.shape[0]-2))
            return np.where(inside,sampler.sample([points[...,1],points[...,0]]),np.nan)
        samplers.append(sample)
        points=radii[:,None,None]*(1-directions[None]);delta=max(.75,ppm*.04)
        strength=np.nan_to_num(abs(sample(points+directions*delta)-sample(points-directions*delta))/(2*delta),nan=0.)
        # Broad angular evidence and equal corner votes keep a dark rivet or
        # one high-contrast corner from determining the entire rectangle.
        profiles.append(np.percentile(np.minimum(strength,32),30,axis=1))
    profiles=np.array(profiles)
    clean=np.maximum(0,profiles-np.percentile(profiles,20,axis=1,keepdims=True))
    normalized=clean/np.maximum(clean.max(axis=1,keepdims=True),.5)
    joint=np.sort(normalized,axis=0)[1:3].mean(axis=0)
    objective=joint-.06*(radii_mm-prior_mm)**2
    peaks=find_peaks(objective,prominence=.015)[0]
    eligible=[i for i in peaks if joint[i]>=.30 and np.count_nonzero(normalized[:,i]>=.25)>=2]
    measured=bool(eligible)
    if measured:
        best=max(objective[eligible])
        candidate=min((i for i in eligible if objective[i]>=best-.02),key=lambda i:abs(radii_mm[i]-prior_mm))
        lo,mid,hi=objective[candidate-1:candidate+2];denominator=lo-2*mid+hi
        fraction=float(np.clip(.5*(lo-hi)/denominator,-.5,.5)) if denominator < -1e-8 else 0.
        shared=float((radii_mm[candidate]+fraction*.025)*ppm)
        score=float(joint[candidate]);agreeing=int(np.count_nonzero(normalized[:,candidate]>=.25))
    else:
        shared=prior_mm*ppm;score=0.;agreeing=0
    tilt=float(geometry.get('depth',{}).get('weak_perspective_tilt_proxy_degrees',0.))
    steep=tilt>=30.
    template=dict(model='shared_tangent_quarter_circles',radius_px=shared,radius_mm=shared/ppm,
                  evidence='joint_image_estimate' if measured else 'size_prior',prior_radius_mm=prior_mm,
                  search_radius_mm=[.8,4.5],joint_score=score,supporting_corners=agreeing,
                  steep_view=steep,tilt_proxy_degrees=tilt,steep_threshold_degrees=30.,
                  maximum_local_adjustment_fraction=.08 if steep else 0.,
                  note='One radius in the rectified plane. Size prior and view proxy are heuristic, not a calibrated shell standard or camera pose.')
    fits=[]
    for index,(sample,(origin,sign)) in enumerate(zip(samplers,corners)):
        observed=_observe_arc(sample,directions,shared,ppm)
        radius=shared;adjusted=False;local=observed.get('measured_radius_px',shared)
        agrees=observed['supported'] and abs(local/shared-1)<=.12
        # Large disagreement calls for frame review, not an exaggerated crop.
        if (measured and steep and agrees and abs(local/shared-1)<=.08 and
                observed['template_rms_px']>max(.35,observed['rms_px']*1.5)):
            radius=local;adjusted=True
        result=dict(corner=['top_left','top_right','bottom_right','bottom_left'][index],
                    applied=True,model='tangent_quarter_circle',radii_xy_px=[radius,radius],
                    fitted_radii_xy_px=[local,local],evidence='measured' if measured and agrees else 'inferred',
                    reason='bounded_steep_view_adjustment' if adjusted else 'shared_radius_template',
                    shared_template=template,local_adjustment_fraction=radius/shared-1,
                    local_adjustment_applied=adjusted,template_mismatch=bool(measured and not agrees),
                    coverage=observed['coverage'],rms_px=observed.get('rms_px'),
                    template_rms_px=observed.get('template_rms_px'),
                    arc_center_plane_px=(origin+sign*radius).tolist(),
                    tangent_points_plane_px=(origin+sign*np.array([[radius,0.],[0.,radius]])).tolist())
        if observed['supported']:
            result['source_points_px']=plane_to_source(origin+sign*observed['plane_points'],geometry).tolist()
        fits.append(result)
    return fits
