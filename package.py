"""Export public sources by allowlist; private artwork requires an explicit path."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

from discstraight import __version__

ROOT = Path(__file__).resolve().parent
PUBLIC_FILES = (
    'tests/fixtures/gradient.heic', 'tests/fixtures/README.md',
    'docs/validation-v0.8.0.json',
    'docs/validation-v0.8.1.json',
    'discstraight/manual/images/03-after.png',
    'de-askew-gui.cmd', 'install-windows.ps1', 'assets/de-askew.svg',
    'assets/de-askew.png', 'assets/de-askew.ico', 'assets/de-askew.icns',
    'assets/disc-source.png', 'assets/README.md',
    'discstraight/manual/index.html', 'discstraight/manual/ATTRIBUTION.md',
    'discstraight/manual/samples.json', 'discstraight/manual/images/app-icon.png',
    'discstraight/manual/images/01-after.png',
    'discstraight/manual/images/01-before.jpg',
    'discstraight/manual/images/02-after.png',
    'discstraight/manual/images/02-before.jpg',
    'discstraight/manual/images/03-before.jpg',
    'discstraight/manual/images/04-after.png',
    'discstraight/manual/images/04-before.jpg',
    'discstraight/manual/images/05-after.png',
    'discstraight/manual/images/05-before.jpg',
    'discstraight/manual/images/06-after.png',
    'discstraight/manual/images/06-before.jpg',
    'discstraight/manual/images/07-before.jpg',
    'discstraight/manual/images/08-after.png',
    'discstraight/manual/images/08-before.jpg',
    'discstraight/manual/images/09-after.png',
    'discstraight/manual/images/09-before.jpg',
    'discstraight/manual/images/10-after.png',
    'discstraight/manual/images/10-before.jpg',
    'discstraight/manual/images/11-before.jpg',
    'de-askew', 'de-askew.cmd', 'un-askew', 'un-askew.cmd', 'disc-straighten', 'disc-straighten.cmd', 'bootstrap.py', 'WINDOWS.md', 'MACOS.md', 'build_macos.py', 'pyproject.toml', 'requirements.lock.txt', 'README.md',
    'USAGE.md', 'CASSETTES.md', 'LENS_AND_DEPTH.md', 'IPHONE_CAMERAS.md', 'CONTRIBUTING.md', 'RELEASING.md', 'LICENSE',
    'THIRD_PARTY_NOTICES.md', 'PERSPECTIVE.md', 'PERFORMANCE.md', 'STANDARDS.md',
    'CHANGELOG.md', 'cassette-validation-summary.json', 'validation-report.json', 'package.py', '.gitignore', '.gitattributes',
    '.github/workflows/ci.yml', 'docs/cassette-reference.svg', 'docs/lens-and-depth.svg',
    'research/ARCHIVIST_TOOLS.md', 'research/archivist-tools.csv',
    'research/archivist-tools.json', 'research/repository-snapshots.json',
    'research/cassette-reference-profile.json', 'research/REDDIT_IMAGE_REFERENCES.md',
    'benchmarks/results/ocr-encoding.json', 'benchmarks/results/baseline.json',
    'benchmarks/results/optimized.json', 'benchmarks/results/summary.json',
    'benchmarks/results/output-equivalence.json',
    'benchmarks/results/geometry-optimized-profile.txt',
    'benchmarks/results/geometry-baseline-profile.txt',
)
CODE_FOLDERS = {
    'discstraight': {'.py', '.swift'}, 'tests': {'.py'},
    'examples': {'.py', '.json'}, 'benchmarks': {'.py'}, 'macos': {'.swift'},
}
PRIVATE_NOTICE = (
    'PRIVATE TEST ARTWORK - DO NOT PUBLISH THIS ARCHIVE\n'
    'Test-results contains derivatives of separately supplied source images.\n'
    'The software MIT license grants no rights to these images or logs.\n'
    'The public source ZIP is the sharing artifact.\n'
)


def public_files(root: Path = ROOT) -> list[Path]:
    paths = {root / name for name in PUBLIC_FILES}
    for folder, suffixes in CODE_FOLDERS.items():
        paths.update(p for p in (root / folder).rglob('*')
                     if p.is_file() and p.suffix in suffixes
                     and '__pycache__' not in p.parts)
    paths.update(p for p in (root / 'licenses').rglob('*') if p.is_file())
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f'Missing public source: {path.relative_to(root)}')
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Refusing linked public source: {path.relative_to(root)}')
    return sorted(paths)


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_archive(target: Path, entries: list[tuple[Path, str]], *, private: bool = False) -> None:
    manifest = {name: digest(path) for path, name in entries}
    extra = {'PRIVATE-TEST-ARTWORK-NOTICE.txt': PRIVATE_NOTICE} if private else {}
    manifest.update({name: hashlib.sha256(value.encode()).hexdigest() for name, value in extra.items()})
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.disc-package-', dir=target.parent) as work:
        temporary = Path(work) / target.name
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path, name in entries:
                info=zipfile.ZipInfo.from_file(path,name)
                info.create_system=3
                info.external_attr=(0o100755 if Path(name).name in {'disc-straighten','un-askew','de-askew'} else 0o100644)<<16
                archive.writestr(info,path.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
            for name, value in extra.items():
                archive.writestr(name, value)
            archive.writestr('SHA256-MANIFEST.json', json.dumps(manifest, indent=2) + '\n')
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError('Archive integrity check failed')
            for name, expected in manifest.items():
                if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                    raise ValueError(f'Archive hash mismatch: {name}')
            if not archive.getinfo('disc-straighten/disc-straighten').external_attr >> 16 & 0o111:
                raise ValueError('Launcher executable mode was lost')
        temporary.replace(target)
    target.with_suffix(target.suffix + '.sha256').write_text(f'{digest(target)}  {target.name}\n')
    print(f'{target.name}: {target.stat().st_size:,} bytes; manifest and archive verified')


def export_tree(destination: Path, paths: list[Path]) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Export destination already exists; choose a new directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.disc-export-', dir=destination.parent) as work:
        stage = Path(work) / 'source'
        stage.mkdir()
        manifest = {}
        for path in paths:
            relative = path.relative_to(ROOT)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if digest(target) != digest(path):
                raise ValueError(f'Export hash mismatch: {relative}')
            manifest[relative.as_posix()] = digest(target)
        (stage / 'SHA256-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
        stage.rename(destination)
    print(f'Exported {len(paths)} public source files to {destination.name}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--export-tree', type=Path, help='New directory for a clean GitHub source snapshot')
    parser.add_argument('--private-results', type=Path,
                        help='Explicit local directory of private PNG/JSON results; makes a separate private archive')
    args = parser.parse_args()
    paths = public_files()
    if args.export_tree is not None and (args.export_tree.exists() or args.export_tree.is_symlink()):
        parser.error('--export-tree must name a new directory')
    private_paths = []
    if args.private_results is not None:
        if not args.private_results.is_dir():
            parser.error('--private-results must be an existing directory')
        private_paths = sorted(p for p in args.private_results.iterdir()
                               if p.is_file() and p.suffix in {'.png', '.json'})
        if not private_paths or any(p.is_symlink() for p in private_paths):
            parser.error('--private-results needs regular PNG/JSON files, with no symlinks')
    entries = [(p, f'disc-straighten/{p.relative_to(ROOT).as_posix()}') for p in paths]
    base = f'de-askew-{__version__}'
    write_archive(args.output_dir / f'{base}-source.zip', entries)
    if private_paths:
        write_archive(args.output_dir / f'{base}-private-tests.zip',
                      entries + [(p, f'test-results/{p.name}') for p in private_paths], private=True)
    if args.export_tree is not None:
        export_tree(args.export_tree, paths)


if __name__ == '__main__':
    main()
