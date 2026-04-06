#!/usr/bin/env python3
"""
promote_multi_to_likert.py — Convert multi-choice items to likert when
all items in a scale share the same ordered response options.

Promotes the dominant option set to scale-level likert_options and converts
matching multi items to type "likert", removing per-item options.

Usage:
    python3 tools/promote_multi_to_likert.py --all              # process all PhenX
    python3 tools/promote_multi_to_likert.py --dry-run --all    # preview
    python3 tools/promote_multi_to_likert.py PX180401           # single scale
"""
import argparse, json, os, re
from collections import Counter

PHENX_DIR = os.path.join(os.path.dirname(__file__), '..', 'scales', 'phenx')

# 3-option sets that are ordered (likert-like)
ORDERED_3_OPT = {
    ('Not true or hardly ever true', 'Somewhat true or sometimes true', 'Very true or often true'),
    ('Not at all', 'Sometimes', 'Very often or always'),
    ('Not at all', 'Somewhat', 'Very much'),
    ('Never', 'Sometimes', 'Often'),
    ('Never', 'Sometimes', 'Always'),
    ('Not at all', 'A little', 'A lot'),
}

MIN_OPTIONS_AUTO = 3  # Auto-convert if 3+ options with ordered labels
MIN_ITEMS = 3         # Need at least 3 items sharing options


def is_ordered_options(labels, n_opts):
    """Check if option labels represent an ordered scale."""
    if n_opts < 2:
        return False

    # Exclude binary Yes/No, True/False, Male/Female — these are categorical
    if n_opts == 2:
        joined = ' '.join(labels).lower()
        if any(pair in joined for pair in ['yes', 'no', 'true', 'false', 'male', 'female',
                                            'refused', 'don\'t know', 'don\'t know']):
            return False
        # 2-option with ordinal-like labels (e.g., "Not useful at all | Very useful")
        if any(w in joined for w in ['not at all', 'very', 'extremely']):
            return True
        return False

    # 3+ options: check for ordinal language
    joined = ' '.join(labels).lower()

    # Known non-ordered patterns to exclude
    if any(pat in joined for pat in ['male', 'female', 'right hand', 'left hand',
                                      'front only', 'back only', 'small', 'medium', 'large',
                                      'pounds', 'kilograms', 'don\'t know/refused',
                                      'skip to', 'if yes', 'if no', 'go to',
                                      'specify', 'per week', 'per day',
                                      'cup', 'ounce', 'hour']):
        return False

    # Ordinal indicators
    ordinal_words = ['never', 'rarely', 'sometimes', 'often', 'always',
                     'not at all', 'somewhat', 'very', 'extremely',
                     'strongly', 'disagree', 'agree', 'mild', 'moderate', 'severe',
                     'poor', 'fair', 'good', 'excellent',
                     'no!', 'yes!', 'not true', 'quite', 'slightly',
                     'a little', 'a lot', 'unable', 'none',
                     'almost never', 'almost always',
                     'insignificant', 'infrequent', 'frequent', 'consistent',
                     'seldom', 'mostly', 'impossible',
                     'unimportant', 'important',
                     'untrue', 'neither']

    if any(w in joined for w in ordinal_words):
        return True

    # Check against known ordered sets
    clean = tuple(l.strip() for l in labels)
    if clean in ORDERED_3_OPT:
        return True

    # If 4+ options with numeric-looking values, likely ordered
    if n_opts >= 4:
        try:
            vals = [float(l.strip()) for l in labels]
            return True
        except ValueError:
            pass

    return False


def process_scale(code, dry_run=False):
    """Process one scale: promote multi→likert if appropriate."""
    path = os.path.join(PHENX_DIR, code, f'{code}.osd')
    if not os.path.exists(path):
        print(f"  {code}: file not found")
        return False

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    items = data['definition'].get('items', [])
    trans = data.get('translations', {}).get('en', {})

    # Collect multi items and their option fingerprints
    multi_info = []  # (index, item, opts_tuple, labels_tuple, n_opts)
    for idx, item in enumerate(items):
        if item.get('type') != 'multi' or not item.get('options'):
            continue
        opts = item['options']
        vals = tuple(str(o.get('value', '')) for o in opts)
        labels = tuple(trans.get(o.get('text_key', ''), str(o.get('value', ''))) for o in opts)
        multi_info.append((idx, item, vals, labels, len(opts)))

    if len(multi_info) < MIN_ITEMS:
        return False

    # Find dominant option set
    opt_counter = Counter(vals for _, _, vals, _, _ in multi_info)
    dominant_vals, dominant_count = opt_counter.most_common(1)[0]

    if dominant_count < MIN_ITEMS:
        return False

    # Get labels for dominant set
    dominant_labels = None
    dominant_options = None
    for _, item, vals, labels, _ in multi_info:
        if vals == dominant_vals:
            dominant_labels = labels
            dominant_options = item['options']
            break

    n_opts = len(dominant_vals)
    if not is_ordered_options(dominant_labels, n_opts):
        return False

    name = data['definition']['scale_info'].get('name', code)
    print(f"\n  {code}: {name}")
    print(f"    {dominant_count}/{len(multi_info)} multi items → likert ({n_opts} options)")
    print(f"    Labels: {' | '.join(dominant_labels[:6])}{'...' if n_opts > 6 else ''}")

    if dry_run:
        print(f"    [DRY RUN]")
        return True

    # Build likert_options from the dominant option set
    # Create translation keys for the labels
    likert_label_keys = []
    for i, opt in enumerate(dominant_options):
        key = f'likert_{i + 1}'
        likert_label_keys.append(key)
        # Add translation entry
        label_text = trans.get(opt.get('text_key', ''), str(opt.get('value', '')))
        trans[key] = label_text

    # Determine min/max values
    try:
        vals_numeric = [int(v) for v in dominant_vals]
        min_val = min(vals_numeric)
        max_val = max(vals_numeric)
    except (ValueError, TypeError):
        # Non-numeric values: use 1-based
        min_val = 1
        max_val = n_opts

    # Set or update likert_options
    existing_likert = data['definition'].get('likert_options')
    if not existing_likert:
        data['definition']['likert_options'] = {
            'points': n_opts,
            'min': min_val,
            'max': max_val,
            'labels': likert_label_keys,
        }
    # If already exists and matches, keep it; otherwise add per-item overrides (skip for now)

    # Convert matching multi items to likert
    converted = 0
    for idx, item, vals, labels, _ in multi_info:
        if vals == dominant_vals:
            item['type'] = 'likert'
            if 'options' in item:
                del item['options']
            converted += 1

    # Update translations
    data['translations']['en'] = trans

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f"    Converted {converted} items, likert_options set ({min_val}-{max_val})")
    return True


def main():
    parser = argparse.ArgumentParser(description='Promote multi items to likert')
    parser.add_argument('codes', nargs='*', help='Scale codes')
    parser.add_argument('--all', action='store_true', help='Process all PhenX scales')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    args = parser.parse_args()

    if args.all:
        codes = sorted(d for d in os.listdir(PHENX_DIR)
                       if os.path.isdir(os.path.join(PHENX_DIR, d)))
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
