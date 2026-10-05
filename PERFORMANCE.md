# Performance and Rust decision

## Version 0.6.0 OCR-free disc fallback

When OCR cannot run, the automatic −45° to +45° fallback creates one temporary
head-on analysis view and scores at most 60,000 selected pixels at 1° intervals,
then 0.05° around the best angle. Projection histograms avoid rendering 91 full
rotated images. The final renderer still samples the original once. This bounded
NumPy/OpenCV path does not require a Rust port. Its visual straightness scores
cannot replace OCR's readable-text evidence; every fallback requires review.
Timing tables below remain historical and do not measure this new fallback.

## Historical optimization measurements

This report measures releases 0.2.0 and 0.2.1. Version 0.3.0 retains those
optimizations but adds nominal two-ring fitting and mini-disc candidates; its
images intentionally differ. The old timing and byte-equivalence claims below
must not be read as 0.3.0 benchmark results.

Measured September 30, 2026. **Retain Python orchestration with the existing
native libraries; do not port the whole application to Rust at this stage.**
The implemented 0.2.1 changes remove redundant work and speed up lossless
temporary-file encoding. They do not reduce sampling precision, the number of
OCR views, rim-search coverage, or final rendering quality.

## End-to-end measurements

Apple M4 Pro, 14 physical cores, 64 GiB RAM; Python 3.14.7, pinned dependencies.
Three sequential runs per image per version; local files and a warm compiled
Vision helper. Includes normalization, geometry, all OCR views, final 16-bit
PNG, JSON, and preview. Excludes interpreter/module startup, downloads, initial
dependency installation, and the one-time Swift compilation. Before and after
were measured in separate same-day blocks, not randomized crossover trials.
The sample is small, and results are not promises for other machines or images.

| Input | v0.2.0 median | v0.2.1 median | Speedup | Time saved |
| --- | ---: | ---: | ---: | ---: |
| Disney label, 602 × 600 | 11.46 s | 7.00 s | 1.64× | 39% |
| Computerra, 1936 × 1935 | 58.80 s | 15.45 s | 3.81× | 74% |
| Angled TDK photo, 1280 × 1280 | 18.83 s | 13.09 s | 1.44× | 30% |

Observed ranges, before → after: Disney 11.41–11.64 → 6.93–7.20 s;
Computerra 58.50–59.67 → 15.33–15.53 s; TDK 18.45–18.84 → 13.05–13.36 s.
The three-run batches total 267.6 seconds before and 106.9 seconds after
(about 2.5× aggregate throughput for this particular mix).

Every benchmarked final PNG is **byte-for-byte identical** to the baseline,
including all three repeats. The three additional regression cases—Mobile
Computers and the two rotated scan controls—also match their v0.2.0 final PNGs
exactly. All six retain the same measured geometry, orientation decisions,
knockout parameters, and review statuses. Log timestamps/version information
can differ; older scan logs used a single OCR-view counter instead of separate
coarse/fine counters. Twenty-five automated tests pass, including known-camera
interior landmarks and weak-rim/offset-print controls. This confirms regression
equivalence on the tested corpus, not physical accuracy for unseen discs.

## What was slow, and what changed

**Repeated full-image cubic prefiltering.** A profiled Computerra geometry run
made 751 `map_coordinates` calls. Each cubic call silently prefiltered the full
image even when only a few exterior points were requested. The prefilter took
37.93 seconds of a 43.58-second profiled geometry run. The actual resampling
kernel took only 0.41 seconds. These are profile timings, distinct from the
unprofiled medians above.

`CubicSampler` now calculates float64 spline coefficients once for each reusable
sampling plane. It preserves the pinned SciPy version's nearest-boundary
padding and passes the coefficients to the public sampler with
`prefilter=False`. It does **not** disable prefiltering on raw pixels, which would
change the interpolation. Exact numerical tests cover borders, far-outside
coordinates, repeated radial profiles, and image-lifetime independence.
The optimized profile has 13 prefilters for the same 751 sampling calls;
prefilter time falls to 0.66 seconds. No global cache retains user images.
Unprofiled Computerra geometry falls from 42.53 to 3.94 seconds.
[SciPy documents the prefilter behavior](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.map_coordinates.html);
the [pinned implementation](https://github.com/scipy/scipy/blob/v1.18.1/scipy/ndimage/_interpolation.py)
also specifies its boundary preparation.

**Over-compressing temporary OCR images.** A 27-view experiment on the TDK photo
compared three angles, three repeats, and PNG compression defaults/0/1. Median
view preparation was 1.189 / 0.501 / 0.553 seconds, respectively. Decoded RGB
hashes matched for each angle across all settings and repeats. Level 1 was
selected: about 2.44 MB median instead of 2.05 MB at the old default, while level
0 needed 7.69 MB. This keeps most of the measured speed gain with much less
temporary disk traffic. Only coarse OCR views use the new setting. Final PNG
encoding, EWA Lanczos3, linear-light processing, alpha handling, and analytic
feathering remain unchanged.

## Why a full Rust port is not worthwhile now

The application already delegates most expensive operations to compiled code:
OpenCV for contour proposals, SciPy/NumPy for numerical operations, ImageMagick
for pixel transforms/encoding, and Apple's Vision framework through Swift for
OCR. A Rust wrapper would still pay for these operations. Porting a repeated
native calculation without removing the repetition would preserve the bug.

After optimization, Computerra spends about 3.94 of 15.45 seconds in all geometry.
Even making that entire stage instantaneous would only give about 1.34× overall
speedup. That is a generous upper bound for a geometry-only rewrite, not a Rust
benchmark or an estimate of an achievable gain. A new native fitting component
could eventually help the remaining thousands of small robust fits, but its
benefit must be measured against the fitting libraries and interop overhead.

| Option | Assessment |
| --- | --- |
| Current Python + native engines | Recommended now. Measured improvement, unchanged images, smallest maintenance burden. |
| Rust CLI around the same engines | Possible packaging/control benefits, but no demonstrated speed benefit. ImageMagick/OpenCV and macOS Vision would still be dependencies. |
| Small Rust extension for a proven hot loop | Reconsider if a larger representative corpus shows a remaining hot loop worth accelerating. Require equivalent geometry/review outcomes and meaningful end-to-end gain. |
| Full Rust image pipeline | Not recommended now. Must re-establish ICC behavior, linear-light/alpha resampling, 16-bit PNG semantics, projective fitting, OCR, and provenance across platforms. |
| Native C++ or libvips backend | Also a candidate rather than an automatic improvement; benchmark the actual transforms and validate fidelity before switching. |

[opencv-rust](https://github.com/twistedfall/opencv-rust) binds native OpenCV;
changing bindings does not replace its algorithms. The inspected
[imageproc warp API](https://docs.rs/imageproc/latest/imageproc/geometric_transformations/enum.Interpolation.html)
offers nearest, bilinear, and bicubic interpolation; it is not an equivalent
drop-in replacement for our EWA Lanczos3 renderer. This is a specific API gap,
not a claim that Rust cannot implement equivalent rendering.
[libvips](https://www.libvips.org/API/current/how-it-works.html) has an attractive
demand-driven, parallel architecture, but its performance on our exact task was
not measured in this review. No comparative Rust/C++/libvips speed claim is made.

For archival portability, an independently tested Tesseract or other open OCR
backend is a higher-value next step than changing orchestration languages:
Apple Vision currently makes this a macOS-specific build. A Rust rewrite alone
would not remove that constraint. No port was performed.

## Further speed work, in priority order

These are proposals, not implemented features or promised gains.

1. **Bounded batch concurrency.** Benchmark two image workers first, with explicit
   native thread limits and a memory budget. Avoid multiplying Python workers by
   all-core native workers. Measure whole-batch throughput and peak memory on
   large scans; the current 40 MP input limit is not a concurrency budget.
2. **Reuse an OCR process.** Evaluate a persistent Swift helper or batched image
   requests. Current Vision subprocess totals are only about 1.6–2.4 seconds per
   image, including actual recognition, so launch savings have a strict ceiling.
   Keep all eight coarse views, deterministic ordering, and clear failures.
3. **Temporary fine-view encoding.** Apply the same lossless encoding experiment
   to the photo's two fine-alignment views. They currently cost about 2.3 seconds
   combined; some of that is necessary masking/warping, not compression.
4. **Profile final rendering on bigger scans.** Computerra's final image takes
   about 4.9 seconds. A persistent native renderer, faster analytic mask
   evaluation, or configurable lossless PNG compression may help. A changed
   compressed file may have identical pixels but a different checksum; log that
   explicitly and verify decoded pixels/color metadata.
5. **Reduce redundant fitting only with evidence.** The next geometry cost is
   robust fitting of many similar candidates. A validated candidate-merging
   strategy or analytic Jacobian may be more valuable than a port. Preserve
   ambiguous outer-rim alternatives and test weak transparent rims before use.

Skipping views, reducing full-resolution edge sampling, or replacing the final
warp with bilinear interpolation would trade accuracy for speed. They are not
part of this optimization.

## Reproduce and inspect

Run once after the launcher has installed dependencies and built the OCR helper:

```sh
.venv/bin/python benchmarks/measure.py /path/to/Label.jpg /path/to/computerra.jpg /path/to/tdk-photo.jpg --output ./timings --repeat 3
.venv/bin/python benchmarks/ocr_encoding.py /path/to/tdk-photo.jpg /path/to/tdk-photo-straightened.json ./ocr-encoding.json
.venv/bin/python -m unittest discover -s tests -v
```

For a before/after replication, extract the retained v0.2.0 source archive and
copy `benchmarks/measure.py` into its `benchmarks/` folder, then run each version
sequentially on the same local files with separate output folders. Do not run
them concurrently. Keep the same native dependencies and macOS version.

Raw evidence is in [benchmarks/results](benchmarks/results):
[summary](benchmarks/results/summary.json),
[baseline timings](benchmarks/results/baseline.json),
[optimized timings](benchmarks/results/optimized.json),
[encoding experiment](benchmarks/results/ocr-encoding.json),
[baseline profile](benchmarks/results/geometry-baseline-profile.txt),
[optimized profile](benchmarks/results/geometry-optimized-profile.txt), and
[six-image equivalence](benchmarks/results/output-equivalence.json).

## Cassette v0.4.0 observations

The historical v0.4.0 pass below covered five supplied development photos. The [current summary](cassette-validation-summary.json) now records v0.5.0 separately. These are observations, not repeated benchmarks or accuracy claims. All five produced review flags. Timings below exclude normalization, RGB reading outside the measured stages, preview/log writing, downloads, and startup. Geometry includes the cassette model; OCR uses two opposed views.

| Sample | Source pixels | Geometry | Silhouette | OCR | Render and PNG |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | 361 × 244 | 0.76 s | 0.08 s | 0.23 s | 0.44 s |
| 2 | 2880 × 3840 | 0.94 s | 0.78 s | 0.46 s | 12.96 s |
| 3 | 2880 × 3840 | 1.18 s | 0.80 s | 0.45 s | 14.08 s |
| 4 | 3840 × 2880 | 0.96 s | 0.89 s | 0.47 s | 12.45 s |
| 5 | 1280 × 823 | 1.07 s | 0.52 s | 0.41 s | 1.56 s |

The large images spend most of these measured stages in the cassette renderer. That new renderer evaluates 36 continuous-phase Lanczos taps per footprint sample, including nonlinear mapping and linear-light premultiplied alpha. It is separate from the existing native disc EWA path; the historical byte-equivalence and speedup claims above do not apply to it.

Implemented bounds: a 900-pixel geometry pyramid, narrow full-resolution edge strips with cached cubic coefficients, a 1200-pixel segmentation proposal, two OCR views, and tiled final color sampling. The original is sampled only once for the final derivative. Unneeded full-frame feather distance transforms are skipped at the default feather width.

Next measure mapping, Lanczos evaluation, gathering, and PNG encoding separately on a larger corpus. A compiled sampler (Rust, C++, or another native extension) could reduce temporary-array and gather overhead; cache repeated row weights where the mapping allows. Preserve floating-point phase, alpha, color, and independent-landmark checks when comparing implementations. Do not substitute a quantized remap merely because it is faster. Parallelize batches only with an explicit memory limit after measuring peak use. No claimed gain for these future changes is established yet.

A full Rust port is still not justified. A small measured native render component is now a more plausible optimization target than rewriting detection, OCR integration, or the CLI. No Rust code or additional dependency was added in this release.

## Cassette v0.5.0 observations

The straight body crop removes the GrabCut/freeform-contour stage. Crop analysis
uses measured edge residuals and small corner-gradient probes. The renderer adds
an inverse crop-support mask for clean color interpolation and an analytic final
alpha. It retains continuous-phase Lanczos, linear-light sampling, and one final
color warp. Output padding shrank to two transparent pixels.

| Sample | Geometry | Crop analysis | OCR | Render and PNG |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.74 s | 0.006 s | 0.23 s | 0.35 s |
| 2 | 0.91 s | 0.207 s | 0.46 s | 12.98 s |
| 3 | 1.17 s | 0.209 s | 0.48 s | 14.21 s |
| 4 | 0.95 s | 0.193 s | 0.51 s | 12.67 s |
| 5 | 1.10 s | 0.021 s | 0.44 s | 1.55 s |

This is one local sequential pass, not a controlled speedup benchmark. It uses
the same stage exclusions described above. Full-size color resampling remains
the main cost; the corrected masking adds no new library or OCR pass. The native
sampler recommendation still holds. A whole-program Rust rewrite remains
unjustified by these measurements.

## 0.8.0 sample timings and next optimizations

The five requested cassette examples on the development Apple Silicon Mac took
about 3.6–10.6 s for geometry, 0.06–0.22 s for corner analysis, 0.34–0.52 s for
orientation, and 1.5–24.9 s for final rendering. These are development-run timings,
not a controlled benchmark; image size and active machine work differ. The large
transparent Denon source spends most time in the quality-preserving raster warp.

Keep the Python orchestration with native NumPy/SciPy/OpenCV/ImageMagick for now.
A wholesale Rust port would not accelerate external OCR or image codecs by itself.
Useful next steps are profiling the large-image sampler, bounded tile parallelism
without nested-thread oversubscription, fewer duplicate geometry proposals, and
optional smaller derivatives when archival full resolution is unnecessary.
Do not replace one composed high-quality warp with repeated cheap resizes.

Already applied: anti-aliased bounded geometry analysis, resolution-scaled faint
edge thresholds, cached interpolation coefficients, small preview cards, and
serial batches to bound raster memory. GUI history grows with the number of
small previews; very long unattended runs should use the CLI without --preview.
