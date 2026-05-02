#!/usr/bin/env python3
"""Patch hand-crafted IPIP OSD files to use shared canonical translation keys.

Changes:
  - likert_options.labels: ["likert_1",...] → ["ipip_likert_1",...]
  - likert_options.question_head: "question_head" → "ipip_question_head"
  - item text_key: per-scale key like "ipip_neo_001" → canonical "ipip_H123" (or ipip_text_slug fallback)
  - translations.en: keys updated to match, old keys removed
  - Adds shared anchor strings (ipip_likert_1…5, ipip_question_head, ipip_debrief) to translations.en

Also appends all discovered English item texts to the master translation file.

Usage:
    python3 tools/patch_ipip_shared_keys.py [--dry-run] [--scale CODE]
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT       = Path(__file__).parent.parent
SCALES_DIR      = REPO_ROOT / "scales" / "ipip"
ITEM_CODES_PATH = SCALES_DIR / "ipip_item_codes.json"
MASTER_TRANS    = SCALES_DIR / "ipip_master_en.json"

IPIP_LIKERT_KEYS = ["ipip_likert_1", "ipip_likert_2", "ipip_likert_3",
                    "ipip_likert_4", "ipip_likert_5"]
IPIP_SHARED_EN = {
    "ipip_likert_1": "Very Inaccurate",
    "ipip_likert_2": "Moderately Inaccurate",
    "ipip_likert_3": "Neither Accurate Nor Inaccurate",
    "ipip_likert_4": "Moderately Accurate",
    "ipip_likert_5": "Very Accurate",
    "ipip_question_head": (
        "<h3>How Accurately Can You Describe Yourself?</h3>"
        "<p>Describe yourself as you generally are now, not as you wish to be in the future. "
        "Describe yourself as you honestly see yourself, in relation to other people you know "
        "of the same sex as you are, and roughly your same age. So that you can describe "
        "yourself in an honest manner, your responses will be kept in absolute confidence. "
        "Indicate the accuracy of the item as it applies to you, using the following rating scale:</p>"
    ),
    "ipip_debrief": "Thank you for completing this questionnaire.",
}

OLD_LIKERT_KEYS = ["likert_1", "likert_2", "likert_3", "likert_4", "likert_5"]


def load_item_codes() -> dict:
    if ITEM_CODES_PATH.exists():
        data = json.loads(ITEM_CODES_PATH.read_text(encoding='utf-8'))
        return data.get('text_to_code', {})
    return {}


def text_to_key(text: str, text_to_code: dict) -> str:
    code = text_to_code.get(text.strip())
    if code:
        return f"ipip_{code}"
    slug = re.sub(r'[^a-z0-9]+', '_', text.lower().strip()).strip('_')[:40]
    return f"ipip_text_{slug}"


def load_master_en() -> dict:
    if MASTER_TRANS.exists():
        return json.loads(MASTER_TRANS.read_text(encoding='utf-8'))
    return dict(IPIP_SHARED_EN)


def save_master_en(master: dict) -> None:
    MASTER_TRANS.write_text(
        json.dumps(master, indent=2, ensure_ascii=False) + "\n",
        encoding='utf-8'
    )


def patch_osd(osd_path: Path, text_to_code: dict, master_en: dict,
              dry_run: bool) -> bool:
    """Patch one OSD file. Returns True if changed."""
    try:
        data = json.loads(osd_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ERROR reading {osd_path}: {e}")
        return False

    defn = data.get('definition', {})
    items = defn.get('items', [])
    trans = data.get('translations', {})
    en = trans.get('en', {})

    changed = False

    # --- 1. Fix likert_options labels and question_head ---
    opts = defn.get('likert_options', {})
    labels = opts.get('labels', [])
    if labels and labels[0] in OLD_LIKERT_KEYS:
        opts['labels'] = IPIP_LIKERT_KEYS[:len(labels)]
        changed = True
    qh = opts.get('question_head', '')
    if qh in ('question_head', 'likert_head', 'instructions'):
        opts['question_head'] = 'ipip_question_head'
        changed = True

    # --- 2. Remap item text_keys and translations ---
    # Build a map from old text_key → new text_key using item text from en dict
    key_remap = {}  # old_key → new_key
    new_en = dict(IPIP_SHARED_EN)  # start with shared anchors

    for item in items:
        old_tkey = item.get('text_key', item.get('id', ''))
        item_text = en.get(old_tkey, '')
        if not item_text:
            # Can't remap without knowing the text — keep as-is
            new_en[old_tkey] = ''
            continue

        new_tkey = text_to_key(item_text, text_to_code)
        key_remap[old_tkey] = new_tkey
        new_en[new_tkey] = item_text
        master_en[new_tkey] = item_text

        if new_tkey != old_tkey:
            item['text_key'] = new_tkey
            changed = True

    # Copy non-item, non-old-likert keys from original en
    skip_old = set(OLD_LIKERT_KEYS) | {'question_head', 'debrief', 'likert_head', 'instructions'}
    for k, v in en.items():
        if k in skip_old:
            continue
        if k in key_remap:
            continue  # already handled as item key
        # Keep other keys (e.g. subscale headers, custom instructions)
        if k not in new_en:
            new_en[k] = v

    # Check if en dict actually changed
    if new_en != en:
        changed = True

    trans['en'] = new_en
    data['translations'] = trans

    if not changed:
        return False

    if dry_run:
        print(f"  DRY-RUN: would patch {osd_path.parent.name}")
        return True

    osd_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding='utf-8')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--scale', help='Only patch this scale code')
    args = parser.parse_args()

    text_to_code = load_item_codes()
    print(f"Loaded {len(text_to_code)} IPIP item codes")

    master_en = load_master_en()
    print(f"Loaded master_en with {len(master_en)} keys")

    patched = 0
    skipped = 0

    for scale_dir in sorted(SCALES_DIR.iterdir()):
        if not scale_dir.is_dir():
            continue
        code = scale_dir.name
        if args.scale and code != args.scale:
            continue

        osd_path = scale_dir / f"{code}.osd"
        if not osd_path.exists():
            continue

        result = patch_osd(osd_path, text_to_code, master_en, args.dry_run)
        if result:
            print(f"  Patched {code}")
            patched += 1
        else:
            skipped += 1

    if not args.dry_run:
        save_master_en(master_en)
        print(f"\nUpdated master_en → {MASTER_TRANS}  ({len(master_en)} keys)")

    print(f"Patched: {patched}  Unchanged: {skipped}")


if __name__ == "__main__":
    main()
