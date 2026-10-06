"""Verify scan controls and the optional private photo without declaring ground truth."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import cv2

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from discstraight import __version__
from discstraight.perspective import ellipse_points, transform

ANGLES = {'Label':12.5,'mobile-computers':-.75,'computerra':-6.7,
          'mobile-117':-117.75,'computerra-90':-96.7}
RADII = {'Label':(297.703661,36.244586),'mobile-computers':(708.104167,89.219841),
         'computerra':(951.045846,118.66613)}


def verify_nominal_geometry(data: dict, alpha: np.ndarray) -> dict:
    """Check the transform, both circles, and actual encoded alpha independently."""
    profile=data['measurements']['disc_profile']
    output=data['output']; outer=output['outer_circle']; hole=output['spindle_circle']
    ratio=hole['radius_px']/outer['radius_px']
    assert math.isclose(ratio,15/profile['outer_diameter_mm'],rel_tol=1e-12)
    assert data['knockouts']['nominal_ratio_preserved']
    np.testing.assert_allclose(outer['center_px'],hole['center_px'],atol=1e-10)
    matrix=np.array(output['source_to_output_matrix'])
    errors={}
    for name,circle in [('outer',outer),('spindle',hole)]:
        points=transform(ellipse_points(data['perspective'][f'model_source_{name}_ellipse']),matrix)
        error=abs(np.linalg.norm(points-circle['center_px'],axis=1)-circle['radius_px']).max()
        assert error<1e-7
        errors[name]=float(error)
    symmetry=max(float(abs(alpha-other).max()) for other in [alpha.T,alpha[::-1],alpha[:,::-1]])
    assert symmetry<=1/65535
    contours,_=cv2.findContours((alpha>=.5).astype('uint8'),cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
    fits=[]
    for contour in contours:
        if len(contour)>5:
            center,axes,angle=cv2.fitEllipse(contour)
            fits.append(dict(center_px=list(center),diameters_px=list(axes),axis_ratio=min(axes)/max(axes)))
    fits.sort(key=lambda f:max(f['diameters_px']),reverse=True)
    assert len(fits)==2
    assert all(abs(f['axis_ratio']-1)<1e-6 for f in fits)
    return dict(nominal_outer_diameter_mm=profile['outer_diameter_mm'],spindle_to_outer_radius_ratio=ratio,
                maximum_transformed_model_circle_error_px=errors,
                alpha_symmetry_max_difference=symmetry,fitted_50_percent_alpha_contours=fits,
                note='Exact analytic geometry within numerical precision; binary contour radii have pixel quantization.')


def verify(folder: Path) -> dict:
    reports = []
    references = dict(ANGLES)
    if (folder/'tdk-photo-straightened.json').exists():
        references['tdk-photo'] = -3.76
    for stem,angle_reference in references.items():
        path = folder/f'{stem}-straightened.json'
        data = json.loads(path.read_text()); image = folder/data['output']['file']
        raw_file = image.read_bytes()
        assert hashlib.sha256(raw_file).hexdigest()==data['output']['sha256']
        assert raw_file[24:26]==bytes([16,6]), 'PNG must actually be 16-bit RGBA'
        width,height = data['output']['width'],data['output']['height']
        raw = subprocess.check_output(['magick',str(image),'-depth','16','-endian','LSB','rgba:-'])
        pixels = np.frombuffer(raw,dtype='<u2').reshape(height,width,4)
        alpha = pixels[:,:,3]/65535
        assert not pixels[:,:,:3][pixels[:,:,3]==0].any(), 'Hidden RGB must be zero'
        if data['output'].get('transparent_padding_px')==0:
            assert all(edge.any() for edge in (alpha[0],alpha[-1],alpha[:,0],alpha[:,-1]))
        else:
            assert not alpha[0].any() and not alpha[-1].any()
            assert not alpha[:,0].any() and not alpha[:,-1].any()
        x,y = map(round,data['output']['spindle_circle']['center_px'])
        assert alpha[y,x]==0
        ro = data['output']['outer_circle']['radius_px']; rh = data['output']['spindle_circle']['radius_px']
        area_error = abs(alpha.sum()/(math.pi*(ro**2-rh**2))-1)
        assert area_error<.0002
        angle = data['rotation']['clockwise_degrees']
        angle_error = abs((angle-angle_reference+180)%360-180)
        assert angle_error<1, 'Orientation differs from reviewed reference by more than one degree'
        circles = data['measurements']
        radii = [circles[k]['radius_px'] for k in ['outer_circle','spindle_circle']]
        radius_errors = [abs(a-b) for a,b in zip(radii,RADII[stem])] if stem in RADII else None
        if radius_errors:
            assert max(radius_errors)<2, 'Radius differs from reviewed comparison fit by more than two pixels'
        nominal_checks = (verify_nominal_geometry(data,alpha) if data.get('geometry_policy')=='nominal' else None)
        perspective_checks = None
        if stem=='tdk-photo':
            perspective = data['perspective']
            assert perspective['applied'], 'Photo must use measured perspective correction'
            assert perspective['spindle_conic_mismatch_fraction']<.01
            center = data['measurements']['projected_physical_center_px']
            matrix = np.array(data['output']['source_to_output_matrix'])
            np.testing.assert_allclose(transform(np.array([center]),matrix)[0],
                                       data['output']['outer_circle']['center_px'],atol=1e-7)
            source_model = perspective.get('model_source_outer_ellipse',circles['source_outer_ellipse'])
            rim = transform(ellipse_points(source_model),matrix)
            outer = data['output']['outer_circle']
            deviations = np.linalg.norm(rim-outer['center_px'],axis=1)-(outer['radius_px']+data['knockouts']['outer_inset_px'])
            assert abs(deviations).max()<1e-7
            np.testing.assert_allclose(data['output']['spindle_circle']['center_px'],outer['center_px'],atol=1e-8)
            assert circles['source_ellipse_center_separation_px']>25
            perspective_checks = dict(source_ellipse_center_separation_px=circles['source_ellipse_center_separation_px'],
                                      projected_physical_center_px=center,
                                      outer_ellipse=circles['source_outer_ellipse'],
                                      spindle_ellipse=circles['source_spindle_ellipse'],
                                      spindle_conic_mismatch_fraction=perspective['spindle_conic_mismatch_fraction'],
                                      maximum_transformed_rim_roundness_error_px=float(abs(deviations).max()),
                                      checks='Matrix/alpha consistency; not independent physical metrology')
        elif not nominal_checks:
            assert not data['perspective']['applied'], 'Scan controls must retain their original geometry path'
        reports.append(dict(name=stem,clockwise_degrees=angle,reviewed_angle_reference=angle_reference,
                            angle_error_degrees=angle_error,status=data['status'],warnings=data['warnings'],
                            orientation_status=data['rotation']['status'],
                            competing_directions=data['rotation']['candidates'],
                            radius_errors_vs_prior_reviewed_fit_px=radius_errors,
                            alpha_area_relative_error=area_error,output_sha256=data['output']['sha256'],
                            perspective=perspective_checks,nominal_geometry=nominal_checks))
    return dict(tool_version=__version__,real_inputs=3+('tdk-photo' in references),rotated_controls=2,
                result='Geometry/angle comparison tolerances, hashes, PNG depths, and alpha checks passed.',
                limitations='Reviewed fits and angles are comparison estimates, not metrology ground truth. '
                            'The optional photo has model checks plus visual review, not a calibrated reference capture.',
                cases=reports)


if __name__=='__main__':
    result = verify(Path(sys.argv[1]))
    text = json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if len(sys.argv)>2:
        Path(sys.argv[2]).write_text(text)
    else:
        print(text)
