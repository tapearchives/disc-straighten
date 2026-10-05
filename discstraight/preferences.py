"""Shared output preferences for the CLI and native Mac app."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path, PureWindowsPath
import sys
import tempfile
from urllib.parse import urlsplit


def preferences_path() -> Path:
    override = os.environ.get('DISC_STRAIGHTEN_PREFERENCES')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    elif sys.platform == 'win32':
        root = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        root = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return root / 'Disc Straighten' / 'preferences.json'


@dataclass(frozen=True)
class OutputPreferences:
    output_mode: str = 'relative'
    relative_folder: str = 'output'
    fixed_folder: str = ''

    def validated(self) -> OutputPreferences:
        if self.output_mode not in {'relative', 'fixed'}:
            raise ValueError('Output mode must be relative or fixed')
        if not isinstance(self.relative_folder, str) or not self.relative_folder.strip():
            raise ValueError('Relative output folder must not be empty')
        relative = self.relative_folder
        if ('\x00' in relative or Path(relative).is_absolute()
                or PureWindowsPath(relative).anchor or relative.startswith('~')):
            raise ValueError('Use a relative folder such as output or ../processed, or select a fixed location')
        if not isinstance(self.fixed_folder, str) or '\x00' in self.fixed_folder:
            raise ValueError('Fixed output folder must be a path')
        if self.output_mode == 'fixed' and not Path(self.fixed_folder).is_absolute():
            raise ValueError('Fixed output folder must be an absolute path')
        return self


def load_preferences() -> OutputPreferences:
    path = preferences_path()
    if not path.exists():
        return OutputPreferences()
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('schema') != 1:
            raise ValueError('Unsupported preferences schema')
        return OutputPreferences(**{key: value[key] for key in
                                    ('output_mode', 'relative_folder', 'fixed_folder')}).validated()
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f'Invalid preferences at {path}: {error}; use --set-output-relative output to reset') from error


def save_preferences(preferences: OutputPreferences) -> None:
    preferences.validated()
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Same-directory replace keeps readers from seeing a partially written file.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.preferences-', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(dict(schema=1, **asdict(preferences)), stream, indent=2)
            stream.write('\n')
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def output_folder(item: str, explicit: Path | None, preferences: OutputPreferences) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    if preferences.output_mode == 'fixed':
        return Path(preferences.fixed_folder).expanduser().resolve()
    parent = Path.cwd() if urlsplit(item).scheme.lower() in {'http', 'https'} else Path(item).resolve().parent
    return (parent / preferences.relative_folder).resolve()
