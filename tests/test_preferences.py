"""Exercise destination resolution through the actual CLI, without image work."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from discstraight.cli import main
from discstraight.preferences import OutputPreferences, load_preferences, output_folder, save_preferences


class OutputPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.environment = patch.dict(os.environ, {'DISC_STRAIGHTEN_PREFERENCES': str(self.root / 'prefs.json')})
        self.environment.start()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.environment.stop)

    def invoke(self, args, process=None):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()), \
             patch('discstraight.cli.shutil.which', return_value='/magick'), \
             patch('discstraight.cli.process', side_effect=process):
            status = main(args)
        return status, out.getvalue()

    def test_default_and_saved_relative_are_per_input_parent(self):
        source = self.root / 'album' / 'disc.jpg'
        self.assertEqual(output_folder(str(source), None, load_preferences()), source.parent / 'output')
        self.invoke(['--set-output-relative', '../processed'])
        self.assertEqual(output_folder(str(source), None, load_preferences()), self.root / 'processed')

    def test_fixed_and_one_run_override(self):
        fixed = self.root / 'all results'
        self.invoke(['--set-output-fixed', str(fixed)])
        self.assertEqual(output_folder('disc.jpg', None, load_preferences()), fixed)
        self.assertEqual(output_folder('disc.jpg', self.root / 'override', load_preferences()), self.root / 'override')
        self.assertEqual(load_preferences().fixed_folder, str(fixed))
        status, text = self.invoke(['--show-preferences'])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(text)['output_mode'], 'fixed')

    def test_url_relative_is_based_on_current_directory(self):
        self.assertEqual(output_folder('https://example.com/disc.jpg', None, OutputPreferences()), Path.cwd() / 'output')

    def test_bad_preferences_fail_visibly_and_can_be_reset(self):
        (self.root / 'prefs.json').write_text('{"schema": 999}')
        with self.assertRaisesRegex(ValueError, 'Invalid preferences'):
            load_preferences()
        self.invoke(['--set-output-relative', 'output'])
        self.assertEqual(load_preferences(), OutputPreferences())
        original = (self.root / 'prefs.json').read_bytes()
        for relative in ['', '/absolute', 'C:\\absolute', '~/folder', 'bad\x00path']:
            with self.assertRaises(ValueError):
                save_preferences(OutputPreferences(relative_folder=relative))
        self.assertEqual((self.root / 'prefs.json').read_bytes(), original)
        with self.assertRaises(ValueError):
            save_preferences(OutputPreferences(output_mode='fixed', fixed_folder='relative'))

    def test_batch_routes_same_names_to_different_folders_and_keeps_review_exit(self):
        inputs = [self.root / 'a' / 'same.jpg', self.root / 'b' / 'same.jpg']
        outputs = []
        def process(item, name, args, cache):
            outputs.append(args.output)
            self.assertTrue(args.output.is_dir())
            return dict(status='review_required', rotation=dict(clockwise_degrees=0),
                        output=dict(file=name + '-straightened.png'), warnings=['review'])
        status, text = self.invoke([str(p) for p in inputs], process)
        self.assertEqual(status, 2)
        self.assertEqual(outputs, [p.parent / 'output' for p in inputs])
        self.assertEqual(len([line for line in text.splitlines() if '"image"' in line]), 2)
        status, text = self.invoke([*[str(p) for p in inputs], '-o', str(self.root / 'shared')], process)
        self.assertEqual(status, 2)
        results=[json.loads(line)['image'] for line in text.splitlines() if '"image"' in line]
        self.assertEqual(len(set(results)),2,'Same-named sources must both be processed')
        self.assertTrue(all(Path(p).parent==self.root/'shared' for p in results))

    def test_existing_output_file_is_protected_and_batch_continues(self):
        inputs = [self.root / 'a' / 'first.jpg', self.root / 'b' / 'second.jpg']
        inputs[0].parent.mkdir()
        (inputs[0].parent / 'output').write_text('existing file')
        calls = []
        def process(item, name, args, cache):
            calls.append(item)
            return dict(status='completed', rotation=dict(clockwise_degrees=0),
                        output=dict(file=name + '-straightened.png'), warnings=[])
        status, _ = self.invoke([str(p) for p in inputs], process)
        self.assertEqual(status, 0)
        self.assertEqual(calls, [str(p) for p in inputs])
        self.assertEqual((inputs[0].parent/'output').read_text(),'existing file')

    def test_preferences_action_cannot_accidentally_process_inputs(self):
        with self.assertRaises(SystemExit):
            self.invoke(['photo.jpg', '--set-output-relative', 'new'])
        self.assertFalse((self.root / 'prefs.json').exists())
