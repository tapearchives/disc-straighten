"""Ordered batch events with an independent sequential input-preview worker."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import uuid

from .outputs import reserve_folder, targets


def run_batch(items, names, destinations, args, cache, process) -> int:
    from .cli import acquire, write_json
    from .imaging import run
    from .barcode_pairs import rename_pair, rename_back
    lock=threading.Lock();batch_id=uuid.uuid4().hex
    def emit(event):
        with lock:print(json.dumps(event,ensure_ascii=False),flush=True)
    reserved={};records=[];status=0;references={}
    for index,(item,name,destination) in enumerate(zip(items,names,destinations)):
        record=dict(input=item,name=name,event_id=f'{batch_id}:{index}')
        try:
            if destination not in reserved:reserved[destination]=reserve_folder(destination,overwrite=args.overwrite)
            root=reserved[destination]
            record.update(root=root,paths=targets(root,name))
        except OSError as error:
            record['setup_error']=str(error)
        records.append(record)
        emit(dict(input=item,event_id=record['event_id'],status='queued',
                  queued_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))

    def preview(record):
        if 'setup_error' in record:return
        try:
            with tempfile.TemporaryDirectory(prefix='.input-preview-',dir=record['root']) as folder:
                work=Path(folder)
                # Thumbnail generation is independent of geometry, OCR and the
                # final linear-light warp. No UI thread loads full-size photos.
                item=record['input']
                source=Path(item) if Path(item).is_file() else acquire(item,work)[0]
                target=work/'before.png'
                run(['magick',str(source)+'[0]','-auto-orient','-thumbnail','700x500>',
                     '-colorspace','sRGB','-background','#eeeeee','-alpha','remove','-alpha','off',
                     '-strip','-depth','8',str(target)])
                target.replace(record['paths']['before'])
            emit(dict(input=record['input'],event_id=record['event_id'],status='input_preview',
                      before_preview=str(record['paths']['before'])))
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            emit(dict(input=record['input'],event_id=record['event_id'],status='preview_unavailable',preview_error=str(error)))

    def event(record,status_override=None):
        result=record['result'];paths=record['paths']
        return dict(input=record['input'],event_id=record['event_id'],status=status_override or result['status'],
                    result_status=result['status'],clockwise_degrees=result['rotation']['clockwise_degrees'],
                    image=str(paths['image']),log=str(paths['log']),
                    before_preview=str(paths['before']) if paths['before'].exists() else None,
                    preview=str(paths['preview']) if paths['preview'].exists() else None,
                    completed_utc=result.get('created_utc'),warnings=result['warnings'],
                    barcode_pair=result.get('barcode_pair'))

    previous=None
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='input-previews') as executor:
        futures=[executor.submit(preview,record) if args.preview else None for record in records]
        args.background_previews=bool(args.preview)
        for record,future in zip(records,futures):
            try:
                if 'setup_error' in record:raise OSError(record['setup_error'])
                args.output=record['root']
                emit(dict(input=record['input'],event_id=record['event_id'],status='processing',output_folder=str(args.output)))
                record['result']=process(record['input'],record['name'],args,cache)
                record['paths']['image']=record['root']/record['result']['output']['file']
                # A preview must finish before moving its names. Other input
                # thumbnails continue while the main thread converts this one.
                if future:future.result()
                if record['result'].get('catalog_reference'):
                    from .catalog import preserve_reference
                    reference=preserve_reference(record)
                    references.setdefault(record['root'],[]).append(reference)
                    if status==0:status=2
                    emit(event(record));previous=None
                    continue
                if args.name_barcode_pairs:
                    changed,reason=rename_pair(previous,record)
                    if not changed and args.gap_placeholders and reason in (
                            'no_successful_immediately_previous_input','previous_input_already_paired',
                            'previous_input_has_barcode_or_unverified_scan'):
                        changed,reason=rename_back(record)
                    if changed:
                        if len(changed)==2:emit(event(changed[0],'renamed'))
                    else:
                        result=record['result']
                        result['barcode_pair']=dict(status='unpaired',reason='no_barcode_on_this_input' if reason=='not_found' else reason)
                        if reason!='not_found':
                            result['warnings'].append('barcode_pair_'+reason.split(':')[0]);result['status']='review_required'
                        write_json(record['paths']['log'],result)
                if record['result']['status']=='review_required' and status==0:status=2
                emit(event(record));previous=record
            except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as error:
                status=1;previous=None
                if future:future.result()
                failure=dict(input=record['input'],event_id=record['event_id'],status='failed',error=str(error))
                if 'root' in record:
                    try:write_json(record['root']/'output-json'/(record['name']+'-failure.json'),failure)
                    except OSError:pass
                emit(failure)
    if args.name_barcode_pairs and args.gap_placeholders:
        from .catalog import materialize_gaps
        for root in reserved.values():
            try:
                if root in references:
                    write_json(root/'output-json'/'catalog-anchors.json',dict(schema=1,references=references[root]))
                catalog=materialize_gaps(root,args.catalog_start,args.catalog_end)
                emit(dict(status='catalog_complete',folder=str(root),catalogs=catalog['catalog_count'],
                          placeholders=len(catalog['generated_placeholders']),unassigned=catalog['ignored_files'],
                          references=len(catalog['barcode_references']),
                          log=str(root/'output-json'/'catalog-sequence.json')))
            except (ValueError,OSError,RuntimeError) as error:
                status=2 if status==0 else status
                issue=dict(status='catalog_review',folder=str(root),error=str(error))
                write_json(root/'output-json'/'catalog-sequence-review.json',issue)
                emit(issue)
    return status
