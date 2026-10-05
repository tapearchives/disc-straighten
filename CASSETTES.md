# Compact-cassette geometry and implementation

Version 0.6.0; dimensional research checked September 30, 2026. A reviewed cassette beta is implemented. The detailed [JSON profile](research/cassette-reference-profile.json) remains research data; only nominal body dimensions and reel spacing guide runtime fitting. Five supplied photographs informed development; no broad or held-out recognition accuracy is claimed.

## Source hierarchy and access

The requested [Reddit discussion](https://www.reddit.com/r/askmath/comments/iylvxe/mathematical_system_for_djing_compact_cassette/)
was re-read through Chrome on September 30, 2026. All seven reference images
loaded and were visually inspected. The [image catalog and dimensional comparison](research/REDDIT_IMAGE_REFERENCES.md)
distinguish label templates, an unsourced CAD sketch, an inch-based mechanical
drawing, maximum window area, and product/cutaway photos. This supersedes the
earlier attachment-access limitation. Primary standards and patent descriptions
remain the basis for the nominal dimensions below; the reposted drawings supply
corroboration and useful examples, not verified standards provenance.

| Source | Inspected material | Use and limitation |
| --- | --- | --- |
| [IEC 60094-7:1986](https://webstore.iec.ch/en/publication/728) | Official scope; [SIST adoption preview](https://cdn.standards.iteh.ai/samples/4705/b2328da0eace4eb898e73bdafdbb4b6c/SIST-EN-60094-7-1999.pdf), PDF p.11 / printed p.9 | Governing audio-cassette mechanical reference. Preview defines reference planes but ends before the dimensional figures; full dimensional conformity has not been verified against the complete edition and amendments. |
| [ECMA-34, third edition (1976)](https://ecma-international.org/wp-content/uploads/ECMA-34_3rd_edition_september_1976.pdf) | Figure 4, PDF p.25 / printed p.23; Figure 5, PDF p.26 / printed p.25 | Public dimensional drawing for the 3.81 mm **data** cassette. Useful historical corroboration and provisional landmark geometry; withdrawn, and not a replacement for the audio standard. |
| [US5566037A](https://patents.google.com/patent/US5566037A/en) | [PDF](https://patentimages.storage.googleapis.com/b1/93/d2/b987f72d93a9dc/US5566037.pdf), Fig.11, PDF p.12 / sheet 11; conventional C-cassette description | Confirms 100.4 × 63.8 mm body, different thicknesses, and distinction between main-body width and side-projection span. Its DCC discussion is a different format. |
| [US5161079A](https://patents.google.com/patent/US5161079A/en) | [PDF](https://patentimages.storage.googleapis.com/b0/78/f0/7c30cb0cb0965e/US5161079.pdf), Fig.5, PDF p.4 / sheet 3; conventional cassette description | Independently states 42.5 mm reel-hole spacing. Fig.5 is identified as prior art; the patent's new shutter cassette is not the baseline. |
| [US4809928A](https://patents.google.com/patent/US4809928A/en) | [PDF](https://patentimages.storage.googleapis.com/b5/5c/de/6ceb8ae576a4f3/US4809928.pdf), Figs.1–3, PDF pp.2–3; description | Shows separate shell, tape guide, reference regions, and raised front structures. Useful for understanding construction variation; no new exact dimensions inferred from drawing scale. |

Patents corroborate dimensions and feature meanings; they are not metrology
standards. No dimension was measured from the pixel scale of an undimensioned
patent illustration. Downloaded publications are excluded from the public source
package. The [schematic](docs/cassette-reference.svg) is an original explanatory
drawing, not a reproduction of a standards figure.

## Candidate dimensional baseline

Here, **width** is the long left-to-right body dimension; **height** runs from
the rear edge to the tape-access edge. This vocabulary differs from some patent
descriptions. All dimensions below are millimeters. Values are nominal, with
manufacturing tolerance where established by the inspected drawing.

| Reference | Baseline | Evidence and fitting policy |
| --- | ---: | --- |
| Main body width, excluding side projections | 100.4; ECMA tolerance ±0.3 | ECMA Fig.4; US5566037 body description. Primary calibration span. |
| Rear edge to prime reference line | 56.9 ±0.3 | ECMA Fig.4. A datum distance, **not the total shell height**. |
| Prime reference line to tape-access edge | 6.9 ±0.2 | ECMA Fig.4. Together the two distances give nominal 63.8. |
| Main body height | 63.8 | US5566037; corroborated by 56.9 + 6.9 in ECMA. A conservative arithmetic envelope from those ECMA distances is ±0.5, not a directly printed audio-standard tolerance. |
| Derived body width / height | 1.5736677 | 100.4 / 63.8. Use after rectification; not as a hard ratio in a perspective source image. |
| Reel-axis / reel-opening center separation | 42.5 ±0.3 in ECMA; 42.5 in US5161079 | Strong second-scale check after body rectification. Fit fixed opening rims rather than freely rotating teeth or tape-pack edges. |
| Reel-axis line to prime reference line | 27.9 ±0.15 | ECMA Fig.4. Implies nominal rear-edge-to-reel-axis distance 56.9 − 27.9 = 29.0. Provisional until checked against full audio drawings. |
| Inner positioning/reference-hole pair spacing | 28 ±0.15 | ECMA Fig.4. These are the **inner** pair, not the farther-apart capstan holes. Their reference geometry is not simply four identical circles. |
| Outer capstan-hole pair spacing | 48 ±0.2 | ECMA Fig.4. The outer pair of small holes near the tape-access edge. |
| Capstan opening diameter | 4.5, +0.3/−0.1 | ECMA Fig.4. A provisional aperture-boundary reference, not a reel-hole size. |
| Main-body thickness / raised-front total thickness | 8.6 / 12.0, both +0.3/−0.1 | ECMA side view; US5566037 confirms both. Symmetric nominal construction implies a 1.7 mm surface-height step per side. |

The detailed pin-hole tolerances are **historical ECMA reference values**, not
assertions that all audio shells comply with that data-cassette edition. Check
the complete applicable IEC drawings before promoting them to hard constraints.
Some shell designs use different-looking apertures, chamfers, recesses, or slots.
Screw holes, window shape, printed borders, label cutouts, hub teeth, and the
diameter of wound tape are not universal calibration features.

US5161079's additional 34 mm dimension refers to a lateral half-span at the
front window portion. It is not a body height or a reel-to-bottom distance.
The large rectangular head/pinch-roller openings in a front-edge view must also
not be confused with the small holes seen on the broad face.

## Body detection and calibration

`--media cassette` uses grayscale analysis at up to 900 pixels on the long side.
Several Canny thresholds, closed contours, line-segment proposals, and border
seeds provide candidate frames. A dynamic-programming edge trace follows local
absolute gradient strength, so contrast may reverse across a mixed black/white
background. Path continuity discourages jumps to printing or a nearby shadow.

A robust quadratic consensus fit rejects short localized edge excursions, such
as guide projections. Rounded corners are excluded from support. Full-resolution
normal profiles use 0.125-pixel steps and local gradient-peak refinement. The
default then selects straight ridges supported across the body edge, excluding
rounded corners and short rail protrusions. If a blurred edge has insufficient
ridge support, one straight line is fitted to its traced main-body samples; the
fallback and residual are logged. **Virtual corners are the intersections of
four fitted straight lines**, never curve intersections in the default mode.
A whole-object bounding rectangle is only a proposal, never the final scale
reference.

Candidates also need a plausible reel pair after provisional rectification, using
42.5/100.4 as a soft spacing check. Rotating teeth, tape-pack edges, decorative
circles, or a case can still confuse that evidence. Reel centers validate the
candidate; they do not set the final body scale or force apertures to be circular.
Small pin holes and raised-front features are not fitted as universal landmarks.

The frame maps to nominal 100.4 × 63.8 mm. That ratio belongs to the continuous
body frame and the final crop rectangle, without an additional inset. Feather
and integer sampling mean the encoded alpha bounding box need not have exactly
that ratio.
Correct dimensions do not establish that the correct physical layer was
selected. Manufacturing tolerances remain real.

## Bow and depth correction

The default `--debow off` uses only a planar homography. Without a calibrated
lens profile, no lens correction or nonlinear edge adjustment is assumed.
Explicit experimental `auto` and `conform` modes retain the earlier curved-edge
models for reviewed comparisons. `auto` requires agreement across multiple
edges before applying its radial estimate; `conform` chooses the approximate
boundary blend. [Lens distortion and depth](LENS_AND_DEPTH.md) explains the equations,
threshold policy, examples, disc implications, and limitations.

The nominal cassette front is thicker than the main body. The current detector
does not reliably classify every visible shoulder, bevel, and lip into separate
planes. A single homography plus a small edge blend cannot reconstruct all of
them head-on. Logs always flag this assumption. A future stricter mode would
use identified main-face shoulders, camera calibration, and a stepped 3D model;
hidden surfaces would still require additional captures.

## Media selection and orientation

`--media disc` remains the default. `--media auto` first tests body plus reel-pair
evidence. A cassette score of at least 0.65 selects the cassette branch; otherwise
the existing disc detector must establish its own rim/aperture geometry. If it
cannot, processing fails. The score is not a calibrated probability. An unknown
object is not declared a valid disc merely because cassette fitting failed.

This is a first routing heuristic, not a general object recognizer: it does not
compare calibrated class probabilities, discover multiple objects, or guarantee
that a cassette illustration inside another object is rejected. Near frontal
circularity and rectangle aspect ratio are useful proposals only; perspective,
shadows, rails, and transparency defeat a pure circle-versus-box test.

Cassette body geometry locks the long edges horizontally. Two opposed OCR views
select 0 or 180 degrees in that plane. Confidence and text height weight capped
letter counts; the top five lines dominate the balanced score, limiting dense
small print. Text can be deliberately diagonal or sideways, so weak or conflicting
OCR requires review. Fine text slant does not rotate the already level body.
This is not semantic recognition of primary versus artistic text.

## Exterior mask and image quality

The current cassette path keeps all source pixels through one composed geometry
warp. The full nominal body rectangle is cropped only in the final corrected
plane. Alpha comes from four straight sides, independently measured corner arcs, and a slight centered
smoothstep feather (`--feather`, at least one output pixel). No color key,
exterior flood fill, silhouette trace, guessed corner arc, safety inset, or
opaque retention band modifies alpha. Color and edge contrast may estimate the
plane, but cannot independently erase pixels.

If a straight side cuts through the measured body, review the physical reference
and correction model; do not repair the result with a locally eroded mask.
Residual alignment above one pixel at the 95th percentile is flagged. Source
availability is tracked separately: the pipeline cannot recreate pixels outside
the original photograph. Such missing corner data remains transparent and is
logged, even if it prevents a complete rectangular derivative.

The `compact cassette AR` tag uses average opposite straight-edge lengths before
the homography. Its nominal ratio is 100.4/63.8 (1.5736677) with a 5% relative
tolerance. Perspective can invalidate that input ratio even for a real cassette;
the tag is a bounded heuristic alongside the existing reel and edge checks.

For all rectified cassettes, `--cassette-crop auto` samples each corner in the rectified
plane, mapping samples back to the unmasked source. It finds the outermost
broadly supported gradient arc and refines a tangent quarter ellipse. It does
not copy a universal corner radius or use an interior screw's high contrast as
the shell outline. Small outward uncertainty protects the edge. Each fit logs
its radii, source points, support and residual. Unresolved corners inherit a measured sibling radius (bounded to 4.5% of
body height), or a 2 mm nominal prior. The log identifies these as inferred
and produces `some_corner_arcs_inferred_from_geometry_review_crop`.
The prior is a conservative default, not a verified universal shell dimension. The rectangle-only mode
is available as `--cassette-crop rectangle`.

Short guide projections outside the main-body
frame are discarded. Enclosed whites, hub teeth, windows, and backing remain
photographed content. Final colors are sampled once in linear RGB using
continuous-phase Lanczos3 with bounded footprint supersampling. Padding is
transparent, and preview backgrounds are not baked into the PNG.

## Validation, performance, and remaining work

Tests include a split dark/light background with protruding guides, a known
projective warp with independent interior landmarks, non-cassette rectangles and
a disc negative, a synthetic radial warp, nonlinear inverse consistency, sampling
phase, and alpha/color encoding. The generated CLI smoke control checks automatic
routing, an initial quarter turn, OCR, provenance, and review status.

Five real supplied photos were processed with the same algorithm and no named
sample presets. They include clear, dark, gray, yellow, and pale shells, two
quarter-turn inputs, weak edges, and mixed background contrast. They are private
development examples, not a representative accuracy study. Transparent edges,
severe perspective, lens-center estimation, overlapped objects, deep shadows,
and plane assignment need a larger independently measured corpus.

The analysis pyramid, cached edge sampler, narrow native strips, and two OCR views
keep detection work bounded. Final resampling is now the larger cassette cost;
[performance notes](PERFORMANCE.md) distinguish new observations from historical
disc benchmarks. Keep Python with native libraries for this release. A measured
native rendering extension may be useful later; a whole-app Rust rewrite would
not resolve incorrect physical-edge identity or missing depth information.

### Low-resolution crop preservation

For small inputs, a fixed pixel guard can remove screw rims and clear plastic.
The strongest gradient can be an inner shell edge: zero inset does not solve
that mistake, and adding a retention band can instead leave a white frame.
The correction must first use the physical outer boundary.

#### Outer rim versus calibration edge

The default uses coherent straight gradient ridges. Near-equally supported
parallel ridges favor the outer rim, but a faint fringe diverging from the long
body side does not define its corner. The former uniform-background threshold
refinement is skipped: on the small transparent example it followed a fringe
that widened toward the lower right. That pass remains only in the explicitly
requested experimental nonlinear modes.

The assumptions are a single rigid cassette, four long main shell sides, and
short guide projections that must not set the body dimensions. Contrast may
reverse across a mixed backdrop. Fit lines, intersect them, map their frame to
the nominal body ratio, and only then crop and feather. If genuine edge curvature
remains, one homography cannot make every point on that curve straight; log the
residual and review the reference plane or obtain a calibrated lens profile.

The final alpha is analytic geometry: straight sides plus supported quarter
ellipses, never a pixel-wise color mask. Weak corner evidence in a small JPEG
uses explicitly logged radius priors for unresolved corners. Background noise, a shadow, or a molded bevel
can still mislead any single-photo detector; review the corner-fit diagnostics.
Experimental boundary conformance remains a 2D approximation, not calibrated
optical correction. It is separate from the new corner crop.
