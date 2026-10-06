"""Build a relocatable native Mac app around the source processor (no bundled dependencies)."""
from __future__ import annotations

import argparse
from pathlib import Path
import plistlib
import platform
import shutil
import subprocess
import sys
import tempfile

from discstraight import __version__

ROOT = Path(__file__).resolve().parent
BUNDLE_ID = 'org.tapearchives.disc-straighten'


def build(destination: Path, replace: bool = False) -> None:
    if sys.platform != 'darwin':
        raise RuntimeError('Build the native app on macOS with Apple Command Line Tools')
    destination = destination.expanduser().absolute()
    if destination.suffix != '.app':
        raise ValueError('Output must end with .app')
    if destination.is_symlink():
        raise ValueError('Refusing to replace a symlink')
    if destination.exists():
        info = destination / 'Contents' / 'Info.plist'
        if not replace or not info.is_file() or plistlib.loads(info.read_bytes()).get('CFBundleIdentifier') != BUNDLE_ID:
            raise ValueError('Existing destination protected; --replace only replaces a Disc Straighten app')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.disc-app-build-', dir=destination.parent) as temporary:
        stage = Path(temporary) / destination.name
        contents = stage / 'Contents'
        binary = contents / 'MacOS' / 'DiscStraighten'
        engine = contents / 'Resources' / 'engine'
        binary.parent.mkdir(parents=True)
        engine.mkdir(parents=True)
        (engine / 'discstraight').mkdir()
        for source in (ROOT / 'discstraight').iterdir():
            if source.suffix in {'.py', '.swift', '.json'} and source.is_file() and not source.is_symlink():
                shutil.copy2(source, engine / 'discstraight' / source.name)
        for name in ['de-askew', 'un-askew', 'disc-straighten', 'requirements.lock.txt', 'LICENSE', 'THIRD_PARTY_NOTICES.md']:
            shutil.copy2(ROOT / name, engine / name)
        (engine / 'disc-straighten').chmod(0o755)
        (engine / 'un-askew').chmod(0o755)
        (engine / 'de-askew').chmod(0o755)
        shutil.copytree(ROOT / 'discstraight' / 'manual', contents / 'Resources' / 'manual')
        shutil.copy2(ROOT / 'assets' / 'de-askew.icns', contents / 'Resources' / 'de-askew.icns')
        shutil.copytree(ROOT / 'licenses', engine / 'licenses')
        plist = dict(CFBundleIdentifier=BUNDLE_ID, CFBundleName='de-askew',
                     CFBundleDisplayName='de-askew', CFBundleExecutable='DiscStraighten', CFBundleIconFile='de-askew.icns',
                     CFBundlePackageType='APPL', CFBundleShortVersionString=__version__, CFBundleVersion=__version__,
                     LSMinimumSystemVersion='13.0', NSHighResolutionCapable=True,
                     NSHumanReadableCopyright='MIT · TapeArchives',
                     CFBundleDocumentTypes=[dict(CFBundleTypeName='Images and folders', CFBundleTypeRole='Viewer',
                                                LSHandlerRank='Alternate', LSItemContentTypes=['public.image', 'public.folder'])])
        (contents / 'Info.plist').write_bytes(plistlib.dumps(plist))
        subprocess.run(['xcrun', 'swiftc', '-O', '-swift-version', '5', '-framework', 'Cocoa',
                        '-framework', 'UniformTypeIdentifiers', '-framework', 'WebKit', '-framework', 'PDFKit', '-module-cache-path', str(Path(temporary) / 'cache'),
                        '-target', f'{platform.machine()}-apple-macosx13.0',
                        str(ROOT / 'macos' / 'DiscStraighten.swift'), '-o', str(binary)], check=True)
        subprocess.run(['codesign', '--force', '--sign', '-', str(stage)], check=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(stage)], check=True)
        previous = Path(temporary) / 'previous.app'
        if destination.exists():
            destination.rename(previous)
        try:
            stage.rename(destination)
        except OSError:
            if previous.exists():
                previous.rename(destination)
            raise
    print(f'Built {destination}')
    print('Requires Python 3.12+ and ImageMagick 7. First use installs Python dependencies into Application Support.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'de-askew.app')
    parser.add_argument('--replace', action='store_true', help='Replace an existing app with the same bundle identifier')
    args = parser.parse_args()
    build(args.output, args.replace)


if __name__ == '__main__':
    main()
