#!/usr/bin/env python3
"""
add_phenx_scoring.py — Parse scoring text from PhenX scales and add
proper OSD dimensions + scoring blocks.

Usage:
    python3 tools/add_phenx_scoring.py PX180801          # single scale
    python3 tools/add_phenx_scoring.py --all              # all with scoring text
    python3 tools/add_phenx_scoring.py --dry-run PX180801 # preview without writing
"""
import argparse, json, os, re, sys, collections

PHENX_DIR = os.path.join(os.path.dirname(__file__), '..', 'scales', 'phenx')


def load_osd(code):
    path = os.path.join(PHENX_DIR, code, f'{code}.osd')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f), path


def save_osd(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


def get_scored_items(osd):
    """Get list of item IDs that are actual questions (not inst/section)."""
    return [i['id'] for i in osd['definition'].get('items', [])
            if i.get('type') not in ('inst', 'section', 'image')]


def find_scoring_items(osd):
    """Find items that contain scoring text."""
    items = osd['definition'].get('items', [])
    trans = osd.get('translations', {}).get('en', {})
    result = []
    for item in items:
        iid = item.get('id', '')
        text = trans.get(item.get('text_key', ''), '')
        if ('scoring' in iid.lower() or 'scoring' in text.lower()[:60] or
            'score ' in text.lower()[:60] or 'recode' in text.lower()[:60]):
            result.append((iid, item.get('type', ''), text))
    return result


def find_scoring_sections(osd):
    """Find section headers related to scoring."""
    items = osd['definition'].get('items', [])
    trans = osd.get('translations', {}).get('en', {})
    result = []
    for item in items:
        if item.get('type') == 'section':
            text = trans.get(item.get('text_key', ''), '')
            if 'scoring' in text.lower():
                result.append(item['id'])
    return result


def parse_reverse_items(text, all_item_ids):
    """Extract reverse-coded item numbers from scoring text."""
    # Patterns like "Reverse-score items: 4, 5, 7, 8" or "Items 1, 5, 6 should be reversed"
    # or "reverse coded: 3, 5, 8" or "items 3, 7, 9 are reverse scored"
    reverse = []

    patterns = [
        r'[Rr]everse[- ]?scor\w*[:\s]+(?:items?\s*)?([0-9,\s]+(?:and\s+\d+)?)',
        r'[Ii]tems?\s+([\d,\s]+(?:and\s+\d+)?)\s+(?:should be|are)\s+reverse',
        r'[Rr]everse[- ]?cod\w*[:\s]+(?:items?\s*)?([0-9,\s]+(?:and\s+\d+)?)',
        r'[Rr]everse[d\s]+items?[:\s]+([\d,\s]+(?:and\s+\d+)?)',
    ]

    for pat in patterns:
        m = re.search(pat, text)
        if m:
            nums_str = m.group(1).replace('and', ',')
            nums = [int(n.strip()) for n in nums_str.split(',') if n.strip().isdigit()]
            reverse.extend(nums)

    return list(set(reverse))


def parse_subscales(text, all_item_ids):
    """Extract subscale definitions from scoring text."""
    subscales = collections.OrderedDict()

    # Pre-process: fix run-on text where item codes jam against subscale names
    # e.g., "BAES14Sedation:" → "BAES14 Sedation:"
    text = re.sub(r'(\d)([A-Z][a-z])', r'\1 \2', text)

    # Pattern: "Subscale Name: items 1, 3, 5, 7" or "Name (items: 1,2,3)"
    # or "Factor Name: items 1, 2, 3" or "Name subscale: items 1-5"
    patterns = [
        # "Name: items 1, 3, 5" or "Name: questions 1, 3, 5"
        r'([A-Z][\w\s/&-]{2,40}?)(?:\s*subscale)?(?:\s*\([^)]*\))?[:\s]+(?:items?|questions?)\s*[:\s]*([\d,\s\-]+(?:and\s+\d+)?)',
        # "Name subscale: items 1, 3, 5"
        r'([\w\s/&-]+?)\s+[Ss]ubscale[:\s]+(?:items?\s*)?([\d,\s\-]+)',
        # "Name (N items): 1, 3, 5"
        r'([\w\s/&-]+?)\s*\(\d+\s*items?\)[:\s]*([\d,\s\-]+)',
        # "Name: = PREFIX1 + PREFIX2 + PREFIX3" (BAES-style with item code prefixes)
        r'([A-Z][\w\s/&-]{2,30}?):\s*=?\s*([A-Z]+\d+(?:\s*\+\s*[A-Z]+\d+)+)',
    ]

    for pat in patterns:
        for m in re.finditer(pat, text):
            name = m.group(1).strip().rstrip(':').strip()
            raw = m.group(2).replace('and', ',')
            nums = []

            # Check if it's PREFIX+PREFIX format (e.g., "BAES3 + BAES4 + BAES5")
            prefix_items = re.findall(r'[A-Z]+(\d+)', raw)
            if prefix_items and '+' in raw:
                nums = [int(n) for n in prefix_items]
            else:
                # Comma/space separated numbers
                for part in raw.split(','):
                    part = part.strip()
                    if '-' in part:
                        try:
                            a, b = part.split('-')
                            nums.extend(range(int(a.strip()), int(b.strip()) + 1))
                        except ValueError:
                            pass
                    elif part.isdigit():
                        nums.append(int(part))

            if name and nums:
                sub_id = re.sub(r'[^a-z0-9_]', '_', name.lower()).strip('_')
                sub_id = re.sub(r'_+', '_', sub_id)
                subscales[sub_id] = {
                    'name': name,
                    'item_nums': nums,
                }

    return subscales


def parse_thresholds(text):
    """Extract score thresholds from scoring text."""
    thresholds = []

    # Pattern: "0-7 = No clinically significant" or "0-4: Minimal"
    for m in re.finditer(r'(\d+)\s*[-–]\s*(\d+)\s*[=:]\s*([A-Z][\w\s]+?)(?=[,;\.\d]|$)', text):
        thresholds.append({
            'min': int(m.group(1)),
            'max': int(m.group(2)),
            'label': m.group(3).strip(),
        })

    return thresholds


def parse_method(text):
    """Determine scoring method from text."""
    tl = text.lower()
    if 'mean' in tl or 'average' in tl:
        return 'mean_coded'
    if 'sum' in tl or 'add' in tl or 'total' in tl:
        return 'sum_coded'
    if 'correct' in tl or 'number correct' in tl:
        return 'sum_correct'
    return 'sum_coded'  # default


def item_num_to_id(num, all_ids):
    """Map a 1-based item number to an actual item ID."""
    scored = [iid for iid in all_ids]  # already in order
    if 1 <= num <= len(scored):
        return scored[num - 1]
    return None


def build_scoring(code, scoring_text, all_item_ids):
    """Parse scoring text and build dimensions + scoring blocks."""
    reverse_nums = parse_reverse_items(scoring_text, all_item_ids)
    subscales = parse_subscales(scoring_text, all_item_ids)
    thresholds = parse_thresholds(scoring_text)
    method = parse_method(scoring_text)

    dimensions = []
    scoring = collections.OrderedDict()

    if subscales:
        # Multiple subscales
        for sub_id, info in subscales.items():
            dim = {'id': sub_id, 'name': info['name']}
            dimensions.append(dim)

            items_map = collections.OrderedDict()
            for num in info['item_nums']:
                iid = item_num_to_id(num, all_item_ids)
                if iid:
                    coding = -1 if num in reverse_nums else 1
                    items_map[iid] = coding

            if items_map:
                sc = collections.OrderedDict()
                sc['description'] = f"{info['name']}: {method} of {len(items_map)} items."
                sc['method'] = method
                if all(v == 1 for v in items_map.values()):
                    sc['items'] = list(items_map.keys())
                else:
                    sc['items'] = dict(items_map)
                scoring[sub_id] = sc

        # If no subscales captured enough items, fall through to total
        total_captured = sum(len(s.get('items', [])) if isinstance(s.get('items'), list)
                           else len(s.get('items', {})) for s in scoring.values())
        if total_captured < len(all_item_ids) * 0.3:
            # Subscale parsing captured too few items — fall through to total
            dimensions = []
            scoring = collections.OrderedDict()
            subscales = {}

    if not subscales:
        # Single total score — use ALL scored items
        dim_id = 'total'
        dim_name = 'Total Score'
        dimensions.append({'id': dim_id, 'name': dim_name})

        items_map = collections.OrderedDict()
        for i, iid in enumerate(all_item_ids):
            num = i + 1
            coding = -1 if num in reverse_nums else 1
            items_map[iid] = coding

        sc = collections.OrderedDict()
        sc['description'] = f"Total: {method} of all {len(items_map)} items."
        if reverse_nums:
            sc['description'] += f" Items {reverse_nums} reverse-coded."
        sc['method'] = method

        if all(v == 1 for v in items_map.values()):
            sc['items'] = list(items_map.keys())
        else:
            sc['items'] = dict(items_map)

        if thresholds:
            sc['norms'] = {'thresholds': thresholds}

        scoring[dim_id] = sc

    return dimensions, scoring


def process_scale(code, dry_run=False):
    """Process one PhenX scale: parse scoring, add blocks, remove scoring items."""
    osd, path = load_osd(code)

    scoring_items = find_scoring_items(osd)
    if not scoring_items:
        print(f"  {code}: No scoring items found, skipping.")
        return False

    # Skip if already has scoring
    existing_scoring = osd['definition'].get('scoring', {})
    if existing_scoring:
        print(f"  {code}: Already has scoring block with {len(existing_scoring)} dimensions.")

    scored_ids = get_scored_items(osd)
    scoring_sections = find_scoring_sections(osd)

    # Combine all scoring text
    all_scoring_text = ' '.join(text for _, _, text in scoring_items)

    print(f"\n  {code}: {osd['definition']['scale_info'].get('name', '')}")
    print(f"    Scored items: {len(scored_ids)}")
    print(f"    Scoring text items: {[iid for iid, _, _ in scoring_items]}")

    # Parse
    dimensions, scoring = build_scoring(code, all_scoring_text, scored_ids)

    if not scoring:
        print(f"    Could not parse scoring. Manual review needed.")
        return False

    print(f"    Parsed: {len(dimensions)} dimension(s), {len(scoring)} scoring block(s)")
    for dim_id, sc in scoring.items():
        items = sc['items']
        n = len(items) if isinstance(items, (list, dict)) else 0
        rev = sum(1 for v in items.values() if v == -1) if isinstance(items, dict) else 0
        print(f"      {dim_id}: {sc['method']}, {n} items" + (f", {rev} reversed" if rev else ""))

    if dry_run:
        print(f"    [DRY RUN] Would write to {path}")
        return True

    # Apply changes
    osd['definition']['dimensions'] = dimensions
    osd['definition']['scoring'] = dict(scoring)

    # Store original scoring text as metadata
    osd['definition']['_scoring_notes'] = all_scoring_text[:2000]

    # Remove scoring items and sections from items list
    remove_ids = set(iid for iid, _, _ in scoring_items) | set(scoring_sections)
    osd['definition']['items'] = [
        i for i in osd['definition']['items']
        if i['id'] not in remove_ids
    ]

    save_osd(osd, path)
    print(f"    Written to {path}")
    return True


def main():
    parser = argparse.ArgumentParser(description='Add scoring to PhenX scales')
    parser.add_argument('codes', nargs='*', help='Scale codes (e.g., PX180801)')
    parser.add_argument('--all', action='store_true', help='Process all scales with scoring text')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    args = parser.parse_args()

    if args.all:
        # Find all scales with scoring text
        codes = []
        for d in sorted(os.listdir(PHENX_DIR)):
            osd_path = os.path.join(PHENX_DIR, d, f'{d}.osd')
            if not os.path.exists(osd_path):
                continue
            try:
                osd = json.load(open(osd_path))
                if find_scoring_items(osd):
                    codes.append(d)
            except:
                pass
        print(f"Found {len(codes)} scales with scoring text")
    else:
        codes = args.codes

    if not codes:
        parser.print_help()
        return

    processed = 0
    for code in codes:
        try:
            if process_scale(code, args.dry_run):
                processed += 1
        except Exception as e:
            print(f"  {code}: ERROR: {e}")

    print(f"\nProcessed: {processed}/{len(codes)}")


if __name__ == '__main__':
    main()
