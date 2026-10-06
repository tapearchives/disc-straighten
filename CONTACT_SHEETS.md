# Contact sheets and catalog accounting

Open **Create contact sheet**, choose a batch output folder (or a flat folder of
catalog-named images), edit the title/range, and click **Create contact sheet**.
Both platforms and the CLI use `contact_sheet.py` and `catalog.py`.

## Layout and output

The owner's reference uses US Letter (612 × 792 PDF points), 36-point side
margins, four 135 × 88-point picture frames per row and five rows spaced 123.5
points apart. The first frames start 96 points below the page top. Rounded dotted
black outlines surround each picture. Headings are 15 points, captions 12 points,
and the footer up to 11.75 points. Long headings shrink to stay on the page.

`{start}` and `{end}` in the subtitle insert the selected catalog range. The
current print date and page number follow the footer credit. **Fill frames
(reference)** centers and clips photos within their report frames. **Fit whole
image (discs)** contains the entire photo, leaving white space as needed. These
display choices never alter the input or master image.

Generation runs away from the UI thread. Mac uses PDFKit to preview the PDF;
Windows displays rendered PDF pages with Previous/Next buttons and scrollbars.
A fresh `contact-sheet` folder contains the PDF, page PNG previews and
`contact-sheet.json`. Existing folders receive a timestamp suffix. Errors retain
the prior report and show recovery guidance. **Show Report Folder** reveals it;
no external browser opens automatically.

## Barcode anchors and missing images

**Name barcode pairs** starts off. Enabling it automatically checks **Add catalog
gap placeholders**, which can then be unchecked. CLI naming enables placeholders
by default; `--no-gap-placeholders` restores the previous pairing behavior.

Inputs are sorted by case-insensitive filename, then full path. A single usable
decoded barcode names B; its immediately preceding successful, unpaired,
barcode-free image is named A. This assumes consecutive front/back captures.
A barcode-free image is not proof of a physical front: review unread backs or
unusual capture runs. Pairing never skips a failed input or reaches across batches.

With placeholders on, first-file or consecutive decoded backs retain their B
identity even without an eligible front, provided media is supported in the photo.
A coarse reel-pair/disc-rim check keeps barcode-only photos and empty cases from
being mistaken for B sides. An unverified photo is retained in `output-references`
with its barcode, original source hash and review reason; it anchors the catalog
number without consuming the preceding image. If no real sides are identified
for that number, it receives one whole-number placeholder. The original source
remains untouched. Two reference photos of the same empty case still produce
one catalog cell. `output-json/catalog-anchors.json` records these references.

This check is evidence, not proof of absence: obscured reels, unusual shapes or
an incomplete disc rim can also require review. Reviewed geometry overrides the
coarse check. For a manually verified composition, rerun with reviewed corners
or `--no-gap-placeholders`; a correctly named real side supersedes a whole-number
dummy. Never fill a missing identity by counting unassigned photographs.

After naming, numeric catalog gaps
receive a yellow PNG with blue **MISSING MEDIA IMAGE** block lettering. A whole
missing number occupies one report cell. A missing A or B occupies that side's
cell. For example:

| Cell | Meaning |
| --- | --- |
| 001A, 001B | Two identified photos |
| 002 MISSING - PLACEHOLDER | Neither side identified |
| 003A MISSING - PLACEHOLDER | Front not identified |
| 003B | Decoded back |

Dummy logs set `synthetic: true`, `source: null`, catalog ID, optional side, and
reason. `output-json/catalog-sequence.json` inventories all slots and unassigned
files. A missing image here does **not** prove physical media is missing; an
undecoded or unassigned photograph may explain the gap. Original photographs
remain unchanged. Their paths and hashes stay in derivative logs.

Automatic ranges use same-width decimal IDs, preserving leading zeros. Explicit
start/end values include leading/trailing gaps. Ranges are limited to 10,000 IDs;
over 1,000 inferred gaps requires both endpoints to be explicit. Sparse UPC
collections and mixed/alphanumeric barcode namespaces are not expanded blindly.

Use names such as `104001A.png`, `104001B.heic`, or
`104002 MISSING - PLACEHOLDER.png`; `-straightened` suffixes are also recognized.
Nonstandard names, including `MISLABELED` and alternates, remain unassigned and
are listed in the manifest. Duplicate real ID/side names stop report creation.
Real sides supersede a stale whole-number dummy, logged under
`superseded_placeholders`. Existing outputs never get overwritten by pairing.

Contact sheets also display virtual missing cells for older folders without
dummy files, so every number in the selected range is represented. They do not
write dummy images into the source folder: actual placeholder creation belongs
to the main barcode-naming workflow.

## Commands

```sh
# Straighten, name adjacent pairs, and create gap images.
./de-askew "Tape photos" --name-barcode-pairs --preview -o catalog

# Prepare existing compositions without geometry correction.
./de-askew "Prepared photos" --catalog-only --name-barcode-pairs -o catalog

# Complete catalog with explicit limits.
./de-askew --contact-sheet catalog --catalog-start 104001 --catalog-end 104311

# A two-page proof; the JSON marks it as an excerpt.
./de-askew --contact-sheet catalog --contact-pages 2 -o proof

# Show entire images within the frames (recommended for discs).
./de-askew --contact-sheet catalog --contact-fit contain
```

Use `de-askew.cmd` in Windows CMD with the same options. `--catalog-only` exports
full-size PNGs after EXIF orientation/color normalization; finishing and metadata
options still apply. Logs explicitly record that no geometry correction ran.
Ordinary dropped-image processing continues to straighten by default.

The report JSON records ordering, source paths/hashes for rendered photographs,
missing reasons, ignored names, excluded IDs, layout and page/cell positions.
`complete: false` marks a page-limited proof. Preserve it with the PDF. Private
artwork, reference PDFs and generated catalogs are excluded from public exports.
