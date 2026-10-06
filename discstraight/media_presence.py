"""Keep barcode-only reference captures from consuming a neighboring media side."""
from __future__ import annotations

import cv2
import numpy as np


def catalog_reference(gray: np.ndarray, barcodes: dict, args) -> dict | None:
    """Only gate barcode naming with gap accounting; ordinary processing is unchanged."""
    from .barcodes import filename_code
    if not (getattr(args, 'name_barcode_pairs', False) and getattr(args, 'gap_placeholders', False)):
        return None
    code, _ = filename_code(barcodes)
    if code is None:
        return None
    # Reviewed geometry is stronger evidence than this deliberately coarse check.
    if getattr(args, 'cassette_corners', None) or getattr(args, 'outer', None):
        return None
    observed = evidence(gray)
    if observed['status'] == 'supported':
        return None
    return dict(catalog=code, reason='barcode_reference_media_unverified', media_evidence=observed)


def evidence(gray: np.ndarray) -> dict:
    """Coarse presence evidence only; absence is a review flag, not a physical claim."""
    from .cassette import proposals, reel_evidence
    scale=min(1.,640/max(gray.shape))
    small=cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
    candidates=proposals(small)
    best=0.
    for quad in candidates[:80]:
        score=reel_evidence(small,quad)['score']
        best=max(best,score)
        if best>=.35:
            return dict(status='supported',media='cassette',reel_score=best,method='coarse_body_and_reel_pair')
    # A barcode on a disc is legitimate too. Require a substantial closed rim;
    # do not require the spindle, which a sticker/case hub can hide.
    for low,high in [(10,35),(30,90)]:
        edges=cv2.Canny(small,low,high)
        contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            if len(contour)<80:continue
            center,axes,angle=cv2.fitEllipse(contour)
            a,b=np.array(axes)/2
            if min(a,b)<min(small.shape)*.18 or max(a,b)>max(small.shape)*.55:continue
            theta=np.deg2rad(angle);cs,sn=np.cos(theta),np.sin(theta)
            points=contour[:,0]-np.array(center)
            local=points@np.array([[cs,-sn],[sn,cs]])
            radius=np.linalg.norm(local/np.array([a,b]),axis=1)
            bins=np.unique((np.mod(np.arctan2(local[:,1]/b,local[:,0]/a),2*np.pi)*36/(2*np.pi)).astype(int))
            if len(bins)>=30 and np.quantile(abs(radius-1),.90)<.025:
                return dict(status='supported',media='disc',reel_score=best,method='closed_large_ellipse')
    return dict(status='unverified',media=None,reel_score=best,rectangle_candidates=len(candidates),
                method='no_supported_reel_pair_or_disc_rim',
                limitation='May be an empty case, a barcode-only reference, or an obscured/unsupported media photo. Review the preserved source.')
