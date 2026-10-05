# Disc Straighten usage

Applies to version 0.6.0. Disc geometry algorithms are unchanged from 0.3.0.
The disc-specific sections below retain their existing conventions.
Start with the [README](README.md) for installation and a shorter introduction.

Find an optical disc's physical outline and spindle aperture, automatically
rectify supported angled photos, identify a likely upright text direction, and
export a transparent PNG plus reproducible logs.

Version 0.3.0 normalizes both physical rings to concentric circles with an exact
nominal spindle/outer radius ratio: 15/120 for full-size discs or 15/80 for mini
discs. It detects the likely size from the physical aperture and logs ambiguous
choices. [STANDARDS.md](STANDARDS.md) distinguishes this output idealization from
manufacturing tolerances. The earlier filtering/encoding optimizations remain;
[PERFORMANCE.md](PERFORMANCE.md) records the historical 0.2.1 benchmarks and Rust decision.
The [archivist tool catalog](research/ARCHIVIST_TOOLS.md) compares 18 related
open-source projects, with licenses, limitations, and integration recommendations.

```sh
./disc-straighten /path/to/disc-images --output ./processed --preview
```

Pass one file, multiple files, a folder, or quoted HTTP(S) image URLs. Folder
scanning is nonrecursive. Existing results are protected unless `--overwrite`
is supplied. Processing is local; image content is not sent to a cloud service.

## Cassette photographs

```sh
./disc-straighten photos --media cassette -o processed --preview
./disc-straighten photo.jpg --media cassette --debow off -o perspective-only
./disc-straighten mixed-photos --media auto -o processed
```

The default media type is `disc`. Cassette processing fits the nominal
100.4 × 63.8 mm body, excludes short guide-rail excursions from calibration,
applies the final body/corner crop after correction, and chooses between two opposed text directions. It keeps
body edges horizontal rather than rotating them to follow slanted artwork.
`--orientation-policy majority` uses all capped confidence-weighted letter counts;
the default balanced score also weights height and limits dense small print.
Both policies keep the body level. All cassette results are provisional and return exit code 2 unless an input
fails. Automatic media routing is experimental; see [cassette geometry](CASSETTES.md).

`--debow off` is the default: four straight edge lines, their intersections,
and one homography to the nominal rectangle. No lens profile is assumed and no
nonlinear correction is applied. Experimental `auto` tests a radial estimate
and may apply a bounded 2D edge-conformance blend; `conform` skips the lens estimate
and explicitly requests the blend. These are cassette settings; disc lens
correction is not implemented. [Lens and depth notes](LENS_AND_DEPTH.md) explain
why bowed edges and depth parallax require different treatment.

For a reviewed candidate, `--cassette-corners x1,y1,x2,y2,x3,y3,x4,y4` supplies
four main-body virtual corners in perimeter order, in EXIF-normalized source
pixels. They seed local edge refinement; they do not force those exact coordinates
or bypass edge-support requirements. Exclude guides, shadows, and label borders.
Corner and angle overrides apply to one input at a time. Cassette `--angle 0`
or `--angle 180` bypasses OCR and selects an orientation **after** rectification;
it is not a source-image rotation.

Cassette `--feather 1` applies a one-output-pixel transition centered on the
final body rectangle and any measured corner arcs. Larger values widen this transition; smaller values are
unsupported. All original pixels are warped before this crop. There is no safety
inset, guessed corner radius, color key, or pixel-wise edge removal. The default
`--cassette-crop auto` uses measured quarter ellipses when the observed, pre-warp
body ratio is within 5% of 100.4/63.8. The geometry log tags this as
`compact cassette AR`; the tag is not produced merely because the output was
forced to that ratio. Each curve is fitted independently, with small outward
uncertainty to protect the plastic edge. Unsupported corners stay square and
are flagged. `--cassette-crop rectangle` retains all four virtual square corners.
Guide projections outside the main body are cropped. The nominal body and crop share the exact
continuous ratio, with pixel-grid rounding in the encoded alpha extent.
Disc-specific rim, hole, size, and perspective options do not configure cassettes.

Cassette output names match disc output names. Its schema 7 log includes `media`,
source hash, body dimensions, homography, corners, radial estimate, boundary-blend
coefficients, edge residuals, depth assumptions, orientation, crop rectangle,
insets, measured corner ellipses and support/residuals, observed aspect-ratio tag,
resampling, output origin/hash, and timing. Both media logs
include `source.camera` with allowlisted EXIF and explicit unknowns; see
[iPhone camera policy](IPHONE_CAMERAS.md). Detailed source edge samples and crop
diagnostics are in `*-orientation.json`. Pixel coordinates have x right/y down and
integer pixel centers after EXIF normalization. The canonical body origin is the
first fitted virtual corner; OCR may flip that frame by 180 degrees. Use the
logged full mapping, not the rotation summary alone, to reproduce the result.

## Requirements and first run

- macOS with Apple Vision and Swift compiler / Command Line Tools, or Windows
  CMD with Tesseract 5. See [Windows setup](WINDOWS.md).
- Python 3.12 or later.
- ImageMagick 7 (`magick`).

On a machine without these prerequisites, install Python and ImageMagick with
`brew install python imagemagick` and install Apple's Command Line Tools with
`xcode-select --install`. The launcher checks dependencies, creates its own
`.venv`, installs the three pinned Python dependencies, and compiles the included
Vision helper into `~/.cache/disc-straighten` on first OCR use. Later runs use that
environment. Initial dependency installation needs internet access; local-image
processing afterward does not. No system package installation is done silently.

`--ocr auto` chooses Vision on macOS and Tesseract elsewhere. `--ocr tesseract`
selects the portable backend explicitly. Language data is installed separately.
English and Russian are requested by default; Tesseract logs missing languages,
uses the available requested languages and flags the result. If none are
available it fails. `--angle` bypasses OCR. Example:

```sh
./disc-straighten scan.jpg -o processed --languages en-US,ru-RU
```

## How discs choose the top

Text amount is useful evidence, but does not by itself identify designer intent.
The default `balanced` policy:

1. Runs OCR on eight temporary views spanning 360 degrees at 45-degree intervals.
2. Maps text quadrilaterals back to the source or rectified disc plane and deduplicates repeated
   observations of the same physical text region.
3. Groups baseline directions within seven degrees. Text is counted as readable
   evidence only in views within 35 degrees of horizontal.
4. Weights alphanumeric characters by OCR confidence squared, with 32 characters
   per line, modest text-height weighting, lower votes for isolated numbers, and
   lower votes for small text close to the rim.
5. Groups nearby lines into blocks and caps each block's contribution. Tiny
   copyright paragraphs get a smaller cap, preventing an unlimited line-count
   advantage over prominent titles.
6. Estimates the winning family's fine angle using a weighted median. Reports
   alternative families, evidence strength, and a review flag for close scores,
   inconsistent baselines, or insufficient text.

Use `--orientation-policy majority` to compare the simpler confidence-weighted
character-count policy. It still deduplicates OCR and caps individual lines,
but omits prominence, block caps, and rim/number discounts. Neither policy is a
semantic model of artistic intent. A short title can still lose to a long rotated
subtitle; curved lettering, unreadable type, or symmetric designs can be ambiguous.
The score margin is not a calibrated probability or an accuracy percentage.

All rotations use the same search; there are no filename-specific angles, title
dictionaries, manually selected text regions, or sample geometry presets in the
runtime. Intentional diagonal artwork is preserved when the main text wins.

## Angled photographs

Perspective detection is automatic. The same command handles scans and photos:

```sh
./disc-straighten photo.jpg --output processed --preview
```

The detector fits the physical outer rim and spindle opening as separate ellipses,
including their different projected centers. It then solves a projective transform
that makes the two boundaries concentric circles. This supplies the geometric
constraint that an outer-ellipse stretch alone lacks. Text direction is measured
in this flattened plane; perspective correction and text rotation are composed
into one final warp of the original pixels.

For photo outputs up to 2000 pixels wide, up to two additional temporary views
check the winning text family at output scale and refine its angle by at most
two degrees. This reduces small residual skew caused by OCR's upscaled boxes.
These views are analysis only; the final master still comes from the original.

The physical boundaries must be sufficiently visible. Printed circles are used
only as search seeds; the detector searches beyond them for a coherent physical
rim of either contrast polarity, including weak edges and offset printing. A
spindle-radius ratio near 15/120 or 15/80 identifies candidate size profiles. The
default joint fit then fixes that ratio exactly while fitting both boundaries.
If more than one ring could be a compatible aperture, the output requires review.
Use `--disc-size 120` or `--disc-size 80` when the physical size is known.

The default `--geometry-policy nominal` always fits both rings, even for a nearly
round source. A circular outer outline alone does not exclude perspective. When
closed contours are insufficient, a light-background scan detector proposes
circles, then refits actual ellipses from the image before solving the same
constrained transform. If neither route establishes usable boundaries, the input
fails instead of silently claiming exact geometric recovery.

`--geometry-policy measured` retains the earlier behavior: independent scan
circles below practical distortion thresholds and a freely fitted radius ratio
for supported photos. `--perspective off` and reviewed `--outer` / `--hole`
source-circle overrides require this policy. `--perspective on` requires a
usable physical pair and cannot be combined with source-circle overrides.

The output boundary is an analytically round circle. Artwork accuracy still
depends on correctly identifying the physical boundaries, a flat disc, and the
camera's lens distortion. Unknown lens distortion is not calibrated away;
glare, occlusion, blur, and hidden detail cannot be recovered. Read
[PERSPECTIVE.md](PERSPECTIVE.md) for the method, assumptions, and research sources.

## Geometry and image quality

Automatic geometry targets one nominal 120 mm or 80 mm disc with a 15 mm aperture.
Size inference assumes the detected opening is the actual spindle hole; a
decorative hub ring or obscuring case hub can make that inference ambiguous.
It does not identify CD/DVD/BD format or independently measure millimeters.
The scan fallback expects
a nearly face-on scan on a plain light background. It generates circle hypotheses, requires
broad angular edge support, then selects an outer supported circle. This reduces
selection of strong interior printing boundaries but cannot prove that a weak
edge is the physical polycarbonate boundary. Large margins between print and rim,
severe shadows, cropped/occluded discs, and missing physical
boundaries may need reviewed geometry or a new capture. Photos can have a dark
background when the rim and aperture remain measurable.

Both ellipses are measured independently before testing the physical-disc model.
Measured conics and the constrained model conics are recorded separately: noisy
measured edges cannot generally be mapped exactly to an arbitrary fixed ratio.
The shared homography is refitted against those edges; no nonlinear radial warp
is added to force incompatible measurements. Edge measurement uses
analysis-only smoothing, 0.125-pixel radial/normal samples, quadratic gradient-peak
refinement, and robust geometric fitting. Residuals report model consistency;
subpixel coordinates do not establish subpixel physical accuracy.

Final color pixels undergo one EWA Lanczos3 projective/rotation warp in linear RGB
with alpha-aware sampling. OCR trials never become the final image. Source EXIF
orientation is normalized first; tagged input color is converted to sRGB using
the system profile. An analytic destination mask provides a one-pixel smoothstep
feather without repeated mask resampling. PNG bit depth is explicitly forced to
16 by default, including for 8-bit PNG sources. The output does not create detail
absent from the source. Fully transparent RGB is zeroed. Photo output radius is
the geometric mean of the measured outer semiaxes, retaining approximately the
captured footprint's area; local magnification necessarily varies across a photo.
Exported master PNGs explicitly declare sRGB and discard source EXIF, timestamps, and
stale camera dimensions. Encoded image pixels are unchanged by this metadata step;
provenance remains in the JSON logs.

Only the exterior and physical spindle aperture are removed. The clear hub and
matrix artwork remain; true material translucency cannot be recovered from one
scan over white. No sharpening, denoising, super-resolution, or generative
processing is performed. Input must be opaque and single-frame.

## Output and review

For `scan.jpg`, the tool writes:

- `scan-straightened.png`: RGBA master at the measured disc scale.
- `scan-straightened.json`: source hash, independent measured circles, actual
  knockout circles, feather/offsets, clockwise rotation, source-to-output matrix,
  output hash, versions, and review reasons. Schema 4 also records the selected
  size profile, geometry policy, measured and modeled source ellipses, projected
  physical center, source-to-plane homography, fit residuals, and whether custom
  knockout offsets preserve the nominal ratio.
- `scan-orientation.json`: detailed OCR region votes and geometry candidates.
- `scan-preview.png`: optional 900-pixel dark-background preview.

Coordinates use integer pixel centers: top-left `(0,0)`, x right, y down, after
EXIF normalization. For rectified photos, measured/applied circles use disc-plane
coordinates with physical center `(0,0)`; ellipse fields retain source coordinates.
Output circles and the full source-to-output homography are logged separately.
A positive rotation is clockwise in the selected plane. Knockout radii denote the
50% alpha contour. Defaults: outer inset 0 px, spindle expansion 0 px, full feather
width 1 output pixel. Thus the feathered 50% contours retain the exact nominal
ratio within floating-point precision. Explicit offsets can change that ratio;
the log reports the applied value. Raster edges inevitably have pixel quantization.

Exit codes: `0` all processed without review flags; `2` completed with provisional
results requiring review; `1` one or more inputs failed. A `review_required` image
uses the best current estimate. It is not an assertion that the result is correct.
Batch processing continues after an individual failure. Progress goes to stderr;
one JSON summary per completed image goes to stdout. A failed input has an error
summary on stderr and no newly published successful-result log.

To supply reviewed geometry or an angle, use one input per command:

```sh
./disc-straighten scan.jpg -o reviewed --geometry-policy measured --outer 967.7,974.2,951.05 --hole 963.8,976.2,118.67
./disc-straighten scan.jpg -o reviewed-angle --angle -6.7
./disc-straighten mini-cd.jpg -o processed --disc-size 80
```

Other controls: `--feather`, `--outer-inset`, `--hole-expansion`, `--depth 8`,
`--min-margin`, and `--preview`. Run `./disc-straighten --help` for details.

## Validation and distribution

After the launcher creates its environment:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover conflicting text directions, small copyright blocks, duplicate OCR
votes, circular angle wraparound, empty/numeric text, a shifted high-contrast print
inside a physical rim only six gray levels below white, independent centers, alpha coverage, native rotation
coordinates, and transparent RGB. Perspective tests use known camera transforms
and independent interior landmarks, noisy edge samples, a weak rim with offset
printing, incorrect hub rings, invalid horizons, and actual rendered fiducials.
Cached interpolation is checked against SciPy's original sampler with exact
array comparisons, including boundary and far-outside coordinates.
The packaged report records the three supplied scans, two rotated controls, and
the attached TDK photograph. Mini-disc validation uses synthetic known-camera
controls; no real 80 mm photograph has been supplied. Tests check interior
landmarks as well as both circle boundaries and the encoded alpha symmetry.
The original photo is not in the source bundle. The sample report records the
0.3.0 algorithm; the 0.3.1 synthetic integration check is separately reproducible
with `examples/synthetic_smoke.py`.

To explicitly download and rerun those five sample cases:

```sh
.venv/bin/python examples/run_samples.py ./sample-run
```

This checks the original source hashes and validates rotations, circle-radius
comparisons, real PNG bit depth, transparent RGB, and analytic alpha area. It
returns exit code 2 when completed samples retain expected review flags.

The runtime is a beta based on a small validation set. It is ready for command-line
trials and batches with review; it has not been established as an unattended
archive-quality classifier across arbitrary optical-disc scans.

Source is MIT licensed. See `THIRD_PARTY_NOTICES.md` and `licenses/` for dependency
terms. No numerical-library binaries, Apple framework binaries, or copyrighted
sample artwork are included in the source bundle. Private test derivatives are
included only when explicitly requested during packaging and must not be uploaded
as a public release. Sample source links and hashes are in `examples/sources.json`.
