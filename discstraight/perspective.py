"""Physical conic detection and two-circle projective metric rectification.

An outer ellipse alone does not identify a perspective homography. Whiten it to
a unit circle, then solve the circle-preserving projective transform that makes
the measured spindle aperture concentric. Printed rings are not calibration data.
"""
from __future__ import annotations

import math

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d, map_coordinates
from scipy.optimize import least_squares
from scipy.signal import find_peaks

from .sampling import CubicSampler
from .profiles import select_profile


class PerspectiveDetectionError(ValueError):
    def __init__(self, message: str, *, suspected: bool = False):
        super().__init__(message)
        self.suspected = suspected


def rotation(angle: float) -> np.ndarray:
    c,s = np.cos(angle),np.sin(angle)
    return np.array([[c,-s],[s,c]])


def transform(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack([points,np.ones(len(points))])@matrix.T
    if np.any(abs(homogeneous[:,2])<1e-10):
        raise ValueError('Projective horizon intersects sampled geometry')
    return homogeneous[:,:2]/homogeneous[:,2,None]


def ellipse_points(ellipse: dict, n: int = 720) -> np.ndarray:
    theta = np.linspace(0,2*np.pi,n,endpoint=False)
    points = np.column_stack([np.cos(theta),np.sin(theta)])*ellipse['semiaxes_px']
    return points@rotation(ellipse['angle_radians']).T+ellipse['center_px']


def ellipse_distance(points: np.ndarray, ellipse: dict) -> np.ndarray:
    """First-order signed Euclidean distance, adequate near a measured contour."""
    axes = np.asarray(ellipse['semiaxes_px'])
    local = (points-ellipse['center_px'])@rotation(ellipse['angle_radians'])
    normalized = local/axes
    radius = np.linalg.norm(normalized,axis=1)
    derivative = np.linalg.norm(normalized/axes,axis=1)/np.maximum(radius,1e-12)
    return (radius-1)/np.maximum(derivative,1e-12)


def ellipse_fit(points: np.ndarray, seed: dict) -> dict:
    def unpack(p):
        return dict(center_px=p[:2],semiaxes_px=np.exp(p[2:4]),angle_radians=p[4])
    initial = np.r_[seed['center_px'],np.log(seed['semiaxes_px']),seed['angle_radians']]
    # Refine a local proposal, never an unbounded conic. Spurious case/shadow
    # contours otherwise allow enormous axes and numerical overflow.
    travel = max(seed['semiaxes_px'])*.25
    span = np.array([travel,travel,.4,.4,np.pi])
    fit = least_squares(lambda p:ellipse_distance(points,unpack(p)),initial,
                        bounds=(initial-span,initial+span),
                        loss='soft_l1',f_scale=.6,max_nfev=100)
    if not fit.success:
        raise ValueError('Ellipse refinement did not converge')
    ellipse = unpack(fit.x)
    residual = ellipse_distance(points,ellipse)
    ellipse.update(center_px=ellipse['center_px'].tolist(),semiaxes_px=ellipse['semiaxes_px'].tolist(),
                   angle_radians=float(ellipse['angle_radians']),
                   edge_rms_px=float(np.sqrt(np.mean(residual**2))),
                   edge_residual_p95_px=float(np.percentile(abs(residual),95)))
    return ellipse


def contour_ellipses(gray: np.ndarray) -> list[dict]:
    """Proposals only; physical outer-rim selection occurs after this step."""
    scale = min(1,1400/max(gray.shape))
    small = cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA) if scale<1 else gray
    output = []
    for low,high in [(15,45),(40,100),(80,180)]:
        contours,_ = cv2.findContours(cv2.Canny(small,low,high),cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            if len(contour)<40:
                continue
            center,axes,angle = cv2.fitEllipse(contour)
            axes = np.array(axes)/(2*scale); center = np.array(center)/scale
            if min(axes)<8 or max(axes)>max(gray.shape)*.8 or min(axes)/max(axes)<.25:
                continue
            ellipse = dict(center_px=center.tolist(),semiaxes_px=axes.tolist(),
                           angle_radians=math.radians(angle))
            points = contour[:,0].astype(float)/scale
            errors = ellipse_distance(points,ellipse)
            q = (points-center)@rotation(ellipse['angle_radians'])/axes
            bins = np.unique((np.mod(np.arctan2(q[:,1],q[:,0]),2*np.pi)*72/(2*np.pi)).astype(int))
            if len(bins)<58 or np.percentile(abs(errors),95)>max(2.5,np.sqrt(np.prod(axes))*.006):
                continue
            if any(np.linalg.norm(center-old['center_px'])<2/scale and
                   abs(np.sqrt(np.prod(axes))-np.sqrt(np.prod(old['semiaxes_px'])))<2/scale for old in output):
                continue
            output.append(dict(ellipse,coverage=len(bins)/72,
                               edge_residual_p95_px=float(np.percentile(abs(errors),95))))
    return sorted(output,key=lambda e:np.prod(e['semiaxes_px']),reverse=True)


def refine_edge(gray: np.ndarray, seed: dict, band: float, sign: int,
                exclude_inside: dict | None = None) -> tuple[dict,np.ndarray]:
    smooth = CubicSampler(gaussian_filter(gray.astype(float),.65))
    ellipse = seed.copy()
    offsets = np.arange(-band,band,.125)
    for _ in range(3):
        points = ellipse_points(ellipse)
        # Outward ellipse normals, as distinct from radial directions.
        r = rotation(ellipse['angle_radians']); axes = np.array(ellipse['semiaxes_px'])
        normals = ((points-ellipse['center_px'])@r/axes**2)@r.T
        normals /= np.linalg.norm(normals,axis=1)[:,None]
        samples = points[:,None,:]+normals[:,None,:]*offsets[None,:,None]
        values = smooth.sample([samples[:,:,1],samples[:,:,0]])
        gradients = np.gradient(values,.125,axis=1)
        strength = sign*gradients if sign else abs(gradients)
        if exclude_inside is not None:
            excluded = ellipse_distance(samples.reshape(-1,2),exclude_inside).reshape(samples.shape[:2])<3
            strength[excluded] = 0
        indices = strength.argmax(axis=1); rows = np.arange(len(points))
        valid = (indices>0)&(indices<len(offsets)-1)&(strength[rows,indices]>1.5)
        indices = np.clip(indices,1,len(offsets)-2)
        left,middle,right = strength[rows,indices-1],strength[rows,indices],strength[rows,indices+1]
        denominator = left-2*middle+right
        delta = np.divide(.5*(left-right),denominator,out=np.zeros_like(left),where=abs(denominator)>1e-9)
        selected = points+normals*(offsets[indices]+np.clip(delta,-1,1)*.125)[:,None]
        h,w = gray.shape
        valid &= (selected[:,0]>2)&(selected[:,0]<w-3)&(selected[:,1]>2)&(selected[:,1]<h-3)
        if valid.sum()<360:
            raise ValueError('Incomplete ellipse edge support')
        selected = selected[valid]
        ellipse = ellipse_fit(selected,ellipse)
    ellipse['coverage'] = float(valid.mean())
    return ellipse,selected


def physical_rim(gray: np.ndarray, seed: dict) -> tuple[dict,np.ndarray,dict]:
    """Search beyond a printed boundary for a coherent physical rim of either polarity."""
    center = np.array(seed['center_px']); axes = np.array(seed['semiaxes_px'])
    radius = np.sqrt(np.prod(axes)); theta = np.linspace(0,2*np.pi,720,endpoint=False)
    directions = np.column_stack([np.cos(theta),np.sin(theta)])*(axes/radius)
    directions = directions@rotation(seed['angle_radians']).T
    radii = np.arange(radius*.98,radius*1.28,.25)
    points = center+directions[:,None,:]*radii[None,:,None]
    values = map_coordinates(gaussian_filter(gray.astype(float),.7),[points[:,:,1],points[:,:,0]],order=3,mode='nearest')
    gradients = np.gradient(values,.25,axis=1)
    candidates = []
    for sign in [1,-1]:
        curve = gaussian_filter1d(np.mean(np.clip(sign*gradients,0,40),axis=0),3)
        peaks,_ = find_peaks(curve,prominence=.08,distance=12)
        for k in peaks:
            # A clear-plastic rim may be far weaker than silkscreen. Its angular
            # consistency, not a fraction of the strongest contrast, decides.
            # Offset printing smears a weak rim across the angular average;
            # individual normal profiles still must exceed 1.5 gray levels/px.
            if curve[k]<.2:
                continue
            proposal = dict(seed,semiaxes_px=(axes*radii[k]/radius).tolist())
            try:
                ellipse,edge = refine_edge(gray,proposal,max(2,radius*.009),sign)
            except ValueError:
                if radii[k]<=radius*1.025:
                    continue
                try:
                    # Exclude the strong seed printing so a broader search can
                    # recover an eccentric weak rim without snapping back to it.
                    ellipse,edge = refine_edge(gray,proposal,max(3,radius*.10),sign,seed)
                except ValueError:
                    continue
            if ellipse['coverage']<.72 or ellipse['edge_residual_p95_px']>max(2.5,radius*.007):
                continue
            candidates.append((ellipse,edge,sign,float(curve[k])))
    if not candidates:
        raise ValueError('No physical outer ellipse supported beyond the printed boundary')
    # Very partial case shadows cannot displace a nearly complete rim.
    support = max(c[0]['coverage'] for c in candidates)
    candidates = [c for c in candidates if c[0]['coverage']>=support*.9]
    chosen = max(candidates,key=lambda c:np.prod(c[0]['semiaxes_px']))
    return chosen[0],chosen[1],dict(candidates=[dict(ellipse=c[0],polarity=c[2],strength=c[3]) for c in candidates])


def boost(vector: np.ndarray) -> np.ndarray:
    """A projective automorphism of the unit circle (orientation preserving)."""
    squared = float(vector@vector)
    if squared>=.85**2:
        raise ValueError('Perspective too severe for stable reconstruction')
    gamma = 1/math.sqrt(1-squared)
    matrix = np.eye(3)
    if squared>1e-20:
        matrix[:2,:2] += (gamma-1)*np.outer(vector,vector)/squared
    matrix[:2,2] = -gamma*vector
    matrix[2,:2] = -gamma*vector
    matrix[2,2] = gamma
    return matrix


def projected_circle_ellipse(matrix: np.ndarray, radius: float) -> dict:
    """Exact source conic implied by a circle in the destination plane."""
    conic = matrix.T@np.diag([1.,1.,-radius**2])@matrix
    center = -np.linalg.solve(conic[:2,:2],conic[:2,2])
    level = -(center@conic[:2,:2]@center+2*conic[:2,2]@center+conic[2,2])
    values,vectors = np.linalg.eigh(conic[:2,:2]/level)
    if not np.isfinite(values).all() or min(values)<=0:
        raise ValueError('Nominal transform does not describe a bounded source ellipse')
    return dict(center_px=center.tolist(),semiaxes_px=(1/np.sqrt(values)).tolist(),
                angle_radians=float(np.arctan2(vectors[1,0],vectors[0,0])))


def nominal_fit(affine: np.ndarray, vector: np.ndarray, ratio: float,
                outer_points: np.ndarray, inner_points: np.ndarray, radius: float) -> tuple[np.ndarray,dict]:
    """Fit one homography to both boundaries with an exact target radius ratio.

    An arbitrary pair of measured conics cannot generally be mapped exactly to
    concentric circles at an arbitrary fixed ratio. Refit the shared model to
    the edge evidence instead of silently adding a nonlinear radial warp.
    """
    points = np.vstack([outer_points,inner_points])
    target = np.r_[np.ones(len(outer_points)),np.full(len(inner_points),ratio)]
    def matrix(p):
        adjustment = np.array([[np.exp(p[0]),p[1],p[3]],
                               [0,np.exp(p[2]),p[4]],[0,0,1.]])
        return boost(p[5:7])@adjustment@affine
    def residual(p):
        h = matrix(p)
        projected = transform(points,h)
        radii = np.linalg.norm(projected,axis=1)
        denominator = points@h[2,:2]+h[2,2]
        # Convert implicit radial error to a first-order source-pixel distance.
        gradient = ((projected/np.maximum(radii[:,None],1e-12))@h[:2,:2]
                    -radii[:,None]*h[2,:2])/denominator[:,None]
        return (radii-target)/np.maximum(np.linalg.norm(gradient,axis=1),1e-12)
    initial = np.r_[np.zeros(5),vector]
    bound = [.08,.08,.08,.05,.05,.55,.55]
    fit = least_squares(residual,initial,bounds=(-np.array(bound),bound),
                        loss='soft_l1',f_scale=.6,max_nfev=180,ftol=1e-10,xtol=1e-10,gtol=1e-10)
    if not fit.success:
        raise ValueError('Nominal two-ring fit did not converge')
    errors = residual(fit.x)
    outer_error,inner_error = errors[:len(outer_points)],errors[len(outer_points):]
    metrics = {name:dict(rms_px=float(np.sqrt(np.mean(e**2))),
                         residual_p95_px=float(np.percentile(abs(e),95)),samples=len(e))
               for name,e in [('outer',outer_error),('spindle',inner_error)]}
    if (metrics['outer']['residual_p95_px']>max(2.5,radius*.006) or
            metrics['spindle']['residual_p95_px']>max(3.,radius*ratio*.05)):
        raise ValueError('Physical edge evidence is inconsistent with the exact nominal annulus '
                         f"(outer p95 {metrics['outer']['residual_p95_px']:.2f} px, "
                         f"aperture p95 {metrics['spindle']['residual_p95_px']:.2f} px)")
    h = matrix(fit.x)
    metrics.update(iterations=int(fit.nfev),residual_units='source pixels, first-order normal distance',
                   max_affine_parameter_adjustment=float(max(abs(fit.x[:5]))),
                   fitted_perspective_strength=float(np.linalg.norm(fit.x[5:7])))
    return h,metrics


def rectify_concentric(outer: dict, inner: dict, *, disc_size: str = 'auto',
                       geometry_policy: str = 'measured', outer_edges: np.ndarray | None = None,
                       inner_edges: np.ndarray | None = None) -> dict:
    axes = np.array(outer['semiaxes_px']); r = rotation(outer['angle_radians'])
    affine = np.eye(3); affine[:2,:2] = r@np.diag(1/axes)@r.T
    affine[:2,2] = -affine[:2,:2]@outer['center_px']
    samples = transform(ellipse_points(inner,360),affine)
    initial = samples.mean(axis=0)
    if np.linalg.norm(initial)>.65:
        raise ValueError('Spindle candidate is too far from the disc center')
    def residual(parameters):
        points = transform(samples,boost(parameters[:2]))
        return np.linalg.norm(points,axis=1)-parameters[2]
    guess = [*initial,float(np.median(np.linalg.norm(samples-initial,axis=1)))]
    fit = least_squares(residual,guess,bounds=([-.55,-.55,.03],[.55,.55,.30]),
                        loss='soft_l1',f_scale=.001,max_nfev=200)
    h = boost(fit.x[:2])@affine
    h /= h[2,2]
    hole_ratio = float(fit.x[2])
    error = float(np.percentile(abs(residual(fit.x)),95)/hole_ratio)
    profile = select_profile(hole_ratio,disc_size)
    if not fit.success or error>.05:
        raise ValueError('Measured pair is inconsistent with a standard disc rim and spindle aperture')
    radius = float(np.sqrt(np.prod(axes)))
    extra = dict(geometry_policy=geometry_policy,disc_profile=profile,
                 measured_spindle_radius_ratio=hole_ratio)
    if geometry_policy=='nominal':
        hole_ratio = profile['nominal_radius_ratio']
        h,metrics = nominal_fit(affine,fit.x[:2],hole_ratio,
                                ellipse_points(outer) if outer_edges is None else outer_edges,
                                ellipse_points(inner) if inner_edges is None else inner_edges,radius)
        extra['nominal_fit'] = metrics
    elif geometry_policy!='measured':
        raise ValueError('Geometry policy must be nominal or measured')
    output_scale = np.diag([radius,radius,1.0])
    h = output_scale@h
    h /= h[2,2]
    projected_center = transform(np.zeros((1,2)),np.linalg.inv(h))[0]
    if geometry_policy=='nominal':
        extra.update(model_source_outer_ellipse=projected_circle_ellipse(h,radius),
                     model_source_spindle_ellipse=projected_circle_ellipse(h,radius*hole_ratio))
    return dict(source_to_plane_matrix=h.tolist(),plane_outer_circle=dict(center_px=[0.,0.],radius_px=radius),
                plane_spindle_circle=dict(center_px=[0.,0.],radius_px=hole_ratio*radius),
                projected_physical_center_px=projected_center.tolist(),
                perspective_strength=float(np.linalg.norm(fit.x[:2])),
                source_axis_ratio=float(min(axes)/max(axes)),spindle_radius_ratio=hole_ratio,
                spindle_conic_mismatch_fraction=error,
                method=('joint physical-edge homography fit with exact nominal annulus' if geometry_policy=='nominal' else
                        'outer conic metric normalization plus concentric-aperture projective boost'),
                assumption='physical outer rim and physical aperture are coplanar concentric circles; uncalibrated lens',**extra)


def detect_perspective(gray: np.ndarray, *, disc_size: str = 'auto', geometry_policy: str = 'measured') -> dict:
    candidates = contour_ellipses(gray)
    minimum = min(gray.shape)
    proposals = [e for e in candidates if np.sqrt(np.prod(e['semiaxes_px']))>minimum*.22]
    if not proposals:
        raise PerspectiveDetectionError('No sufficiently complete outer ellipse found')
    suspected = any(min(e['semiaxes_px'])/max(e['semiaxes_px'])<.94 for e in proposals[:2])
    # Try the largest supported closed outlines. Rectangular case edges fail the
    # conic residual/coverage tests; a printed circle can seed the physical search.
    for seed in proposals[:4]:
        try:
            outer,outer_edges,diagnostics = physical_rim(gray,seed)
        except ValueError:
            continue
        radius = np.sqrt(np.prod(outer['semiaxes_px']))
        possible_holes = [e for e in candidates if .08*radius<np.sqrt(np.prod(e['semiaxes_px']))<.24*radius
                          and np.linalg.norm(np.array(e['center_px'])-outer['center_px'])<radius*.55]
        solutions = []
        for initial in possible_holes:
            try:
                hole,hole_edges = refine_edge(gray,initial,max(1.5,radius*.004),0)
                rectification = rectify_concentric(outer,hole,disc_size=disc_size,geometry_policy=geometry_policy,
                                                    outer_edges=outer_edges,inner_edges=hole_edges)
            except ValueError:
                continue
            score = abs(rectification['disc_profile']['relative_ratio_deviation'])+rectification['spindle_conic_mismatch_fraction']
            solutions.append((score,hole,hole_edges,rectification))
        if solutions:
            best_score,hole,hole_edges,rectification = min(solutions,key=lambda c:c[0])
            warnings = []
            diagnostics['spindle_candidates'] = [dict(score=score,ellipse=e,disc_profile=r['disc_profile'])
                                                  for score,e,_,r in solutions]
            if disc_size=='auto' and any(r['disc_profile']['outer_diameter_mm']!=rectification['disc_profile']['outer_diameter_mm']
                                        for _,_,_,r in solutions):
                warnings.append('disc_size_ambiguous')
            return assessed_pair(gray,outer,hole,rectification,diagnostics,warnings)
    raise PerspectiveDetectionError('Could not establish a physical rim/aperture pair for perspective correction',
                                    suspected=suspected)


def assessed_pair(gray: np.ndarray, outer: dict, hole: dict, rectification: dict,
                  diagnostics: dict, warnings: list[str]) -> dict:
    radius = rectification['plane_outer_circle']['radius_px']
    if rectification['spindle_conic_mismatch_fraction']>.025:
        warnings.append('perspective_concentric_model_uncertain')
    if outer['edge_residual_p95_px']>max(2,radius*.005):
        warnings.append('outer_ellipse_irregular_or_uncertain')
    if min(outer['coverage'],hole['coverage'])<.90:
        warnings.append('ellipse_incomplete_edge_support')
    nominal = rectification.get('nominal_fit')
    if nominal and (nominal['outer']['residual_p95_px']>max(2,radius*.005) or
                    nominal['spindle']['residual_p95_px']>max(1.5,radius*rectification['spindle_radius_ratio']*.03)):
        warnings.append('nominal_annulus_edge_fit_uncertain')
    rim_points = ellipse_points(outer)
    height,width = gray.shape
    if (rim_points.min()<1 or np.any(rim_points[:,0]>width-2)
            or np.any(rim_points[:,1]>height-2)):
        warnings.append('source_touches_or_clips_disc_boundary')
    axis_difference = max(outer['semiaxes_px'])-min(outer['semiaxes_px'])
    diagnostics['source_roundness'] = dict(axis_ratio=rectification['source_axis_ratio'],
        semiaxis_difference_px=axis_difference,
        consistent_with_circle_at_edge_noise=axis_difference<=max(.5,2*outer['edge_residual_p95_px']),
        note='Heuristic comparison with edge residuals, not proof of perfect source circularity')
    needs = (rectification['geometry_policy']=='nominal' or rectification['source_axis_ratio']<.985 or
             rectification['perspective_strength']>.012)
    return dict(outer_ellipse=outer,spindle_ellipse=hole,rectification=rectification,
                needs_rectification=needs,warnings=list(dict.fromkeys(warnings)),diagnostics=diagnostics)


def detect_scan_pair(gray: np.ndarray, *, disc_size: str = 'auto') -> dict:
    """Use scan-circle proposals when contours are broken, then refit real ellipses.

    Never treat the proposal circles as evidence of circularity: the same
    independently measured edge points and fixed-ratio fit remain required.
    """
    from .geometry import detect
    circles = detect(gray,disc_size=disc_size)
    shapes = []
    for key in ['outer_circle','spindle_circle']:
        circle = circles[key]
        seed = dict(center_px=circle['center_px'],semiaxes_px=[circle['radius_px']]*2,angle_radians=0.)
        # This route is specifically a light-background scan. Preserve edge
        # polarity so refinement cannot drift onto the opposite side of a
        # printed stroke or reflective rim highlight.
        sign = 1 if key=='outer_circle' else -1
        shapes.append(refine_edge(gray,seed,max(1.5,circle['radius_px']*.004),sign))
    (outer,outer_edges),(hole,hole_edges) = shapes
    rectification = rectify_concentric(outer,hole,disc_size=disc_size,geometry_policy='nominal',
                                        outer_edges=outer_edges,inner_edges=hole_edges)
    diagnostics = dict(circles['diagnostics'],selection='scan proposals followed by independent ellipse-edge refinement',
                       scan_circle_proposals={k:circles[k] for k in ['outer_circle','spindle_circle']})
    return assessed_pair(gray,outer,hole,rectification,diagnostics,circles['warnings'])
