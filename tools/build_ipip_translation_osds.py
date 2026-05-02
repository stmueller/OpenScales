#!/usr/bin/env python3
"""Build per-language IPIP translation OSD files for human review and editing.

Creates one OSD per language (plus English) in scales/ipip/translations/:
  ipip_master_en.osd   — all IPIP items with English text only
  ipip_master_{lang}.osd — all IPIP items with {lang} translations where
                           available; English used as fallback for missing items

These files are NOT run as assessments — they exist so translators can
open a single file, see all items side-by-side (via the translations block),
and fill in gaps. Re-run apply_ipip_translations.py after updating masters.

Items are ordered by text_key (ipip_HXXX numeric sort). Each item has:
  - text_key: the shared key (e.g. ipip_H34)
  - type: "likert"
  - no scoring keys, no dimensions, no random_group

Usage:
    python3 tools/build_ipip_translation_osds.py [--lang LANG] [--dry-run]
"""

import argparse
import json
import re
from pathlib import Path

REPO_ROOT  = Path(__file__).parent.parent
SCALES_DIR = REPO_ROOT / "scales" / "ipip"
TRANS_DIR  = SCALES_DIR / "translations"

SHARED_KEYS = [
    "ipip_likert_1", "ipip_likert_2", "ipip_likert_3",
    "ipip_likert_4", "ipip_likert_5",
    "ipip_question_head", "ipip_debrief",
]

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


def _sort_key(text_key: str) -> int:
    """Sort ipip_HXXX by numeric suffix; non-matching keys sort last."""
    m = re.search(r'(\d+)$', text_key)
    return int(m.group(1)) if m else 999999


def collect_all_item_keys() -> list[str]:
    """Return sorted list of all unique item text_keys used across all OSDs."""
    keys = set()
    for sd in SCALES_DIR.iterdir():
        if not sd.is_dir():
            continue
        osd = sd / f"{sd.name}.osd"
        if not osd.exists():
            continue
        try:
            data = json.loads(osd.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for item in data.get("definition", {}).get("items", []):
            tk = item.get("text_key", "")
            if tk and tk not in SHARED_KEYS:
                keys.add(tk)
    return sorted(keys, key=_sort_key)


def load_master(lang: str) -> dict:
    """Load a language master JSON. Returns {} if not found."""
    p = TRANS_DIR / f"ipip_master_{lang}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def build_osd(lang: str, item_keys: list[str], master_en: dict, master_lang: dict) -> dict:
    """Build the OSD structure for one language."""
    is_en = (lang == "en")

    # English translation block: shared keys + all item keys
    en_trans = {**SHARED_EN}
    for tk in item_keys:
        en_trans[tk] = master_en.get(tk, f"[MISSING EN: {tk}]")

    # Language translation block (only if not English)
    lang_trans = {}
    if not is_en:
        for k in SHARED_KEYS:
            if k in master_lang:
                lang_trans[k] = master_lang[k]
        for tk in item_keys:
            if tk in master_lang:
                lang_trans[tk] = master_lang[tk]

    # Coverage stats for description
    if is_en:
        coverage_note = f"{len(item_keys)} items (English source)"
    else:
        covered = sum(1 for tk in item_keys if tk in master_lang)
        shared_covered = sum(1 for k in SHARED_KEYS if k in master_lang)
        coverage_note = (
            f"{covered}/{len(item_keys)} items translated"
            f"; {shared_covered}/{len(SHARED_KEYS)} shared keys"
        )

    items = [
        {"id": f"i{i+1}", "text_key": tk, "type": "likert"}
        for i, tk in enumerate(item_keys)
    ]

    osd = {
        "osd_version": "1.0",
        "definition": {
            "scale_info": {
                "name": f"IPIP Master Item Pool — {lang.upper()}",
                "code": f"ipip_master_{lang}",
                "description": (
                    f"Complete IPIP item pool for translation review and editing. "
                    f"{coverage_note}. "
                    "This file is for translator use only — not an assessment instrument."
                ),
                "license": "Public Domain",
                "domain": "Translation"
            },
            "likert_options": {
                "points": 5,
                "min": 1,
                "max": 5,
                "labels": [
                    "ipip_likert_1", "ipip_likert_2", "ipip_likert_3",
                    "ipip_likert_4", "ipip_likert_5"
                ],
                "question_head": "ipip_question_head"
            },
            "items": items,
        },
        "translations": {"en": en_trans},
    }

    if not is_en and lang_trans:
        osd["translations"][lang] = lang_trans

    return osd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", help="Only build this language (plus en)")
    parser.add_argument("--dry-run", action="store_true", help="Show counts, don't write")
    args = parser.parse_args()

    master_en = load_master("en")
    if not master_en:
        print(f"ERROR: {TRANS_DIR}/ipip_master_en.json not found")
        return

    item_keys = collect_all_item_keys()
    print(f"Unique item keys across all OSDs: {len(item_keys)}")

    # Determine languages to build
    if args.lang:
        langs = [args.lang]
    else:
        langs = sorted(
            f.stem[len("ipip_master_"):]
            for f in TRANS_DIR.glob("ipip_master_*.json")
            if f.stem != "ipip_master_en"
        )

    # Always build English first
    targets = ["en"] + [l for l in langs if l != "en"]

    for lang in targets:
        master_lang = load_master(lang) if lang != "en" else {}
        osd = build_osd(lang, item_keys, master_en, master_lang)
        out_path = TRANS_DIR / f"ipip_master_{lang}.osd"

        covered = sum(1 for tk in item_keys if tk in master_lang)
        shared_covered = sum(1 for k in SHARED_KEYS if k in master_lang)
        status = (
            "English source" if lang == "en"
            else f"{covered}/{len(item_keys)} items, {shared_covered}/{len(SHARED_KEYS)} shared"
        )

        if args.dry_run:
            print(f"  {lang}: would write {out_path.name} ({status})")
        else:
            out_path.write_text(
                json.dumps(osd, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8"
            )
            print(f"  {lang}: {out_path.name} ({status})")


if __name__ == "__main__":
    main()
