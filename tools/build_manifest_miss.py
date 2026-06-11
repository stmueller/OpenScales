#!/usr/bin/env python3
"""Build website/manifest_miss.json from scales/miss/ OSD files.

Scans scales/miss/ for directories named MISS{article_id} (e.g. MISS11061).
Each directory should contain {dir_name}.osd (e.g. MISS11061/MISS11061.osd).

The manifest includes journal_id, doi, and journal_url fields so the
MISS journal website can link directly to each scale file on GitHub.

Directory/file naming convention:
    scales/miss/MISS{article_id}/MISS{article_id}.osd

DOI pattern: 10.5964/miss.{article_id}

Reads scales/miss/EXCLUDE.csv to skip scales (use numeric article IDs as codes).

Usage:
    python3 tools/build_manifest_miss.py
"""
import csv, json, os, re
from pathlib import Path

REPO_ROOT   = Path(__file__).parent.parent
MISS_DIR    = REPO_ROOT / 'scales' / 'miss'
EXCLUDE_CSV = MISS_DIR / 'EXCLUDE.csv'
OUTPUT      = REPO_ROOT / 'website' / 'manifest_miss.json'

JOURNAL_BASE = 'https://miss.psychopen.eu/index.php/miss/article/view/'
DOI_PREFIX   = '10.5964/miss.'

# Also check for hardlinked/copy in OpenScales_web
OUTPUT_WEB   = REPO_ROOT.parent / 'OpenScales_web' / 'manifest_miss.json'

# Load exclusion list
excluded = {}  # article_id -> reason
if EXCLUDE_CSV.exists():
    with open(EXCLUDE_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            code = row.get('code', '').strip()
            reason = row.get('reason', '').strip()
            if code:
                excluded[code] = reason

entries = []
skipped = 0

for scale_dir in sorted(MISS_DIR.iterdir()):
    if not scale_dir.is_dir():
        continue

    article_id = scale_dir.name

    # Only process MISS####-named directories
    if not re.fullmatch(r'MISS\d+', article_id):
        continue

    numeric_id = article_id[4:]  # strip 'MISS' prefix for DOI/URL/exclusion lookup
    if numeric_id in excluded:
        skipped += 1
        continue

    osd_path = scale_dir / f'{article_id}.osd'
    if not osd_path.exists():
        print(f"  WARNING: Missing OSD file in {scale_dir} — expected {osd_path.name}")
        continue

    try:
        bundle = json.loads(osd_path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f"  WARNING: Cannot parse {osd_path}: {exc}")
        continue

    definition = bundle.get('definition', bundle)
    info = definition.get('scale_info', {})

    items = [i for i in definition.get('items', [])
             if i.get('type') not in ('inst', 'section', 'image')]
    dims = definition.get('dimensions', [])
    scoring = definition.get('scoring', {})

    translations = bundle.get('translations', {})
    if translations:
        langs = sorted(translations.keys())
    else:
        langs = sorted(set(
            p.stem.split('.')[-1]
            for p in scale_dir.iterdir()
            if p.suffix == '.json' and '.' in p.stem
        ))
    if not langs:
        langs = ['en']

    journal_url = JOURNAL_BASE + numeric_id
    doi = DOI_PREFIX + numeric_id

    entry = {
        'journal_id':   numeric_id,
        'doi':          doi,
        'journal_url':  journal_url,
        'code':         info.get('code', numeric_id),
        'name':         info.get('name', article_id),
        'abbreviation': info.get('abbreviation', ''),
        'description':  info.get('description', ''),
        'citation':     info.get('citation', ''),
        'license':      info.get('license', 'CC BY 4.0'),
        'domain':       info.get('domain', ''),
        'items_count':  len(items),
        'dimensions':   [{'id': d.get('id'), 'name': d.get('name')} for d in dims],
        'has_scoring':  bool(scoring),
        'languages':    langs,
        'repo':         'miss',
    }
    entries.append(entry)

entries.sort(key=lambda e: e['name'].lower())

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')

if OUTPUT_WEB.parent.exists() and not (OUTPUT_WEB.exists() and os.path.samefile(OUTPUT, OUTPUT_WEB)):
    OUTPUT_WEB.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Also copied to {OUTPUT_WEB}")

print(f"\nWrote {OUTPUT}")
print(f"  Scales found : {len(entries)}")
print(f"  Excluded     : {skipped} (from EXCLUDE.csv)")
if entries:
    print()
    for e in entries:
        lang_str = ', '.join(e['languages'])
        print(f"  [{e['journal_id']:8s}]  {e['code']:16s}  {e['name']}  ({e['items_count']} items) [{lang_str}]")
        print(f"            DOI: {e['doi']}")
else:
    print("  (no scales yet — add OSD files to scales/miss/MISS{article_id}/MISS{article_id}.osd)")
