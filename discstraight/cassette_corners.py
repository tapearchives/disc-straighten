"""Fit small shell corner arcs in the established cassette plane.

No corner radius is taken from a format template. Unsupported corners stay square.
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


def fit_corners(gray: np.ndarray, geometry: dict) -> list[dict]:
    w,h=geometry['plane_size_px'];span=min(w,h)
    sampler=CubicSampler(cv2.GaussianBlur(gray.astype('float32'),(0,0),1.5 if span>700 else .65))
    angles=np.linspace(np.deg2rad(12),np.deg2rad(78),65)
    directions=np.column_stack([np.cos(angles),np.sin(angles)])
    radii=np.arange(max(1.,span*.003),span*.10,.5)
    corners=[(np.array([0.,0.]),np.array([1.,1.])),(np.array([w,0.]),np.array([-1.,1.])),
             (np.array([w,h]),np.array([-1.,-1.])),(np.array([0.,h]),np.array([1.,-1.]))]
    fits=[]
    for index,(origin,sign) in enumerate(corners):
        def sample(local):
            points=plane_to_source(origin+sign*local,geometry)
            inside=((points[...,0]>=1)&(points[...,0]<gray.shape[1]-2)&
                    (points[...,1]>=1)&(points[...,1]<gray.shape[0]-2))
            return np.where(inside,sampler.sample([points[...,1],points[...,0]]),np.nan)
        points=radii[:,None,None]*(1-directions[None])
        gradients=np.nan_to_num(abs(sample(points+directions)-sample(points-directions))/2,nan=0.)
        # Saturating gradient votes prevents a dark screw from overwhelming the
        # weaker, broadly supported plastic/background transition.
        scores=np.mean(np.minimum(gradients,6),axis=1)
        peak=float(scores.max())
        peaks=find_peaks(scores,prominence=.07)[0]
        eligible=[i for i in peaks if scores[i]>=max(.7,peak*.15) and np.mean(gradients[i]>.5)>=.65]
        result=dict(corner=['top_left','top_right','bottom_right','bottom_left'][index],
                    applied=False,model='tangent_quarter_ellipse',reason='insufficient_arc_evidence')
        if not len(eligible):
            fits.append(result);continue
        for candidate in eligible:
            fitted=_refine_arc(sample,directions,float(radii[candidate]),float(scores[candidate]),span)
            if fitted['applied']:
                result.update(fitted)
                points=result.pop('plane_points')
                result['source_points_px']=plane_to_source(origin+sign*points,geometry).tolist()
                break
            result.update(fitted)
        fits.append(result)
    return fits


def _refine_arc(sample, directions: np.ndarray, radius: float, peak: float, span: float) -> dict:
    radius_xy=np.array([radius,radius]);band=max(1.5,min(4.,span*.002))
    offsets=np.arange(-band,band+.125,.25)
    for _ in range(4):
        p=radius_xy*(1-directions)
        normals=directions/radius_xy;normals/=np.linalg.norm(normals,axis=1)[:,None]
        candidates=p[:,None]+offsets[None,:,None]*normals[:,None]
        strength=np.nan_to_num(abs(sample(candidates+normals[:,None])-sample(candidates-normals[:,None]))/2,nan=0.)
        objective=np.log1p(strength)-.15*(offsets[None]/band)**2
        ids=objective.argmax(axis=1);shifts=offsets[ids]
        values=strength[np.arange(len(ids)),ids]
        valid=(ids>0)&(ids<len(offsets)-1)&(values>max(.45,peak*.15))
        observed=p+shifts[:,None]*normals
        if valid.mean()<.4:
            return dict(applied=False,reason='insufficient_arc_evidence',coverage=float(valid.mean()))
        def residual(r):
            z=(observed-r)/r
            return (np.sum(z*z,axis=1)-1)/np.maximum(2*np.linalg.norm(z/r,axis=1),1e-8)
        fitted=least_squares(lambda r:residual(r)[valid],radius_xy,
                            bounds=([max(.5,radius*.65)]*2,[min(span*.14,radius*1.35)]*2),
                            loss='soft_l1',f_scale=max(.65,span*.0007))
        radius_xy=fitted.x
    errors=residual(radius_xy);inliers=valid&(abs(errors)<max(1.2,span*.0018))
    coverage=float(inliers.mean());rms=float(np.sqrt(np.mean(errors[inliers]**2))) if inliers.any() else 999.
    supported=(coverage>=.65 and np.count_nonzero(inliers[:20])>=10 and
               np.count_nonzero(inliers[-20:])>=10 and rms<max(.35,float(np.mean(radius_xy))*.04))
    result=dict(applied=False,reason='insufficient_arc_evidence',coverage=coverage,rms_px=rms,
                gradient_score=peak,fitted_radii_xy_px=radius_xy.tolist())
    if supported:
        allowance=min(max(.4,rms),1.5)
        result.update(applied=True,reason='measured_outer_arc',
                      radii_xy_px=np.maximum(0,radius_xy-allowance/(np.sqrt(2)-1)).tolist(),
                      outward_allowance_px=allowance,plane_points=observed[inliers])
    return result
