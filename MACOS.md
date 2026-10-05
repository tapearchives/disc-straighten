# Mac drag-and-drop app

Disc Straighten 0.7.0 includes a native macOS app and the existing command line.
They use the same image processor and saved output preferences.

## Open and use

Open **Disc Straighten.app**. Drop images or folders into its large drop area,
or onto its Finder/Dock icon. **Choose Images or Folders…** does the same thing.
Folders are scanned once, without descending into subfolders. JPEG, PNG, TIFF,
WebP and BMP are supported; HEIC and raw camera files need conversion first.

The app starts processing on drop. Choose **Automatic**, **Optical disc**, or
**Compact cassette** before adding a batch. Automatic identification remains
experimental. The command line retains its compatibility default of optical disc.
Processing is sequential. Additional drops wait in a queue; **Finish Current
Batch Only** removes waiting batches and lets the active batch finish safely.
Preferences and media selection are locked while processing. Quitting waits for
you to finish processing rather than interrupting the image writer.

Results include the transparent PNG, geometry JSON, orientation JSON, and a
preview. **Review needed** means results were saved with uncertainty flags;
read the JSON before accepting them. **Show Latest Output in Finder** selects
the latest saved PNG. Originals are never modified. Existing output names are
protected; choose a new destination, move previous results, or use CLI
`--overwrite` deliberately.

## Output preferences

Open **Preferences…** (Command-comma):

- **Relative to each input folder** defaults to `output`. A photo at
  `/Photos/Album/disc.jpg` goes to `/Photos/Album/output/`. Dropping `/Photos/Album`
  has the same result. Nested paths such as `prepared/review` and sibling paths
  such as `../processed` are also accepted.
- **One fixed location** saves every batch to a folder you choose, for example
  `/Volumes/Archive/Prepared`. The folder is created when an image is processed.
- **Use Default**, then **Save**, restores the relative `output` setting.

Both JSON logs stay beside their image. Inputs with the same basename may use
separate destination folders. Names that collide in one destination are rejected
before processing that batch. The app never silently replaces previous results.

Preferences persist at:

```text
~/Library/Application Support/Disc Straighten/preferences.json
```

They also apply to command-line runs without `-o`. These commands provide the
same controls for scripts and agents:

```sh
./disc-straighten --show-preferences
./disc-straighten --set-output-relative output
./disc-straighten --set-output-relative ../processed
./disc-straighten --set-output-fixed "/Volumes/Archive/Prepared"
./disc-straighten photo.jpg -o ./one-run-override
```

Explicit `-o` overrides the preference for that run only. URL inputs use the
command's working directory as their relative base. Invalid saved preferences
produce an error; `--set-output-relative output` repairs them without affecting
any photographs. `DISC_STRAIGHTEN_PREFERENCES` can isolate settings for tests.

## Dependencies and building

The app bundles our processor source, not Python, ImageMagick or scientific
libraries. Install Python 3.12+ and ImageMagick 7 first. Apple Command Line Tools
are needed to build the app and compile the Vision OCR helper on its first use:

```sh
brew install python imagemagick
xcode-select --install
python3 build_macos.py
open "dist/Disc Straighten.app"
```

Build again with `python3 build_macos.py --replace`. The build is for the Mac's
native architecture. The script checks its bundle identifier before replacing a
previous build, embeds only source and dependency notices, and verifies an ad-hoc
code signature. A downloaded build is **not Developer ID signed or notarized**;
building from source is the supported sharing route for now.

First launch installs pinned Python dependencies into
`~/Library/Application Support/Disc Straighten/runtime`, outside the signed app.
This can take a few minutes and requires internet access. Subsequent local image
work is offline. Homebrew's standard Apple Silicon and Intel executable paths are
searched even when launching from Finder. `DISC_PYTHON` can select another Python
installation; `DISC_STRAIGHTEN_ENV` can select another runtime directory.
Source CLI runs still use `.venv` in the source directory by default.

The built app can be moved to Applications; its bundled processor moves with it.
Keep prerequisites installed. Moving it does not move your saved preferences or
images. The Windows CMD launcher remains supported; this native interface is Mac
only. Geometry, lens-correction policy, resampling and confidence limits are
unchanged by the interface.

Implementation uses Apple's [native drag destination API](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/DragandDrop/Tasks/acceptingdrags.html)
and [Process output pipes](https://developer.apple.com/documentation/foundation/process/standardoutput).
