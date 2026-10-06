"""Generate the shared native-interface illustration from the runtime palette."""
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
colors = json.loads((ROOT/'discstraight/ui_theme.json').read_text())
svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="200" viewBox="0 0 600 200">
<g fill="none" stroke="{line}" stroke-width="1"><path d="M20 164H580M50 18V182M550 18V182"/>
<path d="M30 40H70M30 140H70M530 40H570M530 140H570"/></g>
<g stroke="{accent}" fill="{surface}" stroke-width="3">
<circle cx="400" cy="99" r="73"/><circle cx="400" cy="99" r="10"/>
<circle cx="400" cy="99" r="29" stroke-width="1"/>
<path d="M343 71A64 64 0 0 1 431 43M348 135A64 64 0 0 0 434 152" stroke-width="1"/></g>
<g opacity=".27" fill="none" stroke="{accent}" stroke-width="3" transform="rotate(-17 400 99)">
<ellipse cx="409" cy="85" rx="83" ry="48"/><ellipse cx="409" cy="85" rx="11" ry="6"/></g>
<g fill="none" stroke="{muted}" stroke-width="2" opacity=".32" transform="rotate(-12 176 92)">
<path d="M75 38L276 56L265 164L67 135Z"/></g>
<g stroke="{ink}" stroke-width="3" fill="{surface}">
<rect x="73" y="45" width="206" height="130" rx="9"/>
<rect x="91" y="64" width="170" height="69" rx="5" fill="{canvas}" stroke-width="1"/>
<circle cx="124" cy="104" r="16"/><circle cx="228" cy="104" r="16"/>
<rect x="153" y="91" width="46" height="27" rx="2"/>
<path d="M118 154H234M94 155H99M253 155H258" stroke-width="2"/>
</g><g stroke="{accent}" stroke-width="2" fill="none">
<path d="M69 30H52V47M286 184H301V169M484 43H500V59M326 158H310V142"/>
</g></svg>'''.format(**colors)
tree=ET.fromstring(svg)
def inherit(element, attributes):
    values={**attributes,**{k:v for k,v in element.attrib.items() if k in {'fill','stroke','stroke-width'}}}
    if element.tag.rsplit('}',1)[-1] not in {'g','svg'}:
        for key,value in values.items():element.set(key,value)
    for child in element:inherit(child,values)
inherit(tree,{})
ET.register_namespace('', 'http://www.w3.org/2000/svg')
source=ROOT/'assets/alignment.svg';source.write_text(ET.tostring(tree,encoding='unicode'))
subprocess.run(['rsvg-convert','--output',str(ROOT/'discstraight/manual/images/alignment.png'),str(source)],check=True)
