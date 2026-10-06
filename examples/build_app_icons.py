"""Rebuild photo-based ICNS/ICO assets (librsvg, ImageMagick, macOS iconutil)."""
from pathlib import Path
import base64
import json
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets'
THEME=json.loads((ROOT/'discstraight/ui_theme.json').read_text())
PHOTO=base64.b64encode((ASSETS/'disc-source.png').read_bytes()).decode('ascii')


def svg(*, small=False):
    # The Commons photograph is embedded verbatim. The tilted layer is an
    # affine duplicate, never a generated replacement for archival artwork.
    ghost='' if small else '''<g opacity=".22" transform="translate(512 478) rotate(-26) scale(1.12 .60)">
      <use xlink:href="#disc" x="-342" y="-342"/>
      <circle r="338" fill="none" stroke="#ffffff" stroke-width="4"/>
    </g>'''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1024" height="1024" viewBox="0 0 1024 1024">
    <title>de-askew: a sharp round disc with a faint tilted overlay</title>
    <defs>
      <linearGradient id="base" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{THEME['accent']}"/><stop offset="1" stop-color="{THEME['ink']}"/></linearGradient>
      <image id="disc" width="684" height="684" xlink:href="data:image/png;base64,{PHOTO}"/>
      <filter id="shadow" x="-.2" y="-.2" width="1.4" height="1.4"><feGaussianBlur stdDeviation="12"/></filter>
    </defs>
    <rect x="64" y="68" width="896" height="896" rx="198" fill="{THEME['ink']}" opacity=".18"/>
    <rect x="64" y="60" width="896" height="896" rx="198" fill="url(#base)"/>
    <rect x="67" y="63" width="890" height="890" rx="195" fill="none" stroke="#ffffff" stroke-opacity=".18" stroke-width="3"/>
    <circle cx="512" cy="531" r="340" fill="#071e29" opacity=".42" filter="url(#shadow)"/>
    <use xlink:href="#disc" x="170" y="170"/>
    {ghost}
    <path d="M158 270V174Q158 158 174 158H270 M754 866H850Q866 866 866 850V754" fill="none" stroke="#d4f3ec" stroke-width="18" stroke-linecap="round"/>
    </svg>'''


def main():
    master=ASSETS/'de-askew.svg';master.write_text(svg())
    subprocess.run(['rsvg-convert','-o',str(ASSETS/'de-askew.png'),str(master)],check=True)
    with tempfile.TemporaryDirectory(prefix='de-askew-icons-') as temp:
        temp=Path(temp);iconset=temp/'de-askew.iconset';iconset.mkdir()
        small=temp/'small.svg';small.write_text(svg(small=True))
        sizes={16,32,48,64,128,256,512,1024}
        for size in sorted(sizes):
            source=small if size<=32 else master
            subprocess.run(['rsvg-convert','-w',str(size),'-h',str(size),'-o',str(temp/f'{size}.png'),str(source)],check=True)
        for size in (16,32,128,256,512):
            shutil.copy2(temp/f'{size}.png',iconset/f'icon_{size}x{size}.png')
            shutil.copy2(temp/f'{size*2}.png',iconset/f'icon_{size}x{size}@2x.png')
        subprocess.run(['iconutil','-c','icns',str(iconset),'-o',str(ASSETS/'de-askew.icns')],check=True)
        subprocess.run(['magick',*[str(temp/f'{size}.png') for size in (16,32,48,64,128,256)],str(ASSETS/'de-askew.ico')],check=True)
    subprocess.run(['magick',str(ASSETS/'de-askew.png'),'-resize','256x256',str(ROOT/'discstraight/manual/images/app-icon.png')],check=True)


if __name__=='__main__':main()
