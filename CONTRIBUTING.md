# Contributing

Disc Straighten targets macOS and Windows CMD. Install Python 3.12+,
ImageMagick 7, and Apple Command Line Tools (macOS) or Tesseract 5 (Windows), then run:

```sh
./disc-straighten --help
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/synthetic_smoke.py
.venv/bin/python examples/cassette_smoke.py
```

The launcher maintains its own environment and pinned numerical dependencies.
Do not change pins merely to silence a numerical regression. The Swift source is
compiled locally; compiled Apple/framework binaries are not part of the project.

## Changes to geometry or image handling

Keep independent measured edges separate from fitted physical models. Check
interior landmarks as well as output silhouettes: a perfect circle or rectangle
can conceal a wrong transform. Log uncertainty, ambiguous alternatives, and
failure reasons. Preserve single-pass final resampling, linear-light color,
alpha behavior, hashes, and source-image immutability.

Use synthetic fixtures with known geometry and independent validation points.
Include a real regression image only when its redistribution rights and provenance
are explicit. Review the entire transformed object at native resolution. For
performance changes, compare decoded pixels, geometry, orientation, and review
decisions before claiming equivalence; profile representative end-to-end runs.

## Reporting a problem

Include the tool version, operating system/Python/ImageMagick/OCR versions, command, exit code,
and relevant review reasons. Reproduce with the generated synthetic sample when
possible. Logs can contain source paths, URLs, and recognized text: inspect them
before sharing. Share original photographs only with permission from the owner.

Cassette work should follow [CASSETTES.md](CASSETTES.md). The research profile is
not a runtime detector. Do not claim cassette support from synthetic rectangles
alone, or use guide projections as the 100.4 mm body boundary.

## Source distribution

Keep images, downloaded research PDFs, environments, and private test runs out of
Git. `package.py` exports a reviewed allowlist; new public files must be added to
that list deliberately. See [RELEASING.md](RELEASING.md). Contributions must be
compatible with the project's MIT license and retain third-party notices.

For cassette changes, retain the guide-projection and mixed-background controls and independent interior-landmark test. Review lens-model assumptions separately from 2D edge conformance. Real-photo fit residuals are not independent physical accuracy; do not turn private development samples into a public accuracy claim.
