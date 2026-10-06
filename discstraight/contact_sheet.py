"""A Letter-size, 4 by 5 archival contact sheet with complete catalog accounting."""
from __future__ import annotations

import datetime
import json
import math
from pathlib import Path
import tempfile

from .catalog import inventory
from .imaging import run, sha256, srgb_profile
from .outputs import reserve_folder
from . import __version__

# Measured from the supplied two-page reference (PDF points, 72 per inch).
PAGE = (612, 792)
COLUMNS, ROWS = 4, 5
LEFT, TOP, WIDTH, HEIGHT, ROW_STEP = 36, 96, 135, 88, 123.5


def frame_fit(width: int, height: int, requested: str) -> str:
    """Reference fill may trim background, but must not cut a portrait photo in half."""
    ratio = (width / height) / (WIDTH / HEIGHT)
    retained_fraction = min(ratio, 1 / ratio)
    return 'contain' if requested == 'cover' and retained_fraction < .8 else requested


def thumbnail(source: Path, target: Path) -> None:
    raster = str(source) + '[0]'
    profiles = run(['magick', 'identify', '-ping', '-format', '%[profiles]', raster])
    command = ['magick', raster, '-auto-orient']
    if 'icc' in profiles.lower() or 'icm' in profiles.lower():
        command += ['-profile', str(srgb_profile())]
    run(command + ['-colorspace', 'sRGB', '-thumbnail', '900x650>', '-strip', '-depth', '8', str(target)])


def create(folder: Path, *, output: Path | None = None, title: str = 'Media Archives Catalog',
           subtitle: str = 'Audio Cassette Tapes Media Asset ID# {start} - {end}',
           footer: str = 'Created with de-askew', start: str | None = None, end: str | None = None,
           page_limit: int | None = None, image_fit: str = 'cover', progress=None) -> dict:
    from PIL import Image
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import pypdfium2 as pdfium

    progress = progress or (lambda event: None)
    if page_limit is not None and not 1 <= page_limit <= 1000:
        raise ValueError('Preview page limit must be between 1 and 1,000.')
    if image_fit not in ('cover','contain'):
        raise ValueError('Choose cover (reference layout) or contain (entire image).')
    if not title.strip() or any(len(x) > 500 for x in (title, subtitle, footer)):
        raise ValueError('Enter a title; each heading/footer must be at most 500 characters.')
    report = inventory(folder, start, end)
    entries = report['entries']
    pages = math.ceil(len(entries) / (COLUMNS * ROWS))
    selected_pages = min(pages, page_limit) if page_limit else pages
    # Completed reports publish as one folder only after the PDF and page previews succeed.
    base = output or (folder / 'contact-sheet')
    root = reserve_folder(base)
    try:
        with tempfile.TemporaryDirectory(prefix='.contact-work-', dir=root) as directory:
            work = Path(directory)
            pdf = work / 'contact-sheet.pdf'
            c = canvas.Canvas(str(pdf), pagesize=PAGE, pageCompression=1)
            c.setTitle(title); c.setAuthor('de-askew'); c.setSubject('Catalog sequence contact sheet')
            printed = datetime.date.today().strftime('%A, %B %d, %Y').replace(' 0', ' ')
            sub = subtitle.replace('{start}', report['start']).replace('{end}', report['end'])

            def centered(text, y, size, x=306, max_width=540):
                fitted = min(size, size * max_width / max(1, c.stringWidth(text, 'Helvetica', size)))
                c.setFont('Helvetica', fitted); c.drawCentredString(x, y, text)

            for page in range(selected_pages):
                c.setFillColorRGB(0, 0, 0)
                centered(title, 738, 15); centered(sub, 720, 15)
                selected = entries[page*20:(page+1)*20]
                for index, entry in enumerate(selected):
                    x = LEFT + (index % COLUMNS) * WIDTH
                    y = PAGE[1] - TOP - (index // COLUMNS) * ROW_STEP - HEIGHT
                    c.saveState()
                    clip = c.beginPath(); clip.roundRect(x, y, WIDTH, HEIGHT, 9)
                    c.clipPath(clip, stroke=0, fill=0)
                    if entry['kind'] == 'missing':
                        c.setFillColorRGB(1, 1, 0); c.rect(x, y, WIDTH, HEIGHT, fill=1, stroke=0)
                        c.setFillColorRGB(0, 0, 1); c.setFont('Helvetica-Bold', 21)
                        for text, offset in zip(('MISSING', 'MEDIA', 'IMAGE'), (29, 50, 71)):
                            c.drawCentredString(x+WIDTH/2, y+HEIGHT-offset, text)
                    else:
                        source = Path(entry['path']); thumb = work / 'thumb.png'
                        thumbnail(source, thumb)
                        with Image.open(thumb) as image:
                            w, h = image.size
                            fit = frame_fit(w, h, image_fit)
                            entry['frame_fit'] = fit
                            if fit != image_fit:
                                entry['display_note'] = 'Whole image fit: frame filling would hide more than 20% of the photograph; no rotation inferred.'
                            scale = (max if fit=='cover' else min)(WIDTH/w, HEIGHT/h)
                            dw, dh = w*scale, h*scale
                            c.setFillColorRGB(1, 1, 1); c.rect(x, y, WIDTH, HEIGHT, fill=1, stroke=0)
                            # The reference fills each frame, centered in both axes.
                            # This is presentation clipping only; source/masters stay intact.
                            image_y = y+(HEIGHT-dh)/2
                            c.drawImage(ImageReader(image.copy()), x+(WIDTH-dw)/2, image_y,
                                        dw, dh, mask='auto')
                        entry['sha256'] = sha256(source)
                    c.restoreState()
                    c.setStrokeColorRGB(0, 0, 0); c.setLineWidth(.9); c.setDash(1.7, 2.3)
                    c.roundRect(x, y, WIDTH, HEIGHT, 9, stroke=1, fill=0); c.setDash()
                    c.setFillColorRGB(0, 0, 0)
                    for line, text in enumerate(entry['caption'].splitlines()):
                        centered(text, y-14-line*15, 12, x+WIDTH/2, WIDTH-4)
                    entry.update(page=page+1, cell=index+1)
                    progress(dict(status='contact_progress', completed=page*20+index+1,
                                  total=min(len(entries), selected_pages*20), catalog=entry['catalog']))
                centered(f'{footer}. Printed {printed}. Page {page+1}', 39, 11.75)
                c.showPage()
            c.save()
            previews = []
            with pdfium.PdfDocument(pdf) as document:
                for index in range(len(document)):
                    path = work / f'page-{index+1:03}.png'
                    page = document[index]
                    bitmap = page.render(scale=1.5)
                    bitmap.to_pil().save(path)
                    bitmap.close(); page.close()
                    previews.append(path.name)
            report.update(tool='de-askew',version=__version__,title=title, subtitle=sub, footer=footer, pages=selected_pages,
                          complete=selected_pages == pages, available_pages=pages,
                          displayed_entries=min(len(entries), selected_pages*20),
                          page_size_points=list(PAGE), grid=[COLUMNS, ROWS], image_fit=image_fit,
                          pdf='contact-sheet.pdf', previews=previews,
                          missing_semantics='No image available in this folder; not proof that physical media is missing.',
                          created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            (work / 'contact-sheet.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            for name in ['contact-sheet.pdf', *previews, 'contact-sheet.json']:
                (work / name).replace(root / name)
    except Exception:
        # Leave a recoverable error marker; never replace a prior report.
        (root / 'FAILED.txt').write_text('Report generation failed. Retry with a new report folder.\n', encoding='utf-8')
        raise
    return dict(status='contact_complete', folder=str(root), pdf=str(root/'contact-sheet.pdf'),
                log=str(root/'contact-sheet.json'), previews=[str(root/p) for p in previews],
                pages=selected_pages, catalogs=report['catalog_count'], missing=report['missing_count'],
                images=report['image_count'], complete=report['complete'], ignored=report['ignored_files'])
