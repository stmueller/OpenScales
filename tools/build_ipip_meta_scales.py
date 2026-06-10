#!/usr/bin/env python3
"""Build meta-scale OSD files aggregating all subscales in a family.

For each family (AB5C, CPI, TCI, etc.), produces a single OSD that:
  - Contains every item from every subscale as a separate section
  - Each section has a visible_when parameter (show_<subscale_code>) defaulting to true
  - Scoring and dimensions are copied verbatim from the subscale OSDs
  - Translations are merged (all subscale translations combined)

This gives translators one file to work with instead of 30-40, and lets
runners administer any combination of subscales via parameter flags.

Usage:
    python3 tools/build_ipip_meta_scales.py [--dry-run] [--family FAMILY]
    python3 tools/build_ipip_meta_scales.py --list
"""

import argparse
import json
import re
from pathlib import Path
from collections import OrderedDict
from datetime import date

REPO_ROOT  = Path(__file__).parent.parent
SCALES_DIR = REPO_ROOT / "scales" / "ipip"

TODAY = date.today().isoformat()

FAMILIES = {
    "6FPQ":    {"prefix": "IPIP-6FPQ-",    "name": "IPIP 6FPQ",     "abbr": "IPIP-6FPQ"},
    "7FACTOR": {"prefix": "IPIP-7FACTOR-", "name": "IPIP 7-Factor", "abbr": "IPIP-7FACTOR"},
    "AB5C":    {"prefix": "IPIP-AB5C-",    "name": "IPIP AB5C",     "abbr": "IPIP-AB5C"},
    "CPI":     {"prefix": "IPIP-CPI-",     "name": "IPIP CPI",      "abbr": "IPIP-CPI"},
    "HPI":     {"prefix": "IPIP-HPI-",     "name": "IPIP HPI",      "abbr": "IPIP-HPI"},
    "HPIHIC":  {"prefix": "IPIP-HPIHIC-",  "name": "IPIP HPI-HIC", "abbr": "IPIP-HPIHIC"},
    "JPI":     {"prefix": "IPIP-JPI-",     "name": "IPIP JPI",      "abbr": "IPIP-JPI"},
    "MPQ":     {"prefix": "IPIP-MPQ-",     "name": "IPIP MPQ",      "abbr": "IPIP-MPQ"},
    "NEO5-20": {"prefix": "IPIP-NEO5-20-", "name": "IPIP NEO5-20",  "abbr": "IPIP-NEO5-20"},
    "ORAIS":   {"prefix": "IPIP-ORAIS-",   "name": "IPIP ORAIS",    "abbr": "IPIP-ORAIS"},
    "TCI":     {"prefix": "IPIP-TCI-",     "name": "IPIP TCI",      "abbr": "IPIP-TCI"},
}

SHARED_KEYS = {
    "ipip_likert_1","ipip_likert_2","ipip_likert_3",
    "ipip_likert_4","ipip_likert_5","ipip_question_head","ipip_debrief",
}


def safe_param_name(code):
    """Convert subscale code to a valid parameter name: show_<code_lowercased_sanitized>."""
    slug = re.sub(r'[^a-z0-9]', '_', code.lower()).strip('_')
    return f"show_{slug}"


def subscale_title_key(code):
    return f"section_title_{re.sub(r'[^a-z0-9]', '_', code.lower()).strip('_')}"


def load_subscales(prefix):
    """Return sorted list of (code, osd_data) for all subscales with prefix."""
    subs = []
    for d in sorted(SCALES_DIR.iterdir()):
        if not d.is_dir() or not d.name.startswith(prefix):
            continue
        osd = d / f"{d.name}.osd"
        if not osd.exists():
            continue
        data = json.loads(osd.read_text(encoding="utf-8"))
        subs.append((d.name, data))
    return subs


def build_meta(family_key, dry_run=False, verbose=False):
    cfg = FAMILIES[family_key]
    prefix = cfg["prefix"]
    meta_code = f"IPIP-{family_key}"
    meta_dir = SCALES_DIR / meta_code

    subs = load_subscales(prefix)
    if not subs:
        print(f"  {family_key}: no subscales found, skip")
        return

    # --- pick citation + url from first subscale ---
    first_info = subs[0][1]["definition"]["scale_info"]
    citation = first_info.get("citation", "")
    url = first_info.get("url", "")

    # --- build parameters block ---
    parameters = {
        "shuffle_questions": {
            "type": "boolean",
            "default": 0,
            "description": "Randomize item presentation order within each section."
        }
    }
    for code, data in subs:
        pname = safe_param_name(code)
        n = sum(1 for it in data["definition"].get("items", []) if it.get("type") == "likert")
        parameters[pname] = {
            "type": "boolean",
            "default": 1,
            "description": f"Include the {code} subscale ({n} items)."
        }

    # --- build dimensions (collect from all subscales) ---
    all_dimensions = []
    seen_dims = set()
    for code, data in subs:
        for dim in data["definition"].get("dimensions", []):
            if dim["id"] not in seen_dims:
                all_dimensions.append(dim)
                seen_dims.add(dim["id"])

    # --- build items list (section marker + items per subscale) ---
    all_items = []
    all_scoring = {}
    item_id_set = set()

    for code, data in subs:
        defn = data["definition"]
        pname = safe_param_name(code)
        title_key = subscale_title_key(code)

        section_marker = {
            "id": f"section_{re.sub(r'[^a-z0-9]', '_', code.lower()).strip('_')}",
            "type": "section",
            "text_key": title_key,
            "visible_when": pname
        }
        all_items.append(section_marker)

        for item in defn.get("items", []):
            # Ensure item IDs are unique across the meta-scale
            item_copy = dict(item)
            orig_id = item_copy["id"]
            # prefix with subscale slug if needed to avoid collisions
            slug = re.sub(r'[^a-z0-9]', '_', code.lower()).strip('_')
            new_id = f"{slug}__{orig_id}" if orig_id in item_id_set else orig_id
            item_copy["id"] = new_id
            item_id_set.add(new_id)
            all_items.append(item_copy)

        # scoring: remap item IDs
        sub_scoring = defn.get("scoring", {})
        for dim_id, dim_scoring in sub_scoring.items():
            new_dim = dict(dim_scoring)
            old_items_map = dim_scoring.get("items", {})
            new_items_map = {}
            for oid, weight in old_items_map.items():
                slug = re.sub(r'[^a-z0-9]', '_', code.lower()).strip('_')
                new_oid = f"{slug}__{oid}" if oid in (item_id_set - {oid}) else oid
                new_items_map[new_oid] = weight
            new_dim["items"] = new_items_map
            all_scoring[dim_id] = new_dim

    # --- merge translations ---
    merged_trans = {}
    for code, data in subs:
        for lang, trans in data.get("translations", {}).items():
            if lang not in merged_trans:
                merged_trans[lang] = {}
            for k, v in trans.items():
                merged_trans[lang][k] = v  # later subscales overwrite shared keys (all identical anyway)

    # Add section title keys to English translation
    en_trans = merged_trans.setdefault("en", {})
    for code, data in subs:
        title_key = subscale_title_key(code)
        # Use the subscale's own name as section title
        sub_name = data["definition"]["scale_info"].get("name", code)
        en_trans[title_key] = sub_name

    # Canonical key order for en: shared keys first, then section titles, then item keys
    ordered_en = {}
    for k in ["ipip_likert_1","ipip_likert_2","ipip_likert_3","ipip_likert_4","ipip_likert_5","ipip_question_head","ipip_debrief"]:
        if k in en_trans:
            ordered_en[k] = en_trans[k]
    for code, _ in subs:
        tk = subscale_title_key(code)
        if tk in en_trans:
            ordered_en[tk] = en_trans[tk]
    for k, v in en_trans.items():
        if k not in ordered_en:
            ordered_en[k] = v
    merged_trans["en"] = ordered_en

    # --- assemble OSD ---
    osd = {
        "osd_version": "1.0",
        "definition": {
            "scale_info": {
                "code": meta_code,
                "name": cfg["name"],
                "abbreviation": cfg["abbr"],
                "description": (
                    f"Meta-scale aggregating all {len(subs)} {cfg['abbr']} subscales. "
                    f"Each subscale is a separate section controlled by a boolean parameter. "
                    f"Intended primarily for translation and bulk administration."
                ),
                "citation": citation,
                "license": "Public Domain",
                "version": "1.0",
                "url": url,
                "domain": "Personality"
            },
            "implementation": {
                "author": "Shane T. Mueller",
                "organization": "OpenScales Project",
                "date": TODAY,
                "license": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "notes": f"Auto-generated by build_ipip_meta_scales.py from {len(subs)} subscales."
            },
            "likert_options": {
                "points": 5,
                "min": 1,
                "max": 5,
                "labels": [
                    "ipip_likert_1","ipip_likert_2","ipip_likert_3",
                    "ipip_likert_4","ipip_likert_5"
                ],
                "question_head": "ipip_question_head"
            },
            "parameters": parameters,
            "dimensions": all_dimensions,
            "items": all_items,
            "scoring": all_scoring
        },
        "translations": merged_trans
    }

    out_dir = meta_dir
    out_path = out_dir / f"{meta_code}.osd"

    if dry_run:
        n_items = sum(1 for it in all_items if it.get("type") != "section")
        n_keys = sum(1 for k in merged_trans.get("en", {}) if k not in SHARED_KEYS and not k.startswith("section_title_"))
        print(f"  {meta_code}: {len(subs)} subscales, {n_items} items, {n_keys} unique item keys  -> {out_path} (dry-run)")
        return

    out_dir.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(osd, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_items = sum(1 for it in all_items if it.get("type") != "section")
    print(f"  {meta_code}: {len(subs)} subscales, {n_items} items -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--family", help="Only build this family (e.g. AB5C)")
    parser.add_argument("--list", action="store_true", help="List families and exit")
    args = parser.parse_args()

    if args.list:
        for k, cfg in sorted(FAMILIES.items()):
            subs = load_subscales(cfg["prefix"])
            print(f"  {k:10s}: {len(subs):3d} subscales  ({cfg['name']})")
        return

    targets = [args.family] if args.family else sorted(FAMILIES.keys())
    for fam in targets:
        if fam not in FAMILIES:
            print(f"Unknown family: {fam}. Use --list to see options.")
            continue
        build_meta(fam, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
