# -*- coding: utf-8 -*-
"""Merge translation parts into the manifest and pre-validate structure + tokens + numbers."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r'C:\Users\AGICO\.zcode\skills\office-translate-pro\formats\word\scripts')
from analyze_docx import PROTECTED_TOKEN

JOBS = Path(r'E:\office-translate-pro\jobs\waste-5t-en')
MANIFEST = JOBS / 'translation-manifest.json'

m = json.load(open(MANIFEST, encoding='utf-8'))
units = m['units']

translations = {}
for i in range(1, 6):
    ns = {}
    exec(open(JOBS / f'part{i}.py', encoding='utf-8').read(), ns)
    for k, v in ns['PART'].items():
        if k in translations:
            raise SystemExit(f'duplicate id {k} in part{i}')
        translations[k] = v

missing = [u['id'] for u in units if u['id'] not in translations]
print('coverage:', len(translations), '/', len(units))
if missing:
    raise SystemExit(f'MISSING ids: {missing}')


def seps(s):
    return re.split(r'(\t|\n)', s)[1::2]


struct_errors = []
for u in units:
    t = translations[u['id']]
    if not t.strip():
        struct_errors.append((u['id'], 'empty target'))
        continue
    if seps(t) != seps(u['source']):
        struct_errors.append((u['id'], f'separator mismatch src={seps(u["source"])} tgt={seps(t)} src={u["source"]!r} tgt={t!r}'))
print('structure errors:', len(struct_errors))
for e in struct_errors[:10]:
    print(' -', e)

# numeric fidelity: every number in the source must appear in the target
# Exception: 万元 (×10,000 yuan) is legitimately converted to million/10,000 RMB.
UNIT_CONVERTED = {48, 296, 414}
num = re.compile(r'\d+(?:[.,]\d+)?')
num_issues = []
for u in units:
    if u['id'] in UNIT_CONVERTED:
        continue
    t = translations[u['id']]
    src_nums, tgt_nums = num.findall(u['source']), num.findall(t)
    missing_nums = [n for n in src_nums if n not in tgt_nums]
    if missing_nums:
        num_issues.append((u['id'], u['source'][:60], missing_nums))
print('numeric fidelity issues:', len(num_issues))
for e in num_issues[:20]:
    print(' -', e)

# token parity (mirrors validate)
def norm_tokens(text):
    return {re.sub(r'\s+', '', tok).replace('℃', '°C').replace(',', '.').casefold()
            for tok in PROTECTED_TOKEN.findall(text)}

token_issues = []
for u in units:
    st, tt = norm_tokens(u['source']), norm_tokens(translations[u['id']])
    if st != tt:
        token_issues.append((u['id'], u['source'][:60], sorted(st - tt), sorted(tt - st)))
print('token parity issues:', len(token_issues))
for e in token_issues[:20]:
    print(' -', e)

if struct_errors or num_issues:
    raise SystemExit('fix errors above before merging')

for u in units:
    u['target'] = translations[u['id']]
MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
print('manifest updated with targets.')
