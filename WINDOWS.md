# Windows CMD quick start

Disc Straighten 0.6.0 runs from the ordinary Windows Command Prompt (`cmd.exe`).
It uses Python, ImageMagick and local Tesseract OCR. No WSL, Apple frameworks or
cloud OCR account is needed. The download is a source kit with a `.cmd` launcher,
not a self-contained `.exe`.

## Install prerequisites once

Install **Python 3.12 or later**, **ImageMagick 7**, and **Tesseract 5**. Include
Python's launcher and add ImageMagick and Tesseract to PATH during installation.
Install English Tesseract language data; add Russian data for Russian labels.
Tesseract is optional for bounded disc straightening: unavailable OCR automatically
falls back to a −45° to +45° visual search. Cassette automatic orientation needs OCR.
Close and reopen CMD after changing PATH.

With Windows Package Manager, these commands are an alternative to the installers:

```bat
winget install --exact --id Python.Python.3.13
winget install --exact --id ImageMagick.ImageMagick
winget install --exact --id UB-Mannheim.TesseractOCR
```

Installer and CLI references: [Python on Windows](https://docs.python.org/3/using/windows.html),
[ImageMagick downloads](https://imagemagick.org/script/download.php),
[Tesseract installation](https://tesseract-ocr.github.io/tessdoc/Installation.html),
[Tesseract command line](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).
Tesseract's Windows installer is maintained separately by UB Mannheim, as linked
by the Tesseract project. Package availability and installer versions can change.

Verify in a new CMD window:

```bat
py -3 --version
magick -version
tesseract --version
tesseract --list-langs
```

## Extract and run

Extract the release ZIP into a writable folder. Run these commands from its
`disc-straighten` directory:

```bat
disc-straighten.cmd -h
disc-straighten.cmd "C:\Photos\Cassette scans" --media cassette -o "C:\Photos\Prepared" --preview
disc-straighten.cmd "C:\Photos\disc.jpg" --media auto --languages eng -o processed
disc-straighten.cmd "C:\Photos\mini cd.jpg" --disc-size 80 -o processed
disc-straighten.cmd "C:\Photos\Russian disc.jpg" --languages eng,rus -o processed
```

The first launch creates `.venv` and installs the pinned Python dependencies.
It requires internet access for that setup. Later local-image processing is
offline. Use a writable folder rather than `Program Files`. Paths with spaces
must be quoted. Inputs and original metadata are preserved in the source files.
Do not share a Mac-created `.venv` with Windows; each platform creates its own.

Automatic OCR uses Tesseract on Windows. `--ocr tesseract` also selects it on
macOS for comparison; `--ocr vision` is macOS-only. `eng`/`rus` and `en-US`/`ru-RU`
are accepted by the Tesseract adapter. Missing requested languages are recorded
and produce a review flag when another requested language is available. If none
are installed, discs automatically use the same visual fallback as missing
Tesseract. The result is flagged for review because this cannot read text or
resolve upside-down orientation. Blank or inconclusive discs stay unrotated.
No flag is required; `--ocr none` explicitly tests this path. For cassettes,
missing OCR still requires a reviewed manual angle or installing Tesseract.

For a reviewed manual direction, OCR can be bypassed:

```bat
disc-straighten.cmd tape.jpg --media cassette --angle 0 -o reviewed
disc-straighten.cmd disc.jpg --angle -17 -o reviewed
```

Cassette angles select 0 or 180 degrees **after** body rectification. Disc angles
are clockwise corrections in degrees. `--cassette-crop rectangle` disables the
measured corner-arc mask for a comparison.

## Exit codes and batch files

- `0`: processed without review flags.
- `2`: PNGs and logs saved; review them. Cassette results currently always need review.
- `1`: at least one input failed. Other items in a batch may have succeeded.

Inside another `.cmd`/`.bat` script use `call`:

```bat
call disc-straighten.cmd "C:\Photos\Tapes" --media cassette -o processed
set "DISC_RESULT=%ERRORLEVEL%"
if "%DISC_RESULT%"=="2" echo Images saved; review the JSON warnings.
if "%DISC_RESULT%"=="1" echo At least one image failed; read its error.
exit /b %DISC_RESULT%
```

For exact branching, store `%ERRORLEVEL%` immediately after `call`; `2` is a
review outcome rather than a failed render. Do not assume every nonzero code
means no output was created.

## Troubleshooting and color

If a command is not recognized, add its install folder to PATH and reopen CMD.
A typical Tesseract folder is `C:\Program Files\Tesseract-OCR`.
ImageMagick must be version 7 with the `magick` command.

Embedded ICC images are converted through Windows' standard sRGB profile at
`%WINDIR%\System32\spool\drivers\color\sRGB Color Space Profile.icm`.
If that profile is unavailable, set `DISC_SRGB_PROFILE` to a valid sRGB ICC/ICM
file. The tool fails explicitly rather than silently ignoring an embedded profile.
Untagged RGB is interpreted as sRGB and this assumption is logged.

```bat
set "DISC_SRGB_PROFILE=C:\Color Profiles\sRGB.icc"
```

Tesseract and Apple Vision can choose different text directions. Their engine,
languages and missing-language flags are logged. Neither engine proves the
artist's intended primary orientation. Preserve and review the original image.
