"""Windows CMD bootstrap, with no third-party imports before environment setup."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def main() -> int:
    if sys.version_info<(3,12):
        print('Python 3.12+ is required. See WINDOWS.md.',file=sys.stderr);return 1
    venv=ROOT/'.venv';python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.is_file():
        subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
    requirements=ROOT/'requirements.lock.txt'
    stamp=venv/('requirements-'+hashlib.sha256(requirements.read_bytes()).hexdigest())
    if not stamp.exists():
        subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(requirements)],check=True)
        stamp.touch()
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT)+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    return subprocess.run([str(python),'-m','discstraight',*sys.argv[1:]],env=env).returncode


if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,subprocess.CalledProcessError) as error:
        print(f'Setup failed: {error}. See WINDOWS.md.',file=sys.stderr);sys.exit(1)
