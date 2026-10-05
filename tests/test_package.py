"""Keep private image/research inputs outside the default public release."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from package import PUBLIC_FILES, export_tree, public_files, write_archive


class PublicPackageTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        for name in PUBLIC_FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('public fixture\n')

    def test_only_allowlisted_sources_are_collected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            private = ['validation/photo.png', 'research/cassette-evidence/standard.pdf',
                       'examples/downloaded.jpg', 'discstraight/private.png',
                       '.env', 'research.html', 'dist/old.whl']
            for name in private:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('private fixture\n')
            chosen = {p.relative_to(root).as_posix() for p in public_files(root)}
            self.assertEqual(chosen, set(PUBLIC_FILES))
            self.assertTrue(chosen.isdisjoint(private))

    def test_selected_symlink_cannot_export_an_external_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            root.mkdir()
            self.fixture(root)
            outside = root.parent / 'private.txt'
            outside.write_text('private fixture\n')
            (root / 'README.md').unlink()
            (root / 'README.md').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'linked public source'):
                public_files(root)

    def test_existing_export_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            marker = destination / 'keep.txt'
            marker.write_text('keep\n')
            with self.assertRaises(FileExistsError):
                export_tree(destination, [])
            self.assertEqual(marker.read_text(), 'keep\n')

    def test_archive_hashes_modes_and_private_notice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / 'launcher'
            launcher.write_text('#!/bin/sh\nexit 0\n')
            launcher.chmod(0o755)
            entries = [(launcher, 'disc-straighten/disc-straighten')]
            for private in [False, True]:
                target = root / f'{private}.zip'
                with contextlib.redirect_stdout(io.StringIO()):
                    write_archive(target, entries, private=private)
                with zipfile.ZipFile(target) as archive:
                    self.assertEqual('PRIVATE-TEST-ARTWORK-NOTICE.txt' in archive.namelist(), private)
                    manifest = json.loads(archive.read('SHA256-MANIFEST.json'))
                    self.assertEqual(set(archive.namelist()), set(manifest) | {'SHA256-MANIFEST.json'})
                    for name, expected in manifest.items():
                        self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)
                    mode = archive.getinfo('disc-straighten/disc-straighten').external_attr >> 16
                    self.assertTrue(mode & 0o111)
                self.assertEqual(target.with_suffix('.zip.sha256').read_text().split()[0],
                                 hashlib.sha256(target.read_bytes()).hexdigest())
