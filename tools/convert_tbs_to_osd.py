#!/usr/bin/env python3
"""Convert ARC .tbs survey files to OpenScales .osd format.

Usage:
    python3 tools/convert_tbs_to_osd.py <input.tbs> [--output <output.osd>]
    python3 tools/convert_tbs_to_osd.py --batch <tbs_dir> [--outdir <osd_dir>]

The .tbs format (used by the UW-Madison Addiction Research Center) has:
    ##I ... ##EI        Instructions block
    ##LQ ... ##EQ       Question block (item_id, text, values, labels)
    ##F                 End of file
    --- separators      Visual dividers (ignored)

Each ##LQ block contains:
    Line 1: item_id (e.g., CEOA_1)
    Line 2: item text
    Line 3: tab-separated values (e.g., 1\t2\t3\t4)
    Lines 4+: one label per line until ##EQ
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


def parse_sss(filepath):
    """Parse an .sss scoring specification file.

    Returns a list of subscale dicts:
        {'name': 'AEX_OUT', 'items': [2,7,9,...], 'reverse_items': [], 'offset': 1}
    """
    subscales = []
    current = None

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('-') or line.startswith('END'):
                if current:
                    subscales.append(current)
                    current = None
                continue

            parts = line.split('\t')
            cmd = parts[0].strip().upper()

            if cmd == 'SUMCMD':
                current = {'name': parts[1].strip() if len(parts) > 1 else '',
                          'items': [], 'reverse_items': [], 'offset': 0}
            elif cmd == 'MEASUREOFFSET' and current:
                val = parts[1].strip() if len(parts) > 1 else '0'
                try:
                    current['offset'] = int(val)
                except ValueError:
                    current['offset'] = 0
            elif cmd == 'REVERSESCORE' and current:
                if len(parts) > 1 and parts[1].strip().upper() == 'YES':
                    # Remaining parts are item numbers to reverse
                    for p in parts[2:]:
                        for num in p.split():
                            try:
                                current['reverse_items'].append(int(num))
                            except ValueError:
                                pass
            elif cmd == 'SUM' and current:
                for p in parts[1:]:
                    for num in p.split():
                        try:
                            current['items'].append(int(num))
                        except ValueError:
                            pass

    if current:
        subscales.append(current)

    return subscales


def parse_r_scoring(filepath):
    """Parse an R scoring file for varScore() calls.

    Returns a list of subscale dicts:
        {'name': 'CESD_TOT', 'forward': ['CESD_1',...], 'reverse': ['CESD_4',...], 'range': [1,4]}
    """
    subscales = []

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Match varScore calls: dS$NAME = varScore(dI, Forward= c(...), Reverse= c(...), Range = c(min,max))
    pattern = r"dS\$(\w+)\s*=\s*varScore\(dI,\s*Forward\s*=\s*c\(([^)]*)\)\s*,\s*Reverse\s*=\s*c\(([^)]*)\)\s*,\s*Range\s*=\s*c\((\d+)\s*,\s*(\d+)\)"

    for match in re.finditer(pattern, content):
        name = match.group(1)
        forward_str = match.group(2)
        reverse_str = match.group(3)
        range_min = int(match.group(4))
        range_max = int(match.group(5))

        forward = [s.strip().strip("'\"") for s in forward_str.split(',') if s.strip()]
        reverse = [s.strip().strip("'\"") for s in reverse_str.split(',') if s.strip()]

        subscales.append({
            'name': name,
            'forward': forward,
            'reverse': reverse,
            'range': [range_min, range_max]
        })

    return subscales


def find_scoring_files(tbs_path):
    """Find .sss and .R scoring files near a .tbs file."""
    tbs_dir = Path(tbs_path).parent
    # Also check parent directory
    search_dirs = [tbs_dir, tbs_dir.parent]

    sss_files = []
    r_files = []

    for d in search_dirs:
        sss_files.extend(d.glob('*.sss'))
        r_files.extend(d.glob('*.R'))

    return list(set(sss_files)), list(set(r_files))


def apply_scoring_info(osd, tbs_path, parsed_items):
    """Try to enhance OSD with scoring info from .sss or .R files."""
    sss_files, r_files = find_scoring_files(tbs_path)

    code = osd['definition']['scale_info']['code']
    item_ids = [i['id'] for i in osd['definition']['items'] if i.get('type') not in ('inst', 'section')]

    # Try .sss first
    for sss_file in sss_files:
        subscales = parse_sss(str(sss_file))
        if not subscales:
            continue

        # Build item ID prefix from parsed items
        prefix = ''
        if parsed_items:
            m = re.match(r'^([A-Za-z_]+)', parsed_items[0]['id'])
            if m:
                prefix = m.group(1).rstrip('_') + '_'

        if len(subscales) > 1 or (len(subscales) == 1 and subscales[0].get('reverse_items')):
            new_dims = []
            new_scoring = {}

            for sub in subscales:
                dim_id = sub['name'].lower()
                offset = sub['offset']

                # Map item numbers to item IDs
                sub_item_ids = []
                reverse_set = set(sub.get('reverse_items', []))
                item_coding = {}

                for num in sub['items']:
                    # Try to find the matching item ID
                    target_id = f"{prefix}{num}"
                    target_id_lower = target_id.lower()
                    matched = None
                    for iid in item_ids:
                        if iid.lower() == target_id_lower:
                            matched = iid
                            break
                    if matched:
                        sub_item_ids.append(matched)
                        item_coding[matched] = -1 if num in reverse_set else 1

                if sub_item_ids:
                    new_dims.append({
                        'id': dim_id,
                        'name': sub['name'].replace('_', ' ').title(),
                        'description': f"Items: {', '.join(str(n) for n in sub['items'])}"
                    })
                    new_scoring[dim_id] = {
                        'method': 'sum_coded',
                        'items': sub_item_ids,
                        'description': f"{sub['name']} ({len(sub_item_ids)} items)",
                        'item_coding': item_coding
                    }

            if new_dims:
                osd['definition']['dimensions'] = new_dims
                osd['definition']['scoring'] = new_scoring
                return True

    # Try .R files
    for r_file in r_files:
        subscales = parse_r_scoring(str(r_file))
        if not subscales:
            continue

        new_dims = []
        new_scoring = {}

        for sub in subscales:
            dim_id = sub['name'].lower()

            all_items = sub['forward'] + sub['reverse']
            reverse_set = set(sub['reverse'])

            sub_item_ids = []
            item_coding = {}

            for item_name in all_items:
                item_name_lower = item_name.lower()
                matched = None
                for iid in item_ids:
                    if iid.lower() == item_name_lower:
                        matched = iid
                        break
                if matched:
                    sub_item_ids.append(matched)
                    item_coding[matched] = -1 if item_name in reverse_set else 1

            if sub_item_ids:
                new_dims.append({
                    'id': dim_id,
                    'name': sub['name'].replace('_', ' ').title(),
                    'description': f"{len(sub['forward'])} forward, {len(sub['reverse'])} reverse items. Range {sub['range'][0]}-{sub['range'][1]}."
                })
                new_scoring[dim_id] = {
                    'method': 'sum_coded',
                    'items': sub_item_ids,
                    'description': f"{sub['name']} ({len(sub_item_ids)} items)",
                    'item_coding': item_coding
                }

        if new_dims:
            osd['definition']['dimensions'] = new_dims
            osd['definition']['scoring'] = new_scoring
            return True

    return False


def parse_tbs(filepath):
    """Parse a .tbs file and return structured data."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    result = {
        'instructions': '',
        'items': [],
        'filename': Path(filepath).stem,
    }

    # Extract instructions
    inst_match = re.search(r'##I\s*\n(.*?)##EI', content, re.DOTALL)
    if inst_match:
        result['instructions'] = inst_match.group(1).strip()
        # Clean up: remove leading/trailing dashes
        result['instructions'] = re.sub(r'^-+\s*', '', result['instructions'])
        result['instructions'] = re.sub(r'\s*-+$', '', result['instructions'])
        result['instructions'] = result['instructions'].strip()

    # Extract questions
    # Handle ##LQ, ##LQ6, etc. variants
    question_blocks = re.findall(r'##LQ\d*\s*\n(.*?)##EQ', content, re.DOTALL)

    for block in question_blocks:
        lines = [l.strip() for l in block.strip().split('\n') if l.strip() and not l.strip().startswith('-')]
        if len(lines) < 3:
            continue

        item_id = lines[0]
        item_text = lines[1]

        # Line 3 should be tab-separated values
        values_line = lines[2]
        values = re.split(r'\t+', values_line)

        # Try to parse as numbers
        try:
            values = [int(v.strip()) for v in values if v.strip()]
        except ValueError:
            try:
                values = [float(v.strip()) for v in values if v.strip()]
            except ValueError:
                # Values might be labels themselves
                values = list(range(1, len(values) + 1))

        # Remaining lines are labels
        labels = []
        for line in lines[3:]:
            line = line.strip()
            if line and not line.startswith('#'):
                labels.append(line)

        # If we have fewer labels than values, pad
        while len(labels) < len(values):
            labels.append('')

        result['items'].append({
            'id': item_id,
            'text': item_text,
            'values': values[:len(labels)],
            'labels': labels[:len(values)],
        })

    return result


def infer_scale_code(filename, items):
    """Infer the scale code from the filename and item IDs."""
    # Use the filename as the base code
    code = filename.upper().replace('-', '_').replace(' ', '_')

    # Try to extract a common prefix from item IDs
    if items:
        prefixes = set()
        for item in items:
            m = re.match(r'^([A-Za-z_]+)', item['id'])
            if m:
                prefixes.add(m.group(1).rstrip('_'))
        if len(prefixes) == 1:
            code = prefixes.pop().upper()

    return code


def tbs_to_osd(parsed, code=None, name=None):
    """Convert parsed .tbs data to OSD format."""
    if code is None:
        code = infer_scale_code(parsed['filename'], parsed['items'])

    if name is None:
        # Generate name from code
        name = code.replace('_', ' ').title()

    # Group items by their response scale (values + labels)
    response_groups = {}  # (values_tuple, labels_tuple) -> [item_indices]
    for i, item in enumerate(parsed['items']):
        key = (tuple(item['values']), tuple(item['labels']))
        if key not in response_groups:
            response_groups[key] = []
        response_groups[key].append(i)

    # Build translation keys
    translations = {}

    # Instruction
    if parsed['instructions']:
        translations[f'{code.lower()}_inst'] = parsed['instructions']

    # Build items and likert options
    items_def = []
    scoring_items = []

    if parsed['instructions']:
        items_def.append({
            'id': f'{code.lower()}_inst',
            'text_key': f'{code.lower()}_inst',
            'type': 'inst'
        })

    # Create shared label keys for each unique response set
    # Name them as scale_set1, scale_set2, etc. (or just scale if only one)
    response_set_keys = {}  # (values, labels) -> list of label_keys
    set_counter = 0
    for resp_key in response_groups:
        values, labels = resp_key
        set_counter += 1
        suffix = '' if len(response_groups) == 1 else f'_{set_counter}'
        label_keys = []
        for val, label in zip(values, labels):
            lk = f'{code.lower()}_r{val}{suffix}'
            translations[lk] = label
            label_keys.append(lk)
        response_set_keys[resp_key] = (label_keys, values)

    if len(response_groups) == 1:
        # All items share the same scale — use global likert_options
        resp_key = list(response_groups.keys())[0]
        label_keys, values = response_set_keys[resp_key]

        likert_options = {
            'points': len(values),
            'min': min(values),
            'max': max(values),
            'labels': label_keys
        }

        for item in parsed['items']:
            item_id = item['id'].lower().replace('-', '_')
            translations[item_id] = item['text']
            items_def.append({
                'id': item_id,
                'text_key': item_id,
                'type': 'likert'
            })
            scoring_items.append(item_id)
    else:
        # Multiple response scales — check if majority share one scale
        # Use likert_options for the majority, per-item overrides for the rest
        likert_options = None
        majority_key = max(response_groups, key=lambda k: len(response_groups[k]))
        majority_indices = set(response_groups[majority_key])
        majority_label_keys, majority_values = response_set_keys[majority_key]

        # If the majority covers most items (>50%), use it as the global likert
        if len(majority_indices) > len(parsed['items']) * 0.5:
            likert_options = {
                'points': len(majority_values),
                'min': min(majority_values),
                'max': max(majority_values),
                'labels': majority_label_keys
            }

            for idx, item in enumerate(parsed['items']):
                item_id = item['id'].lower().replace('-', '_')
                translations[item_id] = item['text']

                if idx in majority_indices:
                    # Use global likert
                    items_def.append({
                        'id': item_id,
                        'text_key': item_id,
                        'type': 'likert'
                    })
                else:
                    # Per-item override using shared label keys for this set
                    resp_key = (tuple(item['values']), tuple(item['labels']))
                    label_keys, values = response_set_keys[resp_key]
                    options = [{'text_key': lk, 'value': v} for lk, v in zip(label_keys, values)]
                    items_def.append({
                        'id': item_id,
                        'text_key': item_id,
                        'type': 'multi',
                        'options': options
                    })
                scoring_items.append(item_id)
        else:
            # No clear majority — use multi for all, but with shared label keys
            for item in parsed['items']:
                item_id = item['id'].lower().replace('-', '_')
                translations[item_id] = item['text']

                resp_key = (tuple(item['values']), tuple(item['labels']))
                label_keys, values = response_set_keys[resp_key]
                options = [{'text_key': lk, 'value': v} for lk, v in zip(label_keys, values)]

                items_def.append({
                    'id': item_id,
                    'text_key': item_id,
                    'type': 'multi',
                    'options': options
                })
                scoring_items.append(item_id)

    translations['debrief'] = 'Thank you for completing this questionnaire.'

    # Build OSD
    osd = {
        'osd_version': '1.0',
        'definition': {
            'scale_info': {
                'name': name,
                'code': code,
                'abbreviation': code,
                'description': f'{len(parsed["items"])}-item self-report measure. Auto-converted from ARC .tbs format.',
                'citation': '',
                'license': '',
                'license_explanation': 'Auto-converted from UW-Madison Addiction Research Center (ARC) .tbs file. License TBD.',
                'version': '1.0',
                'url': f'https://arc.psych.wisc.edu/self-report/',
            },
            'dimensions': [
                {'id': 'total', 'name': 'Total', 'description': f'Sum/mean of all {len(parsed["items"])} items.'}
            ],
            'items': items_def,
            'scoring': {
                'total': {
                    'method': 'sum_coded',
                    'items': scoring_items,
                    'description': f'Sum of all {len(scoring_items)} items.',
                    'item_coding': {item_id: 1 for item_id in scoring_items}
                }
            }
        },
        'translations': {
            'en': translations
        }
    }

    if likert_options:
        osd['definition']['likert_options'] = likert_options

    return osd


def convert_file(tbs_path, output_path=None):
    """Convert a single .tbs file to .osd, incorporating .sss/.R scoring if available."""
    parsed = parse_tbs(tbs_path)

    if not parsed['items']:
        print(f'  WARNING: No items found in {tbs_path}')
        return False

    osd = tbs_to_osd(parsed)

    # Try to enhance with scoring info from .sss or .R files
    scoring_found = apply_scoring_info(osd, tbs_path, parsed['items'])
    scoring_tag = ' +scoring' if scoring_found else ''

    if output_path is None:
        stem = Path(tbs_path).stem
        output_path = Path(tbs_path).parent / f'{stem}.osd'

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(osd, f, indent=2, ensure_ascii=False)
        f.write('\n')

    # Validate JSON
    try:
        with open(output_path) as f:
            json.load(f)
        n_dims = len(osd['definition']['dimensions'])
        print(f'  ✓ {Path(tbs_path).name} → {Path(output_path).name} ({len(parsed["items"])} items, {n_dims} dims{scoring_tag})')
        return True
    except json.JSONDecodeError as e:
        print(f'  ✗ {Path(tbs_path).name} — invalid JSON: {e}')
        return False


def batch_convert(tbs_dir, outdir=None):
    """Convert all .tbs files in a directory tree."""
    tbs_dir = Path(tbs_dir)

    if outdir:
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)

    tbs_files = sorted(tbs_dir.rglob('*.tbs'))
    print(f'Found {len(tbs_files)} .tbs files in {tbs_dir}\n')

    success = 0
    failed = 0

    for tbs_path in tbs_files:
        if outdir:
            # Put OSD in outdir with same relative structure
            rel = tbs_path.relative_to(tbs_dir)
            out_path = outdir / rel.with_suffix('.osd')
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Put OSD next to .tbs file
            out_path = tbs_path.with_suffix('.osd')

        if convert_file(str(tbs_path), str(out_path)):
            success += 1
        else:
            failed += 1

    print(f'\nDone: {success} converted, {failed} failed')
    return success, failed


def main():
    parser = argparse.ArgumentParser(description='Convert ARC .tbs files to OpenScales .osd format')
    parser.add_argument('input', nargs='?', help='Input .tbs file (or directory with --batch)')
    parser.add_argument('--output', '-o', help='Output .osd file path')
    parser.add_argument('--batch', '-b', action='store_true', help='Batch convert all .tbs files in directory')
    parser.add_argument('--outdir', help='Output directory for batch conversion')
    args = parser.parse_args()

    if not args.input:
        parser.print_help()
        sys.exit(1)

    if args.batch:
        batch_convert(args.input, args.outdir)
    else:
        if not convert_file(args.input, args.output):
            sys.exit(1)


if __name__ == '__main__':
    main()
