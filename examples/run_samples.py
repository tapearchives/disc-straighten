"""Download the user-supplied samples, create rotation controls, run the CLI.

After first-run setup: .venv/bin/python examples/run_samples.py /path/to/test-run
Sample art is downloaded only by this explicit command, not by installing the tool.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discstraight.cli import acquire


def main():
    dest = Path(sys.argv[1] if len(sys.argv)>1 else 'sample-run').resolve()
    source_folder = dest/'source'; source_folder.mkdir(parents=True,exist_ok=True)
    paths = []
    for item in json.loads((ROOT/'examples/sources.json').read_text()):
        with tempfile.TemporaryDirectory() as temp:
            source,metadata = acquire(item['url'],Path(temp))
            if metadata['sha256']!=item['sha256']:
                raise ValueError(f"Source changed since validation: {item['name']}")
            target = source_folder/f"{item['name']}.jpg"
            target.write_bytes(source.read_bytes()); paths.append(target)
    for stem,angle,name in [('mobile-computers',117,'mobile-117'),('computerra',90,'computerra-90')]:
        target=source_folder/f'{name}.png'
        subprocess.run(['magick',str(source_folder/f'{stem}.jpg'),'-background','white',
                        '-rotate',str(angle),'+repage',str(target)],check=True)
        paths.append(target)
    result = subprocess.run([str(ROOT/'disc-straighten'),*[str(p) for p in paths],
                             '--output',str(dest/'results'),'--preview'])
    if result.returncode not in [0,2]:
        return result.returncode
    subprocess.run([sys.executable,str(ROOT/'tests/verify_results.py'),str(dest/'results'),
                    str(dest/'validation-report.json')],check=True)
    print('Sample checks passed; consult result logs for review flags.')
    return result.returncode


if __name__=='__main__':
    raise SystemExit(main())
