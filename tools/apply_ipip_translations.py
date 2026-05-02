#!/usr/bin/env python3
"""Inject per-language IPIP translation masters into individual OSD files.

For each OSD in scales/ipip/:
  - Reads its translations.en to get the set of text_keys used
  - For each language master (ipip_master_{lang}.json), looks up each key
  - Writes translations.{lang} only if ALL item keys are covered (all-or-none)
  - Shared keys (ipip_likert_*, ipip_question_head, ipip_debrief) are always
    included when present in the master, regardless of item coverage
  - At the end, reports partially-covered scales per language

Usage:
    python3 tools/apply_ipip_translations.py [--dry-run] [--lang LANG] [--scale CODE]
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT    = Path(__file__).parent.parent
SCALES_DIR   = REPO_ROOT / "scales" / "ipip"
TRANS_DIR    = SCALES_DIR / "translations"
MASTER_EN    = TRANS_DIR / "ipip_master_en.json"

# All shared keys — must ALL be present in a language master before that language
# is written to any OSD. Missing any of these causes raw key display in the runner.
SHARED_KEYS = {
    "ipip_likert_1", "ipip_likert_2", "ipip_likert_3",
    "ipip_likert_4", "ipip_likert_5",
    "ipip_question_head", "ipip_debrief",
}
# Subset that are required (likert anchors + question head); debrief is optional
REQUIRED_SHARED = {
    "ipip_likert_1", "ipip_likert_2", "ipip_likert_3",
    "ipip_likert_4", "ipip_likert_5",
    "ipip_question_head",
}

SHARED_EN = {
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


def load_masters(lang_filter=None):
    """Return dict of {lang: {key: translated_text}}."""
    masters = {}
    for f in sorted(TRANS_DIR.glob("ipip_master_*.json")):
        lang = f.stem[len("ipip_master_"):]
        if lang == "en":
            continue
        if lang_filter and lang != lang_filter:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        masters[lang] = data
    return masters


def item_keys_from_osd(data):
    """Return set of text_keys used by items (excludes shared keys)."""
    items = data.get("definition", {}).get("items", [])
    keys = set()
    for item in items:
        tk = item.get("text_key", "")
        if tk and tk not in SHARED_KEYS:
            keys.add(tk)
    return keys


def apply_translations(osd_path, masters, dry_run, verbose):
    """Apply translations to one OSD. Returns (changed, partial_report).

    partial_report: {lang: (covered, total)} for langs with 0 < covered < total.
    """
    try:
        data = json.loads(osd_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ERROR reading {osd_path}: {e}")
        return False, {}

    item_keys = item_keys_from_osd(data)
    trans = data.setdefault("translations", {})

    en = trans.get("en", {})
    if not en:
        return False, {}

    changed = False
    partial_report = {}  # lang -> (covered, total)

    for lang, master in masters.items():
        # Check required shared keys first — missing any = raw key shown in runner
        missing_shared = REQUIRED_SHARED - master.keys()
        if missing_shared:
            if verbose:
                print(f"    {lang}: missing shared keys {sorted(missing_shared)} — skip")
            if lang in trans:
                if verbose:
                    print(f"    {lang}: removing previously-written translation (missing shared keys)")
                if not dry_run:
                    del trans[lang]
                    changed = True
            continue

        # Count item key coverage
        covered = sum(1 for tk in item_keys if tk in master)
        total = len(item_keys)

        if total > 0 and covered < total:
            if covered > 0:
                partial_report[lang] = (covered, total)
            if verbose:
                status = f"{covered}/{total} ({covered/total:.0%}) — skip (incomplete items)"
                print(f"    {lang}: {status}")
            if lang in trans:
                if verbose:
                    print(f"    {lang}: removing previously-written incomplete translation")
                if not dry_run:
                    del trans[lang]
                    changed = True
            continue

        # Build full translation dict: shared keys + all item keys
        lang_trans = {}
        for sk in SHARED_KEYS:
            if sk in master:
                lang_trans[sk] = master[sk]
        for tk in item_keys:
            lang_trans[tk] = master[tk]

        existing = trans.get(lang, {})
        if lang_trans == existing:
            if verbose:
                print(f"    {lang}: {covered}/{total} item keys — unchanged")
            continue

        if verbose:
            print(f"    {lang}: {covered}/{total} item keys — {'would write' if dry_run else 'writing'}")

        if not dry_run:
            trans[lang] = lang_trans
            changed = True

    if changed and not dry_run:
        osd_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return changed, partial_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, don't write")
    parser.add_argument("--lang", help="Only apply this language code")
    parser.add_argument("--scale", help="Only apply to this scale code")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-language details per scale")
    args = parser.parse_args()

    masters = load_masters(args.lang)
    print(f"Loaded {len(masters)} language masters: {', '.join(sorted(masters))}")

    updated = 0
    skipped = 0
    # partial_coverage: {lang: [(scale_code, covered, total), ...]}
    partial_coverage = {lang: [] for lang in masters}

    for scale_dir in sorted(SCALES_DIR.iterdir()):
        if not scale_dir.is_dir():
            continue
        code = scale_dir.name
        if args.scale and code != args.scale:
            continue

        osd_path = scale_dir / f"{code}.osd"
        if not osd_path.exists():
            continue

        if args.verbose:
            print(f"\n{code}")
        changed, partial = apply_translations(osd_path, masters, args.dry_run, args.verbose)
        for lang, (covered, total) in partial.items():
            partial_coverage[lang].append((code, covered, total))
        if changed:
            if not args.verbose:
                print(f"  Updated {code}")
            updated += 1
        else:
            skipped += 1

    action = "Would update" if args.dry_run else "Updated"
    print(f"\n{action}: {updated}  Unchanged: {skipped}")

    # Report partially-covered scales per language
    any_partial = any(v for v in partial_coverage.values())
    if any_partial:
        print("\nPartially covered (skipped):")
        for lang in sorted(partial_coverage):
            entries = partial_coverage[lang]
            if not entries:
                continue
            print(f"  {lang}:")
            for code, covered, total in sorted(entries, key=lambda x: -x[1]/x[2]):
                print(f"    {code}: {covered}/{total} ({covered/total:.0%})")


if __name__ == "__main__":
    main()
