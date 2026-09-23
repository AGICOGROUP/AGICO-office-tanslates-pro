"""Replace GPT-localized main-story Word images while preserving their geometry.

Main-story pictures reach the package through one of two OOXML hosts:

* ``<wp:inline>`` — a Word inline shape, addressed by ``InlineShapes`` index and
  replaced through Word automation.
* ``<wp:anchor>`` — a floating drawing, which never appears in ``InlineShapes``
  and therefore cannot be addressed that way.

Because a localized replacement is normalised to the source image's exact aspect
ratio (see ``normalize_generated_image``), the anchor's recorded extent stays
correct and the drawing geometry is preserved if the media part itself is
swapped. Anchored pictures are therefore replaced by rewriting the referenced
media part bytes, while the package's other parts, relationships, extents and
anchoring are left untouched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from posixpath import normpath
import re
import subprocess
import tempfile
from zipfile import ZipFile

from translation_core import file_hash

MAIN_DOCUMENT_PART = 'word/document.xml'
MAIN_RELATIONSHIPS_PART = 'word/_rels/document.xml.rels'
DRAWING_HOST = re.compile(r'<wp:(inline|anchor)\b.*?</wp:\1>', re.DOTALL)
RELATIONSHIP = re.compile(r'<Relationship\b[^>]*/?>')
_ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')


def _media_index(group):
    paths = group.get('media_paths', [])
    match = re.search(r'/image(\d+)\.', paths[0] if paths else '')
    if not match:
        raise RuntimeError(f"Cannot resolve Word image order for {group.get('id')}")
    return int(match.group(1))


def _attributes(tag):
    return dict(_ATTRIBUTE.findall(tag))


def _part_relationships(archive):
    """Map relationship id -> package part name for the main document story."""
    try:
        rels = archive.read(MAIN_RELATIONSHIPS_PART).decode('utf-8')
    except KeyError:
        return {}
    targets = {}
    for tag in RELATIONSHIP.findall(rels):
        values = _attributes(tag)
        identifier, target = values.get('Id'), values.get('Target')
        if not identifier or not target or values.get('TargetMode') == 'External':
            continue
        targets[identifier] = normpath(target[1:] if target.startswith('/') else f'word/{target}')
    return targets


def _drawing_host(archive, part_name):
    """Return the OOXML host tag ('inline' or 'anchor') owning a media part."""
    relationships = _part_relationships(archive)
    identifiers = [rid for rid, target in relationships.items() if target == part_name]
    if not identifiers:
        return None
    document = archive.read(MAIN_DOCUMENT_PART).decode('utf-8')
    for host, body in ((match.group(1), match.group(0)) for match in DRAWING_HOST.finditer(document)):
        if any(f'r:embed="{rid}"' in body or f'r:link="{rid}"' in body for rid in identifiers):
            return host
    return None


def _replace_media_parts(output, plan):
    """Swap the media part bytes of anchored pictures, verifying the result."""
    output = Path(output).resolve()
    targets = {}
    for item in plan:
        replacement = Path(item['replacement_path'])
        for part in item['media_parts']:
            if part in targets:
                raise RuntimeError(f"Duplicate localized media part: {part}")
            targets[part] = replacement
    for part, replacement in targets.items():
        if part.lower().endswith('.emf') or part.lower().endswith('.wmf'):
            raise RuntimeError(f"Anchored vector media needs a rendered edit target: {part}")
        if Path(part).suffix.lower() != replacement.suffix.lower():
            raise RuntimeError(f"Replacement format differs from {part}; update content types first")

    with ZipFile(output) as archive:
        entries = archive.infolist()
        names = {entry.filename for entry in entries}
        missing = [part for part in targets if part not in names]
        if missing:
            raise RuntimeError(f"Localized media parts are absent from the package: {missing}")
        before = {entry.filename: archive.read(entry.filename) for entry in entries}

    replacement_bytes = {part: replacement.read_bytes() for part, replacement in targets.items()}
    for part, payload in replacement_bytes.items():
        if file_hash(targets[part]) != file_hash_from_bytes(payload):
            raise RuntimeError(f"Replacement bytes changed while reading: {part}")

    temporary = output.with_name(f".{output.name}.images.tmp")
    try:
        with ZipFile(output) as source, ZipFile(temporary, 'w') as target:
            for entry in source.infolist():
                payload = replacement_bytes.get(entry.filename)
                if payload is None:
                    payload = source.read(entry.filename)
                target.writestr(entry, payload)
        with ZipFile(temporary) as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"Word package is invalid after image replacement: {bad}")
            for entry in archive.infolist():
                payload = archive.read(entry.filename)
                if entry.filename in replacement_bytes:
                    if payload != replacement_bytes[entry.filename]:
                        raise RuntimeError(f"Replacement bytes were not stored: {entry.filename}")
                elif payload != before[entry.filename]:
                    raise RuntimeError(f"Untouched part changed: {entry.filename}")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'replaced': len(targets), 'method': 'anchored-media-part',
            'parts': sorted(targets), 'output_sha256': file_hash(output)}


def file_hash_from_bytes(payload):
    import hashlib
    return hashlib.sha256(payload).hexdigest()


def _run_word_replacements(output, plan):
    plan = sorted(plan, key=lambda item: item['index'], reverse=True)
    script = Path(__file__).with_suffix('.ps1')
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as stream:
        json.dump(plan, stream, ensure_ascii=False)
        plan_path = Path(stream.name)
    try:
        run = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                              '-DocumentPath', str(Path(output).resolve()), '-PlanPath', str(plan_path)],
                             text=True, encoding='utf-8', capture_output=True, timeout=60)
        if run.returncode:
            raise RuntimeError(run.stderr.strip() or run.stdout.strip())
    finally:
        plan_path.unlink(missing_ok=True)
    with ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Word package is invalid after image replacement: {bad}")
    return {'replaced': len(plan), 'method': 'word-automation', 'output_sha256': file_hash(output)}


def apply_word_image_replacements(output, manifest):
    groups = [g for g in manifest.get('image_reviews', []) if g.get('status') == 'localized']
    if not groups:
        return {'replaced': 0}
    with ZipFile(output) as archive:
        hosts = {}
        for group in groups:
            replacement = Path(group['replacement_path']).resolve()
            if not replacement.is_file() or file_hash(replacement) != group.get('replacement_sha256'):
                raise RuntimeError(f"Localized image changed or is missing: {group['id']}")
            media_parts = list(group.get('media_paths') or [])
            if not media_parts:
                raise RuntimeError(f"Localized image has no package part: {group['id']}")
            for part in media_parts:
                hosts.setdefault(_drawing_host(archive, part), []).append((group, part))

    unknown = hosts.pop(None, [])
    if unknown:
        raise RuntimeError(f"Localized main-story images are absent from the document part: "
                           f"{[group['id'] for group, _ in unknown]}")

    results = []
    inline = hosts.pop('inline', [])
    if inline:
        results.append(_run_word_replacements(output, [
            {'id': group['id'], 'story_type': 1, 'kind': 'inline',
             'index': _media_index(group), 'replacement_path': str(Path(group['replacement_path']).resolve())}
            for group, _ in inline]))
    anchored = hosts.pop('anchor', [])
    if anchored:
        grouped = {}
        for group, part in anchored:
            grouped.setdefault(group['id'], {'replacement_path': str(Path(group['replacement_path']).resolve()),
                                             'media_parts': []})
            grouped[group['id']]['media_parts'].append(part)
        results.append(_replace_media_parts(output, list(grouped.values())))

    if len(results) == 1:
        return results[0]
    return {'replaced': sum(result['replaced'] for result in results),
            'methods': [result.get('method') for result in results],
            'output_sha256': file_hash(output)}
