# Reddit cassette image references

Inspected September 30, 2026 through the existing Chrome browser. All seven
reference images in the [requested Reddit post](https://www.reddit.com/r/askmath/comments/iylvxe/mathematical_system_for_djing_compact_cassette/)
loaded and were visually inspected. This supersedes the earlier note that the
attachments could not be inspected. The post discusses cassette DJ track markers;
it is not a dimensional standard.

## Image catalog

The links below point to the exact displayed Reddit preview assets. Some are
resized or transcoded previews, not verified original scans. Browser downloads
were preserved locally with hashes; visual inspection included an enlarged view
of the low-resolution inch drawing. Enlarging it adds no source detail.

| Reference | Retrieved size | Meaning and use |
| --- | --- | --- |
| [Label sheet](https://preview.redd.it/mathematical-system-for-djing-compact-cassette-tapes-need-v0-lxayf72wezo51.jpg?width=490&format=pjpg&auto=webp&s=d67e8b90b0bf329f26d80fc309f966a0d6cb0261) | 490 × 640 | 8.5 × 11 inch page; 3.5 inch label width; 2.375 inch opening. These are label-production dimensions, not the body width or reel-center spacing. |
| [CAD shell sketch](https://preview.redd.it/mathematical-system-for-djing-compact-cassette-tapes-need-v0-fgmebpmyezo51.png?width=1024&format=png&auto=webp&s=dc876457394af7e7ad20b15f507e384cff82da95) | 1024 × 713 | Shows 100 and 63.311 for the body, plus modeled screw, label, window and hole details. No standard, revision, tolerance scheme, or original author is identified in the post. Treat as one sketch, not a universal calibration template. |
| [Inch-based mechanical drawing](https://preview.redd.it/mathematical-system-for-djing-compact-cassette-tapes-need-v0-ci1woiqbfzo51.png?width=763&format=png&auto=webp&s=7a0a04b75daa2277eaa636b568ba6b17e2b20915) | 763 × 392 | Shows separate body and protruding side features, reel geometry, reference holes, a prime reference line, and a stepped side section. Useful corroboration; the cropped repost has no identifiable publication or revision. |
| [Maximum window area](https://preview.redd.it/mathematical-system-for-djing-compact-cassette-tapes-need-v0-m1ska2sffzo51.png?width=462&format=png&auto=webp&s=cbd6e4c38dba38519c216e3bf5269c0e0cb04fe1) | 462 × 330 | The crosshatched area is explicitly a maximum window area. Visible callouts include R 0.315 in (8.0 mm), twice, and 0.524 in (13.3 mm). This is not a requirement that every physical viewing window have the same contour. |
| [Clear Maxell shell photograph](https://preview.redd.it/mathematical-system-for-djing-compact-cassette-tapes-need-v0-3f5u3s6kfzo51.jpg?width=1080&crop=smart&auto=webp&s=49c741275fcce4b03b1f7505d67934555102731a) | 1080 × 1080 retrieved preview | Illustrates clear shell material, reel/tape-pack visibility, screws, and a raised front. The post describes it as without a window; the clear shell still reveals internal parts. Product photo, not metrology. |
| [TDK shell with window photograph](https://preview.redd.it/mathematical-system-for-djing-compact-cassette-tapes-need-v0-ofd2277mfzo51.jpg?width=1024&format=pjpg&auto=webp&s=fbd8b783c0b5f0f63f948045b8e0cea6a2ddc7dc) | 1024 × 692 | Illustrates an opaque shell with a central viewing window, hub openings, teeth, and a raised front. The photographed shape and lighting are not a standard dimensional reference. |
| [Cassette parts cutaway](https://preview.redd.it/mathematical-system-for-djing-compact-cassette-tapes-need-v0-r84o2ixnfzo51.jpg?width=220&format=pjpg&auto=webp&s=f72217d517dd50f6f5b3f655dc79f9ed42a54488) | 220 × 151 | Labels parts such as reels, guide roller/pin, pressure pad, magnetic shield, and erase-protection tab. The author attributes it to Wikipedia; that original file/license was not independently traced here. Too small for dimensional measurement. |

## What changes in the dimensional interpretation

The label-sheet opening is 2.375 inches, or 60.325 mm. It must not be substituted
for reel-center spacing or treated as a fixed window size across shell designs.
The maximum-window-area drawing reinforces that a permissible opening region is
different from a universal physical edge.

The inch mechanical drawing visibly separates the main shell sides from short
protrusions. Reading its printed limit pairs gives the following approximate
conversions. Small lettering in this repost is not a substitute for the complete
primary drawing; these are corroborating readings, not new runtime constraints.

| Feature | Printed limits read from the image, inches | Converted interval, mm | Midpoint, mm |
| --- | --- | --- | --- |
| Body width | 3.941–3.965 | 100.1014–100.7110 | 100.4062 |
| Body height | 2.500–2.524 | 63.5000–64.1096 | 63.8048 |
| Reel-center separation | 1.661–1.685 | 42.1894–42.7990 | 42.4942 |

These midpoints agree closely with the existing nominal **100.4 × 63.8 mm** body
and **42.5 mm** reel spacing established from the separately inspected patent and
historical standards sources in [CASSETTES.md](../CASSETTES.md). The paired limit
values themselves also demonstrate that physical specimens have tolerances.

The CAD sketch instead labels the body **100 × 63.311**, with millimeters inferred
from its scale and the post's caption. That differs from the established nominal
frame. Its 84 mm label-region width also differs from the label-sheet template's
88.9 mm width. This is useful evidence that label and shell sketches must be
classified by feature and provenance, rather than combined into one supposedly
exacting template. Do not change the production body ratio to match this CAD view.

## How the images inform the algorithm and documentation

- Calibrate on supported main-body edges; keep guide projections separate from
  the body frame and preserve their observed silhouette.
- Treat window contours, screw layouts, label shapes and reel teeth as variable.
  They are identification clues, not interchangeable fixed-size constraints.
- Keep raised-front and recessed-reel depth limitations explicit. The side
  section is visual corroboration that a cassette is not a single flat plane.
- Preserve the distinction between a clear shell and an open aperture. A bright
  background visible through plastic is not automatically a region to erase.

No algorithm or nominal dimension changed following this reread. The new evidence
supports the existing distinctions and supplies actual image references where the
previous documentation had only an access limitation.

## Provenance and distribution

The local reference record is `research/reddit-image-evidence/inspection.json`.
It records the seven downloaded files, dimensions and SHA-256 hashes; the adjacent
browser manifest retains the exact URLs. A private `README.md` displays those
copies for local review. That directory is ignored and excluded by the public
source allowlist. The public package includes this link catalog and factual
analysis, not the reposted artwork. Original authorship and redistribution rights
for these illustrations have not been established by the Reddit post.
