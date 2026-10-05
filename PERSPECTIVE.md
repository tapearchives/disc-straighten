# Perspective rectification in 0.3.0

The model uses two physical boundaries: the outer polycarbonate rim and the
spindle aperture. They are circles in the disc plane, but their camera projections
are ellipses whose fitted centers can differ. A photographed ellipse center is
not, in general, the projection of the physical disc center.

## Measurement and transform

1. OpenCV contours propose ellipses. Coverage and conic residuals reject most
   rectangular case edges and partial artwork. Strong printed rings can seed a
   search, but the search continues outward for the physical rim. It considers
   both bright-on-dark and subtle clear-plastic-on-white boundaries.
2. Subpixel profiles along ellipse normals locate gradient peaks. A robust
   geometric fit refines each physical boundary independently. Extended searches
   exclude the strong printing seed when recovering a weak, offset outer rim.
3. Symmetric affine normalization maps the outer ellipse to a unit circle. This
   step alone cannot recover the true proportions within the disc.
4. A circle-preserving projective transform is first fitted with a free aperture
   radius. That measured ratio is compared with the 120 mm and 80 mm profiles.
   Both use a 15 mm aperture: ratios 0.125 and 0.1875 respectively. A user can
   provide the size explicitly. Multiple plausible physical openings require review.
5. The default nominal policy jointly refits a shared homography against the
   original edge samples with the selected ratio fixed exactly. It minimizes
   robust normal-distance residuals in source pixels. An arbitrary noisy pair of
   measured ellipses cannot generally map exactly to an arbitrary fixed ratio;
   therefore raw measurements and constrained model ellipses are logged separately.
   Inconsistent evidence is rejected or flagged, not hidden by a nonlinear warp.
6. The resulting homography recovers the plane up to rotation, translation, and
   scale under the concentric-circle model. OCR consensus supplies the remaining
   readable rotation. All geometry and rotation are composed before the final
   EWA Lanczos3 warp in linear RGB. Temporary OCR images never become masters.
   For photo output widths up to 2000 pixels, two bounded output-scale OCR checks
   can refine the same winning family by up to two degrees. Coarse candidates
   remain in the log; `fine_alignment` records the additional evidence.

The implementation uses an independently written unit-circle projective
normalization, not copied calibration code from the cited papers. ImageMagick's
half-pixel coordinate convention is explicitly converted to and from the integer
pixel centers used in JSON. Source alpha excludes background and spindle content
before interpolation; an analytic final mask defines the round feathered edge.

Nominal mode always fits the plane, including nearly circular scans. If contour
proposals fail, scan circles initialize independent ellipse-edge fits; they do
not force the source to be circular. This scan route preserves the expected edge
polarity on a light background to avoid drifting onto interior artwork strokes.
Scan rim proposals require at least 80% angular support in absolute terms;
a fully visible printed ring does not raise that requirement for a weaker rim.
The source axis ratio and edge noise are logged as a roundness diagnostic. They
cannot prove exact circularity and do not disable the two-ring fit.

The explicit `--geometry-policy measured` retains the previous thresholds:
axis ratio below 0.985 or projective center-displacement parameter above 0.012.
Below them, independent scan circles remain. These are practical thresholds,
not camera-angle measurements or confidence levels. Source-circle overrides
and `--perspective off` require this policy. `on` still requires a usable pair.

## Accuracy and limits

The outer rim generally offers more samples and a larger geometric span for
fitting shape; the aperture can offer stronger contrast but fewer pixels and more
chamfer/hub interference. Neither should be unconditionally authoritative. Here
both are required: the outer rim determines the footprint, while the aperture's
projected displacement and conic shape constrain perspective. Offset silkscreen
is deliberately excluded from that physical concentricity assumption.

Two correctly identified coplanar concentric circles provide enough constraints
for metric rectification up to a similarity. A single outer ellipse does not.
Lens distortion, lens correction already applied by a phone, disc thickness,
chamfer, shadows, mistaken printed boundaries, or an obscuring hub can violate
the model. Subpixel fit residuals are consistency measurements, not an absolute
accuracy certification. No camera intrinsics or physical tilt angle is inferred.

Physical dimensions also have manufacturing tolerances and permitted runout;
see [STANDARDS.md](STANDARDS.md). Nominal concentricity and ratios are intentional
output normalization, not evidence of physically perfect source media. Zero
default knockout offsets preserve the exact nominal ratio at the continuous
50% alpha contours. Custom offsets can change it and are explicitly logged.

The algorithm cannot reconstruct an occluded or blurry region or remove glare.
An analytically round alpha boundary is guaranteed by the renderer; it is not
proof that every artwork point is physically correct. Severe foreshortening,
cropped rims, and hidden apertures need review or another photograph. Mini-disc
support is validated with synthetic camera controls; real mini photographs have
not yet been supplied. Pixel-grid sampling quantizes the analytic circles.

## Verification

The new tests project known concentric circles through independent camera
homographies, recover a rectification, and compare interior grid points after
removing only a similarity. This detects a transform that merely rounds the edge
while retaining projective distortion inside. Tests also use noisy boundary
samples and a physical rim only six gray levels below white with shifted printing.
Tests cover both nominal ratios, slight anisotropic stretches, and a projective
case with a circular outer outline but a displaced hole. Interior landmarks
distinguish true plane recovery from merely rounding the outline. Rendered
colored fiducials validate matrix ordering and half-pixel conventions; PNG
checks verify both modeled circles, encoded-alpha symmetry, area, aperture
transparency, bit depth, and hidden RGB.

The attached TDK case photograph is the real-photo example. Its printed logo is
deliberately slanted relative to the subtitle/legal text. The latter provides the
winning orientation evidence; the logo remains slanted after rectification.
Results and measured values are in `validation-report.json` and the per-image
logs. This is a four-design validation set, not a broad accuracy benchmark.

## Primary research and implementation references

- [Huang, Zhang, Cheung: The Common Self-Polar Triangle of Concentric Circles and
  Its Application to Camera Calibration, CVPR 2015](https://www.cv-foundation.org/openaccess/content_cvpr_2015/papers/Huang_The_Common_Self-Polar_2015_CVPR_paper.pdf).
  Projected concentric-circle constraints and the distinction between ellipse
  centers and projected physical centers.
- [Hao et al.: Conic tangents based high-precision extraction method of
  concentric circle centers, Scientific Reports 2021](https://www.nature.com/articles/s41598-021-00300-y).
  Geometric relationships for physical-center extraction under perspective.
- [OpenCV shape-analysis documentation](https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html).
  Contour and ellipse-fit primitives used for proposals, followed by our own
  robust subpixel refinement.
- [ImageMagick perspective projection and pixel-coordinate conventions](https://usage.imagemagick.org/distorts/#perspective_projection).
  Forward homography coefficients, reverse sampling, and image-coordinate origin.

Research links are background references, not additional bundled code or licenses.
