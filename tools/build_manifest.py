#!/usr/bin/env python3
"""Build website/manifest.json from scale directories.

Scans every scales/{CODE}/{CODE}.json file and extracts metadata for the
OpenScales website. Writes output to website/manifest.json sorted by name.

Usage:
    python3 tools/build_manifest.py
"""

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
SCALES_DIR = REPO_ROOT / "scales" / "openscales"
OUTPUT_FILE = REPO_ROOT / "website" / "manifest.json"

# Domain keyword mapping — first match wins.
# Match against: name.lower() + ' ' + description.lower() + ' ' + code.lower()
DOMAIN_MAP = [
    (['depression', 'depressive', 'cesd', 'phq', 'dass'], 'Mental Health'),
    (['anxiety', 'worry', 'gad', 'pswq', 'ptsd', 'trauma', 'post-traumatic', 'perceived stress', 'psq',
      'paranoid', 'paranoia', 'agoraphob', 'phobia', 'panic', 'obsessive', 'compulsive', 'ocd', 'moci',
      'autism', 'adhd', 'dissociat', 'borderline', 'misophonia', 'distress'], 'Mental Health'),
    (['personality', 'big five', 'ipip', 'bfi', 'hexaco', 'neo-pi'], 'Personality'),
    (['sleep', 'insomnia', 'somnolence'], 'Health'),
    (['alcohol', 'drinking', 'substance', 'drug', 'marijuana', 'cannabis', 'smoking'], 'Substance Use'),
    (['cardiac', 'cardiovascular', 'health', 'physical', 'pain', 'quality of life', 'qol',
      'kidney', 'epilepsy', 'vision', 'asthma', 'fatigue', 'simulator sickness'], 'Health'),
    (['well-being', 'wellbeing', 'flourishing', 'satisfaction', 'happiness', 'who-5', 'who5',
      'positive functioning', 'positive self', 'psychological functioning'], 'Well-being'),
    (['social', 'support', 'loneliness', 'relationship', 'interpersonal'], 'Social'),
    (['smartphone', 'gaming', 'internet', 'media', 'screen', 'addiction'], 'Technology'),
    (['self-esteem', 'resilience', 'coping', 'efficacy', 'self-monitoring',
      'grit', 'optimism', 'locus of control', 'emotion regulation', 'mindfulness'], 'Self & Coping'),
    (['usability', 'user experience', 'ux', 'sus', 'ueq', 'explanation',
      'cognitive load', 'cognitive reflection'], 'Technology'),
    (['eating', 'body image', 'weight', 'cia', 'clinical impairment'], 'Mental Health'),
    (['trust', 'ai', 'xai'], 'Technology'),
]


def derive_domain(code: str, name: str, description: str) -> str:
    """Derive a domain label by keyword matching."""
    haystack = f"{code} {name} {description}".lower()
    for keywords, domain in DOMAIN_MAP:
        for kw in keywords:
            if kw in haystack:
                return domain
    return 'Other'


def load_osd_bundle(osd_path: Path) -> dict | None:
    """Load and return the parsed bundle dict from a .osd file, or None on error."""
    try:
        with open(osd_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def find_definition_file(scale_dir: Path):
    """Return (path_or_None, code, bundle_or_None) for the scale definition.

    Returns (json_path, code, None) when a separate {CODE}.json exists.
    Returns (None, code, bundle)   when only a {CODE}.osd bundle is present.
    Returns (None, code, None)     when neither is found.
    """
    code = scale_dir.name
    candidate = scale_dir / f"{code}.json"
    if candidate.exists():
        return candidate, code, None
    # Try .osd bundle
    osd_candidate = scale_dir / f"{code}.osd"
    if osd_candidate.exists():
        bundle = load_osd_bundle(osd_candidate)
        if bundle and "definition" in bundle:
            return None, code, bundle
        # Flat-format OSD (no definition wrapper) — synthesise bundle with scale_info
        if bundle and "items" in bundle and "scale_info" not in bundle:
            scale_info = {k: bundle[k] for k in
                ("code","name","abbreviation","description","citation","license","version","url")
                if k in bundle}
            definition = dict(bundle)
            definition["scale_info"] = scale_info
            bundle = {"definition": definition, "translations": bundle.get("translations", {})}
            return None, code, bundle
    # Fallback: any .json that doesn't look like a translation file
    for f in scale_dir.glob("*.json"):
        if not re.match(r".+\.\w{2}(-\w+)?\.json$", f.name):
            return f, f.stem, None
    return None, code, None


def find_languages(scale_dir: Path, code: str, bundle: dict | None = None) -> list:
    """Find all available language codes.

    Checks {CODE}.*.json files first; falls back to bundle['translations'] keys.
    """
    languages = []
    for f in scale_dir.glob(f"{code}.*.json"):
        if f.name == f"{code}.json":
            continue
        middle = f.name[len(code) + 1:-5]  # strip "{code}." prefix and ".json" suffix
        if middle.startswith("pbl-"):
            lang = middle[4:]
        else:
            lang = middle
        languages.append(lang)
    if not languages and bundle:
        for lang in bundle.get("translations", {}).keys():
            languages.append(lang)
    return sorted(languages)


def count_items(definition: dict) -> int:
    """Count scorable items (exclude inst/image types)."""
    count = 0
    for item in definition.get("items", []):
        if isinstance(item, dict):
            if item.get("type", "") not in ("inst", "image"):
                count += 1
    # Fallback: count from questions key (older format)
    if count == 0:
        for q in definition.get("items") or definition.get("questions", []):
            if isinstance(q, dict):
                if q.get("type", "") not in ("inst", "image"):
                    count += 1
    return count


def get_dimensions(definition: dict) -> list:
    """Return list of {id, name} dicts for each dimension."""
    result = []
    for dim in definition.get("dimensions", []):
        if isinstance(dim, dict) and "id" in dim:
            result.append({
                "id": dim["id"],
                "name": dim.get("name", dim["id"])
            })
    return result


def process_scale(scale_dir: Path) -> dict | None:
    """Process one scale directory and return a manifest entry or None."""
    def_file, code, bundle = find_definition_file(scale_dir)
    if def_file is None and bundle is None:
        print(f"  WARNING: No definition file found in {scale_dir.name}, skipping.")
        return None

    try:
        if def_file is not None:
            with open(def_file, "r", encoding="utf-8") as fh:
                definition = json.load(fh)
        else:
            definition = bundle["definition"]
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  WARNING: Cannot parse {def_file}: {exc}")
        return None

    info = definition.get("scale_info", {})

    name = info.get("name", code)
    abbreviation = info.get("abbreviation", "")
    description = info.get("description", "")
    citation = info.get("citation", "")
    license_ = info.get("license", "")
    license_explanation = info.get("license_explanation", "")
    version = info.get("version", "1.0")
    url = info.get("url", "")

    items_count = count_scored_questions_compat(definition)
    dimensions = get_dimensions(definition)
    languages = find_languages(scale_dir, code, bundle)
    has_screenshot = (scale_dir / "screenshot.png").exists()

    # Domain detection: check definition's scale_info first, then keyword match
    if "domain" in info:
        domain = info["domain"]
    else:
        domain = derive_domain(code, name, description)

    return {
        "code": code,
        "name": name,
        "abbreviation": abbreviation,
        "description": description,
        "citation": citation,
        "license": license_,
        "license_explanation": license_explanation,
        "version": version,
        "url": url,
        "items_count": items_count,
        "dimensions": dimensions,
        "languages": languages,
        "has_screenshot": has_screenshot,
        "domain": domain,
    }


def count_scored_questions_compat(definition: dict) -> int:
    """Count scorable items supporting both 'items' and 'questions' keys."""
    SKIP_TYPES = {"inst", "image"}
    count = 0
    for item in definition.get("items", []):
        if isinstance(item, dict) and item.get("type", "") not in SKIP_TYPES:
            count += 1
    if count == 0:
        for q in definition.get("items") or definition.get("questions", []):
            if isinstance(q, dict) and q.get("type", "") not in SKIP_TYPES:
                count += 1
    return count


def build_manifest() -> list:
    """Scan all scale directories and return sorted manifest list."""
    if not SCALES_DIR.exists():
        print(f"ERROR: Scales directory not found: {SCALES_DIR}")
        sys.exit(1)

    scales = []
    for child in sorted(SCALES_DIR.iterdir()):
        if not child.is_dir():
            continue
        entry = process_scale(child)
        if entry is not None:
            scales.append(entry)

    # Sort by name
    scales.sort(key=lambda s: s["name"].lower())
    return scales


def main():
    print(f"Scanning {SCALES_DIR} ...")
    scales = build_manifest()

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(scales, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # Summary
    domains = sorted(set(s["domain"] for s in scales))
    all_langs = sorted(set(lang for s in scales for lang in s["languages"]))

    print(f"\nWrote {OUTPUT_FILE}")
    print(f"  Scales found   : {len(scales)}")
    print(f"  Domains covered: {len(domains)}  ({', '.join(domains)})")
    print(f"  Languages found: {len(all_langs)}  ({', '.join(all_langs)})")
    print()
    for s in scales:
        langs = ", ".join(s["languages"]) or "—"
        print(f"  [{s['domain']:15s}]  {s['code']:20s}  {s['name']}  ({s['items_count']} items) [{langs}]")


if __name__ == "__main__":
    main()
