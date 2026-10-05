# Nominal disc geometry and standards

Checked September 30, 2026. The CLI's default is an explicitly idealized output:
two concentric circles representing a nominal outer diameter and a 15 mm spindle
opening. Standards permit manufacturing variation, so this normalization is not
a claim that the captured object had mathematically exact dimensions.

| Output profile | Outer diameter | Aperture diameter | Inner/outer radius ratio |
| --- | ---: | ---: | ---: |
| Full size | 120 mm | 15 mm | 0.125 (1:8) |
| Mini | 80 mm | 15 mm | 0.1875 (3:16) |

Radius and diameter ratios are identical. Both profiles use the same 15 mm hole;
the mini profile therefore needs a proportionally larger opening. They do not
imply a specific optical recording format. The output pixel scale remains based
on the captured outer ellipse, not on an invented DPI or ruler measurement.

## Verified dimensional sources

**CD, IEC 60908:1999 as adopted in SIST EN 60908:2000.** The publicly accessible
[SIST preview](https://preview.sist.si/sist-preview/12193/8ef7e3b5f56e4b41b06bcfef4471bae0/SIST-EN-60908-2000.pdf),
PDF page 15 / printed page 17, clauses 5.1.1–5.2.3, gives outer diameters
120 ± 0.3 mm and 80 ± 0.2 mm, and a center hole of 15 mm with +0.1/−0 mm tolerance.
It also allows 0.4 mm maximum outer-edge radial runout relative to the hole and
edge chamfers/radii. The dimensional table was inspected as a rendered page;
flattened PDF text alone can lose the asymmetric tolerance notation. This is a
preview containing the relevant table, not a claim to have reviewed the complete
licensed Red Book.

**120 mm DVD, ECMA-267 second edition, December 1999.**
[Official PDF](https://ecma-international.org/wp-content/uploads/ECMA-267_2nd_edition_december_1999.pdf),
PDF page 21 / printed page 11, clause 10.1: outer diameter 120 ± 0.30 mm;
substrate opening 15 mm with +0.15/−0 mm tolerance; assembled-disc opening
15 mm minimum. This is the openly available ECMA specification for the same
120 mm read-only DVD family addressed by ISO/IEC 16448. It is not presented as
an identical copy of every later ISO edition.

**80 mm DVD, ECMA-268 second edition, December 1999.**
[Official PDF](https://ecma-international.org/wp-content/uploads/ECMA-268_2nd_edition_december_1999.pdf),
PDF page 20 / printed page 10, clause 10.1: outer diameter 80 ± 0.30 mm;
substrate opening 15 mm with +0.15/−0 mm tolerance; assembled opening 15 mm
minimum. Its outer-diameter tolerance differs from the 80 mm CD tolerance.
Both DVD dimensional pages were visually checked.

The user's [Compact disc overview](https://en.wikipedia.org/wiki/Compact_disc)
is consistent with the nominal sizes; the tables above are the dimensional basis.
The [Blu-ray Disc Association format index](https://blu-raydisc.info/format-spec.php)
distinguishes RE, R, and ROM specification books. A filename such as
`Blu-Ray-1-PhysicalFormatSpecs` without an edition and URL does not identify one
authoritative physical specification. No unverified BD/HD DVD tolerance table is
used to tune this release. The two size profiles can be applied to other media
that share these nominal physical dimensions without classifying their format.
The separately cited DVD/Blu-ray cataloging guide concerns bibliographic
description, not metrology. A catalog description of 4¾ inches is rounded and
must not replace the 120 mm model (4.75 inches is 120.65 mm).

## What is constrained, and what remains uncertain

- The physical polycarbonate rim and actual opening supply geometric evidence.
  Silkscreen and metallization rings may be offset and are not calibration rings.
- A large, complete rim offers more spatial extent for a stable fit. The hole
  often offers stronger contrast but fewer pixels and possible chamfer/hub
  interference. Both contribute; neither is assumed infallible.
- One outer ellipse does not uniquely determine the original plane. Jointly
  fitting two concentric physical rings constrains the interior geometry. The
  software solves a homography and composes it with the OCR rotation for one
  final resampling of the original pixels.
- Exact nominal output circles require a constrained shared fit. Measured noisy
  ellipses, especially with manufacturing runout, need not be exact projections
  of that ideal annulus. Their original measurements, fitted model, and residuals
  remain separate in the log. Inconsistent fits are rejected or flagged.
- Mini classification depends on recognizing the real 15 mm aperture. If both
  size profiles have plausible ring evidence, the result requires review even
  if one score is higher. `--disc-size 80` or `120` supplies known size explicitly.
  Candidate search tolerances are image-analysis allowances, not manufacturing
  tolerances or calibrated probabilities.
- Zero knockout offsets preserve the nominal ratio. Feathering is symmetric
  about the radius, so the continuous 50% alpha contour is the intended circle.
  Integer pixel samples cannot form an infinitely precise continuous curve.
- Unknown lens distortion, occluded edges, and thickness/parallax are not solved
  by a planar homography. Round output boundaries alone do not establish exact
  physical accuracy of every artwork point. Preserve original captures.

Standards PDFs are reference material and are not redistributed in the software
bundle. The included algorithm is independently implemented; the reference links
do not add third-party source code or library dependencies.
