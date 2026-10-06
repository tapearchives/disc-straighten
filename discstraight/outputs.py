"""Per-batch destinations and separate image, preview, and JSON collections."""
from __future__ import annotations

import datetime
from pathlib import Path

from .imaging import run


def reserve_folder(base: Path, *, overwrite: bool = False) -> Path:
    base=base.resolve()
    base.parent.mkdir(parents=True,exist_ok=True)
    if overwrite:
        base.mkdir(exist_ok=True)
        selected=base
    else:
        stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        for index in range(10000):
            candidate=base if index==0 else base.with_name(base.name+'_'+stamp+(f'_{index}' if index>1 else ''))
            try:
                candidate.mkdir()
                selected=candidate
                break
            except FileExistsError:
                continue
        else:
            raise ValueError('Could not reserve a fresh output folder')
    (selected/'.un-askew-output').touch()
    return selected


def targets(root: Path, stem: str) -> dict[str,Path]:
    paths=dict(image=root/'output-images'/f'{stem}-straightened.png',
               log=root/'output-json'/f'{stem}-straightened.json',
               orientation=root/'output-json'/f'{stem}-orientation.json',
               metadata=root/'output-json'/f'{stem}-source-metadata.json',
               preview=root/'output-previews'/f'{stem}-preview.png',
               before=root/'output-previews'/f'{stem}-before.png')
    for path in paths.values():path.parent.mkdir(parents=True,exist_ok=True)
    return paths


def before_preview(normalized: Path, path: Path) -> None:
    run(['magick',str(normalized),'-background','#eeeeee','-alpha','remove','-alpha','off',
         '-resize','700x500>','-strip','-depth','8',str(path)])


def after_preview(image: Path, path: Path) -> None:
    """Show real transparency over checks; never bake a matte into the master."""
    run(['magick',str(image),'-resize','700x500>',
         '(', '+clone','-alpha','opaque','-fill','pattern:checkerboard','-draw','color 0,0 reset',
         '-fill','#eef3f5','-colorize','65',')',
         '+swap','-compose','over','-composite','-alpha','off','-strip','-depth','8',str(path)])
