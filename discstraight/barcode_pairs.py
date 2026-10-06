"""Publish two renamed derivative sets without overwriting or touching sources."""
from __future__ import annotations

import copy
import errno
import json
import os
from pathlib import Path
import shutil

from .barcodes import filename_code


def renamed_paths(paths: dict[str,Path], code: str, side: str) -> dict[str,Path]:
    stem=code+side
    names=dict(image=stem+'.png',log=stem+'.json',orientation=stem+'-orientation.json',
               metadata=stem+'-source-metadata.json',preview=stem+'-preview.png',before=stem+'-before.png')
    return {key:path.with_name(names[key]) for key,path in paths.items()}


def rename_pair(previous: dict | None, current: dict) -> tuple[list[dict],str]:
    code,reason=filename_code(current['result'].get('barcodes',{}))
    if code is None:return [],reason
    if previous is None:return [],'no_successful_immediately_previous_input'
    if previous.get('paired'):return [],'previous_input_already_paired'
    if previous['result'].get('barcodes',{}).get('status') not in ('not_found',):
        return [],'previous_input_has_barcode_or_unverified_scan'
    return _publish(code, [(previous,'A',current),(current,'B',previous)])


def rename_back(current: dict) -> tuple[list[dict],str]:
    """A decoded back retains its identity even when its front is unavailable."""
    code,reason=filename_code(current['result'].get('barcodes',{}))
    if code is None:return [],reason
    return _publish(code, [(current,'B',None)])


def _publish(code: str, assignments: list[tuple]) -> tuple[list[dict],str]:
    plans=[];created=[]
    for record,side,partner in assignments:
        old=record['paths'];new=renamed_paths(old,code,side)
        existing={key:path for key,path in old.items() if path.exists()}
        for key in existing:
            # Check case-folded names too, for portable archives on Unix volumes.
            if any(p.name.casefold()==new[key].name.casefold() for p in new[key].parent.iterdir()):
                return [],'barcode_output_name_collision'
        result=copy.deepcopy(record['result'])
        result['output']['file']=new['image'].relative_to(record['root']).as_posix()
        if result.get('finishing',{}).get('metadata',{}).get('enabled'):
            result['finishing']['metadata']['source_inventory_file']=new['metadata'].name
        result['barcode_pair']=dict(status='paired' if partner else 'back_only',barcode=code,side=side,
                                    partner_input=partner['input'] if partner else None,original_output=record['result']['output']['file'],
                                    order='case-insensitive input filename, then full path; immediately adjacent inputs')
        plans.append((record,existing,new,result))
    try:
        # Every new artifact uses exclusive creation. Old names remain intact
        # until both complete sets exist; an interrupted publication cannot
        # destroy the only copy of a derivative.
        for record,existing,new,result in plans:
            for key,path in existing.items():
                if key=='log':
                    with new[key].open('x',encoding='utf-8') as stream:
                        created.append(new[key]);json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
                else:
                    try:
                        os.link(path,new[key]);created.append(new[key])
                    except OSError as error:
                        if error.errno not in (errno.EPERM,errno.EXDEV,errno.ENOTSUP,errno.EACCES):raise
                        # FAT/exFAT and some network destinations lack hardlinks.
                        with new[key].open('xb') as target,path.open('rb') as source:
                            created.append(new[key]);shutil.copyfileobj(source,target)
    except OSError as error:
        for path in reversed(created):path.unlink(missing_ok=True)
        return [],'pair_publication_failed: '+str(error)
    for record,existing,new,result in plans:
        # Failure to clean an old alias does not undo a completed publication.
        stale=[]
        for path in existing.values():
            try:path.unlink()
            except OSError:stale.append(str(path))
        if stale:
            result['barcode_pair']['retained_old_aliases']=stale
            new['log'].write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        record.update(paths=new,result=result,paired=True)
    return [record for record,_,_ in assignments], 'paired' if len(assignments)==2 else 'back_only'
