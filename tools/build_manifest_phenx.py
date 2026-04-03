#!/usr/bin/env python3
"""Build website/manifest_phenx.json from scales/phenx/ OSD files.

Scans scales/phenx/ for .osd bundles and extracts metadata for the website.
Reads scales/phenx/EXCLUDE.csv to skip scales that should not be published
(e.g., requires images, clinician-administered, no items).

The EXCLUDE.csv file is the single source of truth for which PhenX scales
are visible on the website. The .osd files remain in the repository regardless.

Usage:
    python3 tools/build_manifest_phenx.py
"""
import csv, json, os
from pathlib import Path

REPO_ROOT   = Path(__file__).parent.parent
PHENX_DIR   = REPO_ROOT / 'scales' / 'phenx'
EXCLUDE_CSV = PHENX_DIR / 'EXCLUDE.csv'
OUTPUT      = REPO_ROOT / 'website' / 'manifest_phenx.json'

# Also check for hardlinked copy in OpenScales_web
OUTPUT_WEB  = REPO_ROOT.parent / 'OpenScales_web' / 'manifest_phenx.json'

# Load exclusion list
excluded = {}  # code -> reason
if EXCLUDE_CSV.exists():
    with open(EXCLUDE_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            code = row.get('code', '').strip()
            reason = row.get('reason', '').strip()
            if code:
                excluded[code.upper()] = reason

entries = []
skipped = 0

for scale_dir in sorted(PHENX_DIR.iterdir()):
    if not scale_dir.is_dir():
        continue

    code = scale_dir.name

    # Check exclusion list
    if code.upper() in excluded:
        skipped += 1
        continue

    # Find .osd file
    osd_path = scale_dir / f'{code}.osd'
    if not osd_path.exists():
        continue

    try:
        bundle = json.loads(osd_path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f"  WARNING: Cannot parse {osd_path}: {exc}")
        continue

    # Handle both bundle format (definition wrapper) and flat format
    if 'definition' in bundle:
        definition = bundle['definition']
    else:
        definition = bundle

    info = definition.get('scale_info', {})
    items = [i for i in definition.get('items', [])
             if i.get('type') not in ('inst', 'section', 'image')]
    dims = definition.get('dimensions', [])
    scoring = definition.get('scoring', {})

    # Get languages from translations
    translations = bundle.get('translations', {})
    if translations:
        langs = sorted(translations.keys())
    else:
        # Check for separate translation files
        langs = sorted(set(
            p.stem.split('.')[-1]
            for p in scale_dir.iterdir()
            if p.suffix == '.json' and '.' in p.stem
            and p.stem.startswith(f'{code}.')
        ))
    if not langs:
        langs = ['en']

    entry = {
        'code':         info.get('code', code),
        'name':         info.get('name', code),
        'abbreviation': info.get('abbreviation', ''),
        'description':  info.get('description', ''),
        'citation':     info.get('citation', ''),
        'license':      info.get('license', 'PhenX Toolkit freely available protocol'),
        'version':      info.get('version', '1.0'),
        'url':          info.get('url', ''),
        'domain':       info.get('domain', 'Health'),
        'n_items':      len(items),
        'dimensions':   [{'id': d.get('id'), 'name': d.get('name')} for d in dims],
        'has_scoring':  bool(scoring),
        'languages':    langs,
        'repo':         'phenx',
    }
    entries.append(entry)

entries.sort(key=lambda e: e['name'].lower())

# Write manifest
OUTPUT.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')

# Copy to web directory if it exists and is not the same file
if OUTPUT_WEB.exists() and not os.path.samefile(OUTPUT, OUTPUT_WEB):
    OUTPUT_WEB.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Also copied to {OUTPUT_WEB}")

# Summary
domains = sorted(set(e['domain'] for e in entries))
langs_all = sorted(set(l for e in entries for l in e['languages']))

print(f"\nWrote {OUTPUT}")
print(f"  Scales found   : {len(entries)}")
print(f"  Excluded        : {skipped} (from EXCLUDE.csv)")
print(f"  Domains covered: {len(domains)}  ({', '.join(domains)})")
print(f"  Languages found: {len(langs_all)}  ({', '.join(langs_all[:15])}{'...' if len(langs_all) > 15 else ''})")
print()
for e in entries:
    lang_str = ', '.join(e['languages'])
    print(f"  [{e['domain']:20s}]  {e['code']:12s} {e['name']}  ({e['n_items']} items) [{lang_str}]")

if excluded:
    print(f"\n  Excluded protocols ({len(excluded)}):")
    for code, reason in sorted(excluded.items()):
        print(f"    {code}: {reason}")
