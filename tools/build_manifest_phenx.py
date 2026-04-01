#!/usr/bin/env python3
"""Build website/manifest_phenx.json from PhenX OSD output.

Scans data/phenx_448/osd_output/ and extracts metadata for the website.
Also reads phenx_protocols.csv for scoring/branching flags.

Usage:
    python3 tools/build_manifest_phenx.py
"""
import csv, json, os
from pathlib import Path

REPO_ROOT  = Path(__file__).parent.parent
OSD_DIR    = REPO_ROOT / 'data' / 'phenx_448' / 'osd_output'
CSV_PATH   = REPO_ROOT / 'data' / 'phenx_448' / 'phenx_protocols.csv'
OUTPUT     = REPO_ROOT / 'website' / 'manifest_phenx.json'

# Load phenx_protocols.csv for scoring/branching/exclude flags.
# Exclude any protocol that:
#   - has a non-empty Exclude field (manually flagged), OR
#   - needs manual scoring review (Scoring == 'needs_manual'), OR
#   - has unresolved branching logic (Branching == 'needs_review')
flags = {}
excluded_pids = {}   # pid -> reason string
if CSV_PATH.exists():
    with open(CSV_PATH, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            pid = row['ProtocolID']
            reason = row.get('Exclude', '').strip()
            scoring   = row.get('Scoring', '').strip()
            branching = row.get('Branching', '').strip()
            if reason:
                excluded_pids[pid] = reason
            elif scoring == 'needs_manual':
                excluded_pids[pid] = 'needs_manual_scoring'
            elif branching == 'needs_review':
                excluded_pids[pid] = 'needs_branching_review'
            else:
                flags[pid] = {
                    'scoring':   scoring,
                    'branching': branching,
                }

entries = []
for pid_dir in sorted(OSD_DIR.iterdir()):
    if not pid_dir.is_dir():
        continue
    pid = pid_dir.name
    if pid in excluded_pids:
        continue   # needs_manual_scoring, needs_branching_review, or manually excluded
    json_path = pid_dir / f'PX{pid}.json'
    if not json_path.exists():
        continue
    try:
        d = json.loads(json_path.read_text(encoding='utf-8'))
    except Exception:
        continue

    info = d.get('scale_info', {})
    items = [i for i in d.get('items', []) if i.get('type') not in ('inst', 'section')]
    dims  = d.get('dimensions', [])
    scoring = d.get('scoring', {})

    # Language files
    langs = sorted(set(
        p.stem.split('.')[-1]
        for p in pid_dir.iterdir()
        if p.suffix == '.json' and '.' in p.stem and p.stem != f'PX{pid}'
        and p.stem.startswith(f'PX{pid}.')
    ))
    if not langs:
        langs = ['en']

    f = flags.get(pid, {})
    entry = {
        'code':          f'PX{pid}',
        'name':          info.get('name', f'PhenX Protocol {pid}'),
        'abbreviation':  info.get('abbreviation', f'PX{pid}'),
        'description':   info.get('description', ''),
        'citation':      info.get('citation', ''),
        'license':       info.get('license', 'PhenX Toolkit freely available protocol'),
        'version':       info.get('version', '1.0'),
        'url':           info.get('url', ''),
        'domain':        info.get('domain', 'Other'),
        'items_count':   len(items),
        'dimensions':    [{'id': d2.get('id'), 'name': d2.get('name')} for d2 in dims],
        'has_scoring':   bool(scoring),
        'scoring_flag':  f.get('scoring', ''),
        'branching_flag':f.get('branching', ''),
        'languages':     langs,
        'has_screenshot':False,
        'repo':          'phenx',
    }
    entries.append(entry)

entries.sort(key=lambda e: e['name'].lower())
OUTPUT.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"Written {len(entries)} entries to {OUTPUT}")
if excluded_pids:
    from collections import Counter
    reasons = Counter(excluded_pids.values())
    print(f"Excluded {len(excluded_pids)} protocol(s): {dict(reasons)}")
