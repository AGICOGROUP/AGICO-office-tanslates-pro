"""Replace GPT-localized main-story Word images while preserving their geometry."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile

from translation_core import file_hash


def _media_index(group):
    paths = group.get('media_paths', [])
    match = re.search(r'/image(\d+)\.', paths[0] if paths else '')
    if not match:
        raise RuntimeError(f"Cannot resolve Word image order for {group.get('id')}")
    return int(match.group(1))


def apply_word_image_replacements(output, manifest):
    groups = [g for g in manifest.get('image_reviews', []) if g.get('status') == 'localized']
    if not groups:
        return {'replaced': 0}
    plan = []
    for group in groups:
        replacement = Path(group['replacement_path']).resolve()
        if not replacement.is_file() or file_hash(replacement) != group.get('replacement_sha256'):
            raise RuntimeError(f"Localized image changed or is missing: {group['id']}")
        plan.append({'id': group['id'], 'story_type': 1, 'kind': 'inline',
                     'index': _media_index(group), 'replacement_path': str(replacement)})
    plan.sort(key=lambda item: item['index'], reverse=True)
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
    return {'replaced': len(plan), 'output_sha256': file_hash(output)}
