"""Format-neutral pending work and atomic translation result merging.

Called by the selected adapter, never a router or a replacement delivery gate.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def fields(kind):
    if kind == 'word': return 'units', 'source', 'target'
    if kind == 'ppt': return 'translation_units', 'source_text', 'translation'
    if kind == 'excel': return 'translation_units', 'source', 'translation'
    raise ValueError(f'unknown adapter: {kind}')


def identity(data, kind):
    key, _, _ = fields(kind)
    mutable = {'target', 'translation', 'status', 'reason'}
    source = [{k: v for k, v in unit.items() if k not in mutable} for unit in data[key]]
    payload = [kind, data.get('source_sha256'), data.get('target_language'), data.get('output_mode'), source]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def pending(unit, kind):
    _, _, target = fields(kind)
    return not unit.get(target, '').strip() or (kind == 'excel' and unit.get('status') == 'pending')


def compact_item(unit, kind):
    _, source, _ = fields(kind)
    item = {'id': unit['id'], 'source': unit[source]}
    for key in ('role', 'context_signature', 'context_key', 'protected_tokens', 'context'):
        if unit.get(key): item[key] = unit[key]
    return item


def export_batches(path, *, kind, max_items=80, max_chars=12000, ids=None, index_name='translation-batches.json'):
    """Export only pending work (or explicit IDs for a local correction).

    The index contains paths/counts, not repeated source or translation data.
    A paragraph is never split; size limits are soft for a single long unit.
    """
    if max_items < 1 or max_chars < 1: raise ValueError('batch limits must be positive')
    path = Path(path)
    data = read_json(path)
    key, source, target = fields(kind)
    units = data[key]
    job_id = identity(data, kind)
    selected = None if ids is None else set(ids)
    if selected is not None and not selected <= {str(u['id']) for u in units}:
        raise ValueError('unknown retry ID')
    indexed = [(i, u) for i, u in enumerate(units)
               if (str(u['id']) in selected if selected is not None else pending(u, kind))]
    groups, group, size = [], [], 0
    for pair in indexed:
        length = len(pair[1][source])
        if group and (len(group) >= max_items or size + length > max_chars or pair[0] != group[-1][0] + 1):
            groups.append(group); group, size = [], 0
        group.append(pair); size += length
    if group: groups.append(group)
    index = {'schema_version': 1, 'job_id': job_id, 'target_language': data.get('target_language'),
             'pending_count': sum(pending(u, kind) for u in units), 'selected_count': len(indexed), 'batches': []}
    for group in groups:
        digest = hashlib.sha256(json.dumps([job_id, [u['id'] for _, u in group]]).encode()).hexdigest()[:16]
        relative = f'batches/{digest}.json'
        items = [compact_item(u, kind) for _, u in group]
        for item, (_, unit) in zip(items, group):
            if unit.get(target): item['previous_translation'] = unit[target]
        first, last = group[0][0], group[-1][0]
        batch = {'schema_version': 1, 'job_id': job_id, 'target_language': data.get('target_language'),
                 'context_before': units[first-1][source] if first else '',
                 'context_after': units[last+1][source] if last+1 < len(units) else '', 'items': items}
        if first and units[first-1].get(target):
            batch['context_before_translation'] = units[first-1][target]
        write_json(path.parent / relative, batch)
        index['batches'].append({'file': relative, 'count': len(items)})
    # Image work is explicitly exposed, never silently treated as completed.
    image_key = 'image_groups' if kind == 'ppt' else 'images'
    if data.get(image_key):
        image_path = path.parent / 'image-worklist.json'
        write_json(image_path, {image_key: data[image_key], 'overlays': data.get('overlays', [])})
        index['image_worklist'] = image_path.name
    write_json(path.parent / index_name, index)
    if kind != 'excel' and index_name == 'translation-batches.json':
        write_json(path.parent / 'translation-worklist.json', index)
    return index


def merge_results(path, response_path, *, kind, check=None, before_save=None):
    """Persist valid items, report invalid items, and never silently replace work."""
    path = Path(path)
    data, response = read_json(path), read_json(response_path)
    job_id = identity(data, kind)
    if not isinstance(response, dict) or response.get('job_id') != job_id:
        raise ValueError('response belongs to a different source/configuration; regenerate batches')
    decisions = response.get('translations')
    if not isinstance(decisions, list) or not decisions:
        raise ValueError('translations must be a non-empty array')
    key, source, target = fields(kind)
    units = {u['id']: u for u in data[key]}
    seen = set()
    for decision in decisions:
        if not isinstance(decision, dict): raise ValueError('translation decision must be an object')
        uid = decision.get('id')
        if not isinstance(uid, (str, int)) or isinstance(uid, bool) or uid not in units or uid in seen:
            raise ValueError(f'unknown or duplicate response ID: {uid}')
        seen.add(uid)
    result = deepcopy(data)
    updated = {u['id']: u for u in result[key]}
    accepted, errors = [], []
    for decision in decisions:
        uid, text = decision['id'], decision.get('translation')
        unit = units[uid]
        problems = []
        current = unit.get(target, '')
        if not isinstance(text, str) or not text.strip():
            problems.append('translation must be non-empty text')
        elif current and current != text and decision.get('previous_translation') != current:
            problems.append('completed translation conflict; supply matching previous_translation to correct it')
        else:
            if kind == 'word':
                separators = re.findall(r'\t|\n', unit[source])
                if separators != re.findall(r'\t|\n', text):
                    problems.append('tab/newline sequence changed')
            else:
                for token in unit.get('protected_tokens', []):
                    if token not in text: problems.append(f'protected token missing: {token}')
            if check: problems.extend(check(unit, text))
            if kind == 'excel' and text == unit[source]:
                reason = decision.get('reason', unit.get('reason', ''))
                if not isinstance(reason, str) or not reason.strip():
                    problems.append('unchanged source requires retain reason')
        if problems:
            errors.append({'id': uid, 'source': unit[source], 'translation': text, 'errors': problems})
            continue
        updated[uid][target] = text
        if kind == 'excel':
            updated[uid]['status'] = 'retain' if text == unit[source] else 'translated'
            if updated[uid]['status'] == 'retain':
                updated[uid]['reason'] = decision.get('reason', unit.get('reason', ''))
        accepted.append(uid)
    if 'pending_count' in result:
        result['pending_count'] = sum(pending(u, kind) for u in result[key])
    if accepted:
        if before_save: before_save(accepted)
        write_json(path, result)
    report = {'job_id': job_id, 'accepted_ids': accepted, 'errors': errors,
              'pending_count': sum(pending(u, kind) for u in result[key])}
    export_batches(path, kind=kind)
    if errors:
        report['retry_index'] = 'translation-retry.json'
        export_batches(path, kind=kind, ids=[str(e['id']) for e in errors], index_name=report['retry_index'])
    write_json(path.parent / 'translation-merge-report.json', report)
    return report


def add_commands(subparsers):
    batches = subparsers.add_parser('batches', help='export pending translation batches without repeating prepare')
    batches.add_argument('--job-dir', required=True, type=Path)
    batches.add_argument('--max-items', type=int, default=80)
    batches.add_argument('--max-chars', type=int, default=12000)
    batches.add_argument('--ids', nargs='+', help='explicit IDs for local correction, including completed items')
    merge = subparsers.add_parser('merge', help='merge compact translation results; final delivery checks remain required')
    merge.add_argument('--job-dir', required=True, type=Path)
    merge.add_argument('--responses', required=True, type=Path)


def run_command(args, *, kind, filename='translation-manifest.json', check=None, before_save=None):
    path = args.job_dir / filename
    if args.command == 'batches':
        report = export_batches(path, kind=kind, max_items=args.max_items, max_chars=args.max_chars, ids=args.ids)
    else:
        report = merge_results(path, args.responses, kind=kind, check=check, before_save=before_save)
    print(json.dumps(report, ensure_ascii=False))
    return 2 if report.get('errors') else 0
