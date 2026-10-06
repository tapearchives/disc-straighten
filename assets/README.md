# de-askew icons

The sharp disc is the rectified public-domain Wikimedia photograph
[DVD-Video_bottom-side.jpg](https://commons.wikimedia.org/wiki/File:DVD-Video_bottom-side.jpg).
See the full author/source credit in `../discstraight/manual/ATTRIBUTION.md`.

`disc-source.png` is the resized circular derivative. `de-askew.svg` embeds those
pixels verbatim. The centered disc is 684 px across on a 1024 px canvas. A 22%
opacity duplicate, rotated −26° and scaled (1.12, 0.60), expresses the skewed
input. Two alignment marks express correction. A quiet teal backplate supplies
contrast and margins. No generative repainting or invented disc artwork is used.

Rebuild with `python examples/build_app_icons.py` on macOS with librsvg,
ImageMagick and Apple's `iconutil`. ICNS contains 16/32/128/256/512 1×/2× sizes;
ICO contains 16/32/48/64/128/256 px. At 16 and 32 px the ghost overlay is omitted
to avoid a blurred hub. The source photograph and centered circle remain.
Both OS assets use the same identity. The build uses compatibility ICNS rather
than claiming support for Icon Composer's separate layered appearance variants.

Design references reviewed 2026-10-06:

- [Apple app-icon guidance](https://developer.apple.com/design/human-interface-guidelines/app-icons/): recognizable, simple shape and legibility across appearances.
- [Microsoft app-icon guidance](https://learn.microsoft.com/en-us/windows/apps/design/iconography/app-icon-design): clear metaphor, balanced silhouette, restrained layering, small-size readability and light/dark contrast.
- [Original Commons photograph](https://commons.wikimedia.org/wiki/File:DVD-Video_bottom-side.jpg): Ocrho's public-domain dedication was rechecked.

The two visual ideas are the optical disc and alignment. No app-name text, extra
badges or decorative symbols compete with them. Inspect the multi-size proof on
light/dark fields when changing this asset; source vectors alone do not establish
small-size quality. The UI alignment illustration is separate and generated from
the shared palette by `examples/build_ui_graphic.py` (also requires librsvg).
