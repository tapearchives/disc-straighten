# Changes

## 0.6.0 — October 5, 2026

- Automatically search disc corrections from −45° to +45° when local OCR cannot
  run. Use bounded horizontal-projection deskew, record visual evidence and OCR
  failure, keep weak/ambiguous cases unrotated, and require review. `--ocr none`
  deliberately selects the same fallback; explicit angles remain authoritative.

- Tag detected pre-warp body ratios within 5% of 100.4/63.8 as `compact cassette AR`.
  Independently fit outer corner quarter ellipses after the straight-line frame is
  established. Reject unsupported curves, preserve screws and slight outward
  uncertainty, and apply the final analytic mask after the single color warp.
- Add `--cassette-crop auto|rectangle`, measured corner diagnostics and cassette
  schema 7. Retain square corners when a curve is unresolved.
- Add Windows CMD launcher, local Tesseract backend, portable ICC lookup,
  friendly help examples, Windows guide and macOS/Windows CI. No cloud OCR.
- Add known-corner, aspect-ratio, slanted-text and portable OCR regression tests.

### Included straight-edge corrections

- Default cassette correction to four straight edge lines, their intersections,
  and a single homography to the nominal body ratio (`--debow off`). Fix the old
  off path that still used curved intersections. Skip uncalibrated lens fitting,
  nonlinear bow correction, and the uniform-background fringe refit by default.
- Select broadly supported straight rim ridges; log a fallback to a straight
  fit of measured body samples for blurred edges. Add projective-corner and
  divergent-fringe regressions.
- Warp unmasked original pixels once, then crop to the full nominal rectangle
  with a slight centered feather. Remove color-key alpha, exterior flood fill,
  silhouette masks, corner-arc cuts, safety insets and opaque retention bands.
- Keep source-canvas availability separate from object geometry; log missing
  corner data and residual edge misalignment instead of concealing them.
- Add an encoded-alpha regression proving that changing every source pixel color
  cannot change alpha for fixed geometry. All cassettes share this crop policy.

## 0.5.0 — September 30, 2026

- Replace irregular cassette segmentation with straight body crops after composed perspective/bow correction. Crop rail bumps and a logged small inward margin; estimate small corner arcs separately. Final alpha is analytic and feathered inward.
- Remove the dark cassette preview frame. Masters remain transparent 16-bit PNGs with two pixels of transparent canvas padding. Crop-supported premultiplied sampling prevents exterior colors from contaminating feathered edges.
- Preserve allowlisted camera/lens metadata in both media logs. Recognize iPhone 7 Plus and iPhone 15 Pro Max without inventing missing tags or applying unverified model coefficients. Document Apple correction, macro switching, calibration limits, and the checked Lensfun list.
- Cassette schema 6 replaces silhouette diagnostics with crop bounds, inset, corner arcs, and output origin. Add straight-alpha, hostile-background color, and embedded-EXIF tests; regenerate all five private examples.

## 0.4.0 — September 30, 2026

- Add reviewed cassette processing and experimental `--media auto` routing. Fit long body edges to nominal 100.4 × 63.8 mm, reject short projections during calibration, and verify reel-pair evidence.
- Trace mixed-polarity edges; estimate exterior alpha separately from body geometry. Preserve photographed openings, hub teeth, and visible projections.
- Add opposed-view OCR, a bounded multi-edge radial test, and explicitly logged approximate edge conformance. Distinguish lens bow from unresolved depth parallax; add `--debow off|auto|conform`.
- Compose cassette transforms in one linear-light, alpha-aware, continuous-phase Lanczos3 warp. Retain the disc EWA renderer and numerical geometry. Disc logs explicitly report that lens distortion is not estimated.
- Add synthetic geometry/radiometry controls, cassette CLI smoke coverage, private five-photo examples, and documentation of 3D-to-2D compromises. No new runtime dependency or Rust migration.

## 0.3.1 — September 30, 2026

- Prepare a TapeArchives public README, full usage guide, contributor guidance,
  macOS CI workflow, and an original synthetic integration smoke test.
- Add a source-grounded compact-cassette feasibility report, inactive dimensional
  reference profile, and an original schematic. Cassette processing and automatic
  media classification remain proposed work.
- Export public sources from an allowlist. Require an explicit option and path
  for private test derivatives; exclude downloaded research and test artwork
  from the default archive and GitHub export. Retain dependency notices.
- Keep disc geometry, orientation, rendering algorithms, and pinned dependencies
  unchanged from 0.3.0. The existing sample report remains labeled with that version.

## 0.3.0 — September 30, 2026

- Add automatic 120 mm / 80 mm size hypotheses with nominal 15 mm aperture.
  Flag multiple plausible aperture sizes; allow an explicit `--disc-size`.
- Default to `--geometry-policy nominal`: jointly refit both physical edges to
  a homography with exactly concentric circles and the nominal radius ratio.
  Correct small stretches without the old distortion threshold. Preserve raw
  measurements, model conics, residuals, and selected profile in schema 4 logs.
- Refit scan-circle proposals as physical ellipses when closed contours fail.
  Keep the single final alpha-aware linear-light warp and subpixel edge sampling.
- Require broad absolute scan-rim coverage rather than comparing coverage with
  stronger interior rings; preserve edge polarity during scan refinement.
- Set default outer inset and hole expansion to zero, preserving the nominal
  alpha-contour ratio. Explicit offsets log whether they change that ratio.
- Retain independent scan circles/free ratios under the explicit `measured`
  policy; source-circle overrides and `--perspective off` require this policy.
- Add standards/tolerance notes, synthetic mini-disc and interior-landmark tests,
  and encoded-alpha roundness verification. Mini testing remains synthetic.

## 0.2.1 — September 30, 2026

- Cache cubic interpolation coefficients within each geometry sampling operation.
  Retain float64 precision, boundary handling, subpixel spacing, and all search
  candidates. No persistent image cache is introduced.
- Encode temporary OCR views with PNG compression level 1. Decoded OCR pixels
  are unchanged; final image resampling and compression settings are unchanged.
- Add 18-project archivist catalog in Markdown, CSV, and JSON, with source and
  license links and repository activity snapshots.
- Add reproducible benchmark scripts, raw timing records, and a measured Rust
  migration decision. No Rust migration or additional dependency is introduced.
- Add exact sampler equivalence tests and compare all six sample outputs with
  the prior release. Existing review flags and small-corpus limitations remain.

## 0.2.0

- Added automatic projective rectification using the measured physical outer rim
  and spindle aperture; combined perspective and text rotation in one final warp.
- Added synthetic camera controls and validation on the supplied TDK photograph.
- Standardized output sRGB metadata and removed stale source metadata from PNGs.
