# Mac drag-and-drop app

de-askew 0.9.0 includes a native macOS app and the existing command line.
They use the same image processor and saved output preferences.

## Open and use

Open **de-askew.app**. Drop images or folders into its large drop area,
or onto its Finder/Dock icon. **Choose Images or Folders…** does the same thing.
Folders include nested folders; generated output trees are skipped. JPEG, PNG,
TIFF, WebP, BMP and HEIC/HEIF are supported. HEIC requires ImageMagick libheif.

The app starts processing on drop. Choose **Automatic**, **Optical disc**, or
**Compact cassette** before adding a batch. Automatic identification remains
experimental. The command line also defaults to Automatic.
Processing is sequential. Additional drops wait in a queue; **Clear Pending Batches** removes waiting batches and lets the active batch finish safely.
Preferences and media selection are locked while processing. Quitting waits for
you to finish processing rather than interrupting the image writer.

Results include the transparent PNG, geometry JSON, orientation JSON, and a
preview. **Review needed** means results were saved with uncertainty flags;
read the JSON before accepting them. **Show Latest Output** selects
the latest saved PNG. Originals are never modified. Existing destinations get a timestamp suffix automatically; the CLI
`--overwrite` option explicitly permits reuse.

## Review workbench

Before/after cards appear in the main window, with filename, local completion
time and a persistent saved/review/failed status. Checkerboard previews reveal
the actual PNG alpha; the master contains no checkerboard. **Open Output Image** opens
a full-resolution derivative. Scrolling up to inspect an earlier result pauses
automatic following. **Activity** expands diagnostics. At small window heights,
the controls column also scrolls. Finishing and metadata copying start off.
Use **View → Compact Window** (Command-Shift-0) for a 900 × 720 layout,
or **Standard Window** (Command-0) to restore the larger workbench.
Command-R returns to comparisons; Command-L toggles Activity.
Saved PNGs and previews have no added border. After the final geometric crop,
only completely transparent outer rows and columns are removed; rounded corners
and every nonzero feather pixel remain. Logs use the resulting canvas coordinates.

## Output preferences

Open **Preferences…** (Command-comma):

- **Relative to each input folder** defaults to `output`. A photo at
  `/Photos/Album/disc.jpg` goes to `/Photos/Album/output/`. Dropping `/Photos/Album`
  has the same result. Nested paths such as `prepared/review` and sibling paths
  such as `../processed` are also accepted.
- **One fixed location** saves every batch to a folder you choose, for example
  `/Volumes/Archive/Prepared`. The folder is created when an image is processed.
- **Use Default**, then **Save**, restores the relative `output` setting.

PNG files go in `output-images`, previews in `output-previews`, and logs in
`output-json` under the reserved destination. Inputs with the same basename may use
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
open "dist/de-askew.app"
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
images. The Windows CMD launcher remains supported; this AppKit interface is Mac
only; Windows has a separate Tk front end using the same CLI. Geometry, lens-correction policy, resampling and confidence limits are
unchanged by the interface.

Implementation uses Apple's [native drag destination API](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/DragandDrop/Tasks/acceptingdrags.html)
and [Process output pipes](https://developer.apple.com/documentation/foundation/process/standardoutput).

## Processing cards and finishing controls

A separate scrollable window adds before/after pairs as each file completes,
with filename and local date/time. It keeps previous cards visible while new
ones arrive. Contrast, Brightness, Color, All adjustments and Keep metadata
start off. Preferences select relative/fixed output roots; existing folders
receive timestamp suffixes. The root contains output-images, output-previews,
and output-json. Help opens the bundled illustrated guide without networking.
The application name and icon are **de-askew**. Internal preferences/runtime
folders keep their older name to preserve existing settings.

### Live input previews and barcode naming

The batch immediately adds cards for every input in filename order. A separate
preview thread fills their left panes while conversion fills the right panes.
Use **Open Input Image** / **Open Output Image**, or right-click either image
for open, reveal-folder and copy-path actions. The output menu also opens its JSON log.

**Name barcode pairs** under Finishing defaults off. It names a barcode back
`CODEB.png` and its immediately preceding, barcode-free front `CODEA.png`.
Inputs are sorted by filename across all selected folders. Keep consecutive
front/back photos together in that order. Failed inputs break adjacency; ambiguous
codes and collisions are logged without overwriting files. All decoded values
are logged even when naming is off. See the README for pairing rules.

## Create contact sheet

The app has a **Create contact sheet** tab for output folders and catalog-named
images. It generates a Letter PDF with a 4 × 5 grid, captions, outlined frames
and yellow missing-image markers. **Name barcode pairs** enables **Add catalog
gap placeholders** automatically; clear that option if unwanted.
See [Contact sheets and catalog accounting](CONTACT_SHEETS.md) for the rules,
CLI examples, range limits, and missing-side review.
