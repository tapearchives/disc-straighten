# de-askew icons

The sharp disc is the rectified public-domain Wikimedia photograph
[DVD-Video_bottom-side.jpg](https://commons.wikimedia.org/wiki/File:DVD-Video_bottom-side.jpg).
See the full author/source credit in `../discstraight/manual/ATTRIBUTION.md`.

`disc-source.png` is the resized circular derivative. `de-askew.svg` embeds it
and composes the centered 770-pixel disc with a 25%-opacity duplicate translated
to (512,430), rotated -26 degrees, skewed 12 degrees and scaled (1.14,0.59).
No generative repainting or invented disc artwork is used.

Render with librsvg `rsvg-convert de-askew.svg -o de-askew.png`. ImageMagick's
`icon:auto-resize=256,128,64,48,32,16` generates the Windows ICO. Apple's
`iconutil` builds the ICNS from PNGs at standard 16/32/128/256/512 1x/2x sizes.
The native Mac app and Windows shortcut share this icon and the name de-askew.
