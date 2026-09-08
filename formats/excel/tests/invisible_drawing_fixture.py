"""Build and inspect real OOXML placeholders for the pipeline regression test."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
import sys
import xml.etree.ElementTree as ET

A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
X = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
C = 'http://schemas.openxmlformats.org/package/2006/content-types'


def inject(path):
    with ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    sheet = ET.fromstring(parts['xl/worksheets/sheet1.xml'])
    ET.SubElement(sheet, f'{{{S}}}drawing', {f'{{{R}}}id': 'rIdPlaceholder'})
    parts['xl/worksheets/sheet1.xml'] = ET.tostring(sheet)
    relpath = 'xl/worksheets/_rels/sheet1.xml.rels'
    rels = ET.fromstring(parts[relpath]) if relpath in parts else ET.Element(f'{{{P}}}Relationships')
    ET.SubElement(rels, f'{{{P}}}Relationship', {'Id': 'rIdPlaceholder', 'Type': R + '/drawing', 'Target': '../drawings/drawing1.xml'})
    ET.register_namespace('', P)
    parts[relpath] = ET.tostring(rels, encoding='utf-8', xml_declaration=True)
    types = ET.fromstring(parts['[Content_Types].xml'])
    ET.SubElement(types, f'{{{C}}}Override', {'PartName': '/xl/drawings/drawing1.xml', 'ContentType': 'application/vnd.openxmlformats-officedocument.drawing+xml'})
    ET.register_namespace('', C)
    parts['[Content_Types].xml'] = ET.tostring(types, encoding='utf-8', xml_declaration=True)
    root = ET.Element(f'{{{X}}}wsDr')
    for index in range(1510):
        anchor = ET.SubElement(root, f'{{{X}}}twoCellAnchor')
        for tag, col, row in [('from', 0, 0), ('to', 2, 2)]:
            marker = ET.SubElement(anchor, f'{{{X}}}{tag}')
            for key, value in [('col', col), ('colOff', 0), ('row', row), ('rowOff', 0)]:
                ET.SubElement(marker, f'{{{X}}}{key}').text = str(value)
        shape = ET.SubElement(anchor, f'{{{X}}}sp')
        nv = ET.SubElement(shape, f'{{{X}}}nvSpPr')
        ET.SubElement(nv, f'{{{X}}}cNvPr', {'id': str(index + 1), 'name': f'Rectangle {index + 1}'})
        ET.SubElement(nv, f'{{{X}}}cNvSpPr')
        props = ET.SubElement(shape, f'{{{X}}}spPr')
        transform = ET.SubElement(props, f'{{{A}}}xfrm')
        ET.SubElement(transform, f'{{{A}}}off', {'x': '0', 'y': '0'})
        ET.SubElement(transform, f'{{{A}}}ext', {'cx': '1270000', 'cy': '1270000'})
        ET.SubElement(ET.SubElement(props, f'{{{A}}}prstGeom', {'prst': 'rect'}), f'{{{A}}}avLst')
        ET.SubElement(props, f'{{{A}}}noFill')
        ET.SubElement(ET.SubElement(props, f'{{{A}}}ln'), f'{{{A}}}noFill')
        # Excel's real XLS conversion retains inactive paint in Office extensions.
        extensions = ET.SubElement(props, f'{{{A}}}extLst')
        for uri, tag, color in [
            ('{909E8E84-426E-40DD-AFC4-6F175D3DCCD1}', 'hiddenFill', 'FFFFFF'),
            ('{91240B29-F687-4F45-9708-019B960494DF}', 'hiddenLine', '000000'),
        ]:
            extension = ET.SubElement(extensions, f'{{{A}}}ext', {'uri': uri})
            cache = ET.SubElement(extension, '{http://schemas.microsoft.com/office/drawing/2010/main}' + tag)
            ET.SubElement(ET.SubElement(cache, f'{{{A}}}solidFill'), f'{{{A}}}srgbClr', {'val': color})
        creation = ET.SubElement(ET.SubElement(nv[0], f'{{{A}}}extLst'), f'{{{A}}}ext',
                                {'uri': '{FF2B5EF4-FFF2-40B4-BE49-F238E27FC236}'})
        ET.SubElement(creation, '{http://schemas.microsoft.com/office/drawing/2014/main}creationId',
                      {'id': '{67C1D920-E81E-47D8-9439-A30F810D16A0}'})
        ET.SubElement(anchor, f'{{{X}}}clientData')
    parts['xl/drawings/drawing1.xml'] = ET.tostring(root)
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)


def snapshot(path):
    result = []
    with ZipFile(path) as z:
        for name in z.namelist():
            if not name.startswith('xl/drawings/') or not name.endswith('.xml'):
                continue
            for anchor in ET.fromstring(z.read(name)):
                shape = anchor.find(f'{{{X}}}sp')
                if shape is None:
                    continue
                props = shape.find(f'{{{X}}}spPr')
                result.append({
                    'name': shape.find(f'{{{X}}}nvSpPr/{{{X}}}cNvPr').get('name'),
                    'from': [n.text for n in anchor.find(f'{{{X}}}from')],
                    'to': [n.text for n in anchor.find(f'{{{X}}}to')],
                    'extent': props.find(f'{{{A}}}xfrm/{{{A}}}ext').attrib,
                    'no_fill': props.find(f'{{{A}}}noFill') is not None,
                    'no_line': props.find(f'{{{A}}}ln/{{{A}}}noFill') is not None,
                })
    print(json.dumps(result))


if __name__ == '__main__':
    (inject if sys.argv[1] == 'inject' else snapshot)(Path(sys.argv[2]))
