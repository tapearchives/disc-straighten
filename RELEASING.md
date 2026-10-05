# Preparing a public release

The release repository is [tapearchives/disc-straighten](https://github.com/tapearchives/disc-straighten).
These instructions prepare and verify source exports. Pushing commits and
publishing release assets are separate steps after verification.

## Verify and export

From the source directory on a supported Mac:

```sh
./de-askew --help
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/synthetic_smoke.py
.venv/bin/python examples/cassette_smoke.py
.venv/bin/python package.py --export-tree ../de-askew-github-v0.8.0
```

The last command creates `dist/de-askew-0.8.0-source.zip` and a separate
clean source directory. The export destination must not already exist. Both
contain SHA-256 manifests. The ZIP preserves the launcher's executable mode.
No wheels, environments, downloaded standards/patents, original source photos, private
validation derivatives, or unrelated workspace Git history are copied.

Build the native Mac interface with `python3 build_macos.py`; see [Mac app](MACOS.md).
The app embeds the processor source and notices. Its Python runtime lives in
Application Support; do not bundle your private runtime or preferences. The app
is ad-hoc signed for local use, not notarized for unrestricted distribution.

The export is a release snapshot, not a second development authority. Make
changes in the development source and create a fresh snapshot for a new review.
Keep a public repository separate from any enclosing multi-project workspace.
To initialize the exported tree locally, run `git init -b main` from inside it;
inspect its manifest and `git status` before creating an initial commit. Choose
the final GitHub owner/name when publication is requested. Do not attach a remote
or upload the private validation directory as part of source preparation.

## Build an installable wheel

```sh
.venv/bin/python -m pip wheel --no-deps . --wheel-dir dist
```

The wheel contains Python and original Swift source, not native dependencies.
ImageMagick and the selected OCR engine remain external prerequisites. Retain
`THIRD_PARTY_NOTICES.md` and `licenses/` alongside any release that also distributes
dependency binaries. A complete frozen executable requires a separate dependency
and license review; the source ZIP is the preferred initial sharing artifact.

The configured GitHub workflow runs unit tests, a generated-image integration
check, the CMD launcher, and wheel builds on macOS and Windows. It has read-only repository permissions and
does not publish releases. Local checks do not establish a hosted Actions result.

## Private validation bundles

Private derivatives are never included by default. An explicit request can
create a separately marked archive:

```sh
.venv/bin/python package.py --private-results validation/release-results-v0.3.0
```

This also writes `*-private-tests.zip` with a notice that the artwork is excluded
from the software license. Keep it private. It is not a GitHub release asset.

## Version notes

Update `discstraight/__init__.py`, `pyproject.toml`, README, notices, and changelog
together. Keep historical benchmark and sample reports labeled with the version
that actually produced them. Recheck generated source contents and hashes after
any change. Record the new smoke result separately rather than relabeling an old
run as current validation.

The allowlist includes a small illustrated manual with explicitly credited
Wikimedia and owner-requested sample derivatives. These images retain their
separate licenses in `discstraight/manual/ATTRIBUTION.md`; MIT covers code.
