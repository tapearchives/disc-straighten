# Dependency and distribution notes

Checked September 30, 2026 against the installed distributions and upstream
license texts; ZXing references added October 6, 2026. This is a source distribution of de-askew 0.9.0, licensed
under MIT. The custom geometry and orientation code was written for this tool;
no code from the previously researched deskew, subpixel-edges, circle-fit,
PaddleOCR, or libvips repositories is included.

| Component | Role | License / distribution treatment |
| --- | --- | --- |
| NumPy 2.5.3 | Arrays and numerical operations | BSD-3-Clause primary license; installed wheel notices copied into `licenses/numpy/`. Downloaded by pip, not bundled as binaries. |
| SciPy 1.18.1 | Edge interpolation, robust fitting, peak search | BSD-3-Clause primary license; complete installed wheel license/notice file in `licenses/scipy/`. Downloaded by pip, not bundled as binaries. |
| opencv-python-headless 5.0.0.93 | Contour/ellipse proposals for photos | Python packaging MIT; OpenCV Apache-2.0; full wheel notices in `licenses/opencv-python-headless/`. Downloaded by pip, not bundled as binaries. Other wheel components retain their own terms. |
| zxing-cpp 3.1.1 | Native barcode decoding with rotation and inversion search | Apache-2.0; upstream license in `licenses/zxing-cpp-Apache-2.0.txt`. Installed separately by pip; no decoder binary is bundled. |
| ImageMagick 7 | Color management and raster resampling | ImageMagick License; notice in `licenses/ImageMagick-LICENSE.txt`. Uses an independently installed executable. |
| Apple Vision | Optional macOS OCR | Apple system framework, not open source and not redistributed. Only the original Swift calling code is bundled; compiled locally with Apple's installed SDK. |
| Tesseract 5 and standard tessdata | Windows/local portable OCR | Apache-2.0 upstream engine and standard model repository. Installed separately, not redistributed in this source kit. Third-party installer dependencies retain their own terms. |
| Python / Swift / system ICC profile | Runtime, compiler, color transform target | Provided separately by the user's installation; not redistributed in the archive. |

The MIT application can be distributed with these permissive direct open-source
dependencies while retaining their required notices. ImageMagick explicitly
permits differently licensed applications and commercial use. Installed numerical
wheels can include additional components and runtime licenses (including GCC
runtime exceptions); the complete notices are retained rather than describing
every transitive component as BSD. A future standalone binary must preserve and
recheck the actual licenses of every binary and ImageMagick delegate shipped.

Source license references:

- NumPy: https://github.com/numpy/numpy/blob/main/LICENSE.txt
- SciPy: https://github.com/scipy/scipy/blob/main/LICENSE.txt
- ImageMagick: https://imagemagick.org/license/
- OpenCV: https://github.com/opencv/opencv/blob/5.x/LICENSE
- OpenCV Python packaging: https://github.com/opencv/opencv-python/blob/5.x/LICENSE.txt
- ZXing-C++: https://github.com/zxing-cpp/zxing-cpp/blob/v3.1.1/LICENSE
- Apple developer agreements: https://developer.apple.com/support/terms/
- Tesseract: https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE
- Standard tessdata: https://github.com/tesseract-ocr/tessdata/blob/main/LICENSE

The three supplied disc scans, attached TDK photograph, and processed derivatives remain separate
test material. The source archive includes their URLs and verification metadata,
not copies licensed under MIT. The research report is background documentation;
linked repositories are not bundled dependencies. No input-image rights are
granted by this software license.

The additional archivist catalog is documentation, not a combined distribution of
those applications. Version 0.2.1 adds no runtime dependency. The cached sampler
calls SciPy's public `spline_filter` and `map_coordinates` APIs and preserves the
pinned version's nearest-boundary padding convention; SciPy's existing notices
are retained. No private SciPy API or copied native implementation is included.

The cassette dossier links to IEC, Ecma, Reddit, and patent publications. Copies
of those publications and Reddit attachments are not distributed. The reference
JSON and schematic are original explanatory materials based on attributed
dimensional facts; they are not copies of standards drawings. No cassette
algorithm or dependency was added in version 0.3.1.

Version 0.4.0 adds original cassette geometry and raster code, with no new runtime dependencies. The five supplied cassette photographs, derivatives, OCR logs, and private review gallery are excluded from public source exports. Their rights are separate from the software license.

## 0.8.0 additions

The optional Windows GUI downloads TkinterDnD2 0.6.3 (MIT wrapper with bundled
TkDnD binaries under their upstream permissive terms); its wheel license is
retained in `licenses/tkinterdnd2`. Python and Tcl/Tk are installed separately.
See https://github.com/Eliav2/tkinterdnd2 and https://github.com/petasis/tkdnd.
ExifTool is an optional external executable for requested metadata copying;
it is not distributed by this kit. See https://exiftool.org/ for its Perl
Artistic/GPL terms. HEIC support uses the user's ImageMagick/libheif installation,
not a bundled codec. Delegates retain their own licensing.

The illustrated manual now includes the owner-requested sample images.
`discstraight/manual/ATTRIBUTION.md` records authors, source pages, changes and
per-image licenses, including CC BY-SA for applicable derivatives. These images
are not MIT-licensed by this program. The icon derives from the public-domain
DVD-Video_bottom-side photograph identified in that attribution file.
