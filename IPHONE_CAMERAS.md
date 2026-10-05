# iPhone capture metadata and lens correction

Research checked September 30, 2026; implementation version 0.5.0.

The CLI reads camera metadata before normalization and includes `source.camera`
in both disc and cassette logs. It recognizes **iPhone 7 Plus** and **iPhone 15
Pro Max**. It preserves Make, Model, LensMake, LensModel, FocalLength,
FocalLengthIn35mmFilm, DigitalZoomRatio, FNumber, and Software when present.
Values remain EXIF strings, including rational numbers. GPS, dates, serials,
and opaque MakerNotes are excluded from this record. Final PNGs contain no source
EXIF; the untouched original remains the preservation master.

**All five supplied cassette attachments and the TDK disc attachment lack camera,
lens, and focal-length tags.** They retain an orientation tag, which is not camera
identification. These files log `metadata_status: "absent"`. The photographer's
usual phone is not substituted for missing evidence.

## Camera differences that matter

| Device | Camera system | Consequence |
| --- | --- | --- |
| iPhone 7 Plus | Rear 12 MP wide at f/1.8 and telephoto at f/2.8; front 7 MP. No rear Ultra Wide. | Calibration must match the actual camera and processing pipeline; do not reuse an Ultra Wide profile. [Apple specifications](https://support.apple.com/en-us/111953). |
| iPhone 15 Pro Max | Main at 24 mm equivalent, Ultra Wide at 13 mm equivalent, and 5x telephoto at 120 mm equivalent. The 2x / 48 mm equivalent view uses the Main sensor. Apple lists Ultra Wide and front-camera lens correction. | Zoom and equivalent focal length do not uniquely identify a physical lens or distortion model. [Apple specifications](https://support.apple.com/en-ie/111828). |

On supported iPhones, **Lens Correction** adjusts Ultra Wide and front-camera
photos and is on by default. This does not prove that a particular capture used
it, or describe every processing step of the Main camera. Camera identity tags
do not reliably tell us which geometric correction is already baked into an
export. [Apple advanced settings](https://support.apple.com/en-ca/guide/iphone/-iphb362b394e/ios).

Close cassette photos can trigger automatic **macro switching to Ultra Wide**.
The intended lens and actual lens may differ. The CLI retains the exact LensModel
string and assigns a role only when the label explicitly identifies front, wide,
ultra wide, or telephoto. A generic "back triple camera" label stays ambiguous.
[Apple macro controls](https://support.apple.com/en-mide/guide/iphone/iphfaacf2eb0/ios).

## No universal fisheye coefficient

Focal length does not supply radial coefficients, optical center, crop geometry,
or processing history. Apple's `AVCameraCalibrationData` can supply a radial
lookup table and distortion center associated with a capture. The table describes
radius-dependent magnification, not one fixed stretch percentage. It must match
the capture coordinate system and processing stage. Ordinary Make/Model tags
do not contain this calibration.
[Apple lookup-table documentation](https://developer.apple.com/documentation/avfoundation/avcameracalibrationdata/lensdistortionlookuptable?changes=_8%2C_8).

The Lensfun supported list inspected on this date has Apple **iPhone XS and XS
telephoto**, not the two requested models. That is evidence about this database,
not proof that no calibration exists elsewhere. Neither XS profile is used as a
substitute; no proprietary coefficient collection is bundled.
[Lensfun list](https://lensfun.github.io/lenslist/2999/12/31/Lenslist-master/).

RAW development is a separate concern: Apple's Image I/O documentation describes
DNG opcode lists and rectilinear/fisheye warps at specific development stages.
A rendered JPEG must not blindly receive a RAW-stage correction. This release
accepts JPEG, PNG, TIFF, WebP, and BMP; it does **not** develop DNG/ProRAW or directly
ingest HEIC depth/calibration payloads. Preserve the original capture and retain
metadata when exporting an opaque supported raster.
[Apple DNG properties](https://developer.apple.com/documentation/imageio/dng-image-properties).

## Implemented policy

1. Log camera identity or missing metadata. Never select numerical coefficients
   from the phone model or zoom alone.
2. For cassettes, test remaining curvature against the bounded radial model.
   Several edges must agree; accepted estimates are still marked uncalibrated.
3. Fit perspective, then optionally conform small remaining bow with the bounded
   2D blend. This is not labeled an iPhone camera profile or recovered 3D geometry.
4. Apply a straight, slightly inset crop in the corrected plane, remove rail
   protrusions, and feather inward. Small corner arcs are estimated separately.
5. Compose the mappings for one final color sampling. The final analytic alpha
   follows that warp and adds no matte or stroke.

None of the five supplied cassettes passed the multi-edge radial-model test;
all used the explicitly logged approximate edge blend. Logs state
`model_specific_profile_applied: false` and
`prior_software_lens_correction: "unknown"`. No calibrated profile is loaded.

Discs record the same camera provenance but currently receive no lens correction.
A centered radial warp can leave the outer rim round while distorting interior
artwork. Use matching calibration or independent straight references before
extending that correction to discs. Angle alone is not the trigger: optical bow
can occur head-on. See [perspective, lens distortion and depth](LENS_AND_DEPTH.md).

For future calibration, photograph a flat grid at several positions with the same
physical camera, focus range, zoom/crop, resolution, and export pipeline used for
archiving. Verify the resulting correction on separate captures. As a capture
recommendation, keep the camera approximately parallel, leave some margin around
the object, and watch for macro switching. No lens model recovers occluded detail
or removes the depth parallax of a thick cassette shell.
