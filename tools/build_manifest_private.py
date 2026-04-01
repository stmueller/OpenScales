#!/usr/bin/env python3
"""Build website/manifest_private.json from private/ scale directories.

Scans every private/{CODE}/{CODE}.json file and extracts metadata for the
OpenScales website. Writes output to website/manifest_private.json sorted by name.

Usage:
    python3 tools/build_manifest_private.py
"""

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT   = SCRIPT_DIR.parent
SCALES_DIR  = REPO_ROOT / "scales" / "private"
OUTPUT_FILE = REPO_ROOT / "website" / "manifest_private.json"

# Directories to skip (not scale subdirectories)
SKIP_DIRS = set()


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
    # Fallback: any .json that doesn't look like a translation file
    for f in scale_dir.glob("*.json"):
        if not re.match(r".+\.[a-z]{2}(-\w+)?\.json$", f.name):
            return f, f.stem, None
    return None, code, None


def find_languages(scale_dir: Path, code: str, bundle: dict | None = None) -> list:
    """Find all available language codes.

    Checks {CODE}.*.json files first; falls back to bundle['translations'] keys.
    """
    languages = []
    for f in scale_dir.glob(f"{code}.*.json"):
        middle = f.name[len(code) + 1:-5]  # strip "{code}." prefix and ".json" suffix
        if re.match(r'^[a-z]{2}(-\w+)?$', middle):
            languages.append(middle)
    if not languages and bundle:
        for lang in bundle.get("translations", {}).keys():
            languages.append(lang)
    return sorted(languages)


def count_scored_items(definition: dict) -> int:
    """Count scorable items (exclude inst/image types)."""
    SKIP_TYPES = {"inst", "image"}
    count = 0
    for item in definition.get("items", []):
        if isinstance(item, dict) and item.get("type", "") not in SKIP_TYPES:
            count += 1
    if count == 0:
        for q in definition.get("questions", []):
            if isinstance(q, dict) and q.get("type", "") not in SKIP_TYPES:
                count += 1
    return count


def get_dimensions(definition: dict) -> list:
    """Return list of {id, name} dicts for each dimension."""
    result = []
    for dim in definition.get("dimensions", []):
        if isinstance(dim, dict) and "id" in dim:
            result.append({"id": dim["id"], "name": dim.get("name", dim["id"])})
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

    name         = info.get("name", code)
    abbreviation = info.get("abbreviation", "")
    description  = info.get("description", "")
    citation     = info.get("citation", "")
    license_     = info.get("license", "")
    version      = info.get("version", "1.0")
    url          = info.get("url", "")
    domain       = info.get("domain", "Other")

    items_count    = count_scored_items(definition)
    dimensions     = get_dimensions(definition)
    languages      = find_languages(scale_dir, code, bundle)
    has_screenshot = (scale_dir / "screenshot.png").exists()

    return {
        "code":           code,
        "name":           name,
        "abbreviation":   abbreviation,
        "description":    description,
        "citation":       citation,
        "license":        license_,
        "version":        version,
        "url":            url,
        "items_count":    items_count,
        "dimensions":     dimensions,
        "languages":      languages,
        "has_screenshot": has_screenshot,
        "domain":         domain,
    }


def build_manifest() -> list:
    """Scan all scale directories and return sorted manifest list."""
    if not SCALES_DIR.exists():
        print(f"ERROR: Scales directory not found: {SCALES_DIR}")
        sys.exit(1)

    scales = []
    for child in sorted(SCALES_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith('.') or child.name in SKIP_DIRS:
            continue
        # Skip directories with no scale data files (JSON or OSD)
        if not any(child.glob("*.json")) and not any(child.glob("*.osd")):
            continue
        entry = process_scale(child)
        if entry is not None:
            scales.append(entry)

    scales.sort(key=lambda s: s["name"].lower())
    return scales


def main():
    print(f"Scanning {SCALES_DIR} ...")
    scales = build_manifest()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(scales, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    domains   = sorted(set(s["domain"] for s in scales))
    all_langs = sorted(set(lang for s in scales for lang in s["languages"]))

    print(f"\nWrote {OUTPUT_FILE}")
    print(f"  Scales found   : {len(scales)}")
    print(f"  Domains covered: {len(domains)}  ({', '.join(domains)})")
    print(f"  Languages found: {len(all_langs)}  ({', '.join(all_langs) or '—'})")
    print()
    for s in scales:
        langs = ", ".join(s["languages"]) or "—"
        print(f"  [{s['domain']:20s}]  {s['code']:15s}  {s['name']}  ({s['items_count']} items) [{langs}]")


if __name__ == "__main__":
    main()
