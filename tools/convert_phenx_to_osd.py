#!/usr/bin/env python3
"""Convert PhenX split-file directories to .osd bundles and rename directories.

PhenX directories currently use a split-file layout:
    scales/phenx/010201/
        PX010201.json       ← definition
        PX010201.en.json    ← English translation

This script packs each into a single .osd bundle:
    scales/phenx/PX010201/
        PX010201.osd        ← bundle (definition + translations)

Then deletes the split files and renames the directory from {ID}/ to PX{ID}/.
After running, the phenx collection matches the same layout as openscales/ and
restricted/, so the runner and repos.php can use the same osd format for all three.

Usage:
    python3 tools/convert_phenx_to_osd.py
    python3 tools/convert_phenx_to_osd.py --dry-run
    python3 tools/convert_phenx_to_osd.py --input /path/to/scales/phenx
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent
REPO_ROOT   = SCRIPT_DIR.parent
OSD_VERSION = "1.0"


def pack_phenx_dir(old_dir: Path, dry_run: bool = False) -> bool:
    """Pack one PhenX directory. Returns True on success."""
    dir_id = old_dir.name                  # e.g. "010201"
    code   = "PX" + dir_id                 # e.g. "PX010201"
    new_dir = old_dir.parent / code        # scales/phenx/PX010201

    def_file = old_dir / f"{code}.json"
    if not def_file.exists():
        print(f"  SKIP  {dir_id}: {code}.json not found")
        return False

    # Load definition
    with open(def_file, encoding="utf-8") as fh:
        definition = json.load(fh)

    # Collect all translations: {code}.{lang}.json
    translations = {}
    for f in sorted(old_dir.glob(f"{code}.*.json")):
        lang = f.name[len(code) + 1 : -5]   # strip "PX010201." and ".json"
        with open(f, encoding="utf-8") as fh:
            translations[lang] = json.load(fh)

    bundle = {
        "osd_version":  OSD_VERSION,
        "definition":   definition,
        "translations": translations,
    }

    osd_path = old_dir / f"{code}.osd"
    langs    = ", ".join(translations.keys()) or "(none)"

    if dry_run:
        target = new_dir / f"{code}.osd"
        print(f"  DRY   {dir_id}/ → {code}/ → {code}.osd  [{langs}]")
        return True

    # Write the bundle
    with open(osd_path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # Delete split files
    def_file.unlink()
    for f in sorted(old_dir.glob(f"{code}.*.json")):
        f.unlink()

    # Rename directory: 010201/ → PX010201/
    old_dir.rename(new_dir)

    print(f"  OK    {dir_id}/ → {code}/  [{langs}]")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Convert PhenX split-file dirs to .osd bundles and rename them."
    )
    parser.add_argument("--input", "-i",
                        help="Path to scales/phenx directory (default: scales/phenx/ in repo)")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would happen without making changes")
    args = parser.parse_args()

    phenx_dir = Path(args.input) if args.input else REPO_ROOT / "scales" / "phenx"
    if not phenx_dir.is_dir():
        print(f"ERROR: {phenx_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"{'DRY RUN — ' if args.dry_run else ''}Converting PhenX in: {phenx_dir}")
    print()

    ok = skip = 0
    # Only process directories named with 6-digit IDs (not already PX-prefixed)
    candidates = sorted(
        d for d in phenx_dir.iterdir()
        if d.is_dir() and d.name.isdigit()
    )

    if not candidates:
        # Maybe they're already named PX...
        already = sum(1 for d in phenx_dir.iterdir() if d.is_dir() and d.name.startswith("PX"))
        if already:
            print(f"Nothing to do — {already} directories already have PX prefix.")
        else:
            print("No convertible directories found.")
        return

    for d in candidates:
        if pack_phenx_dir(d, dry_run=args.dry_run):
            ok += 1
        else:
            skip += 1

    print()
    action = "Would convert" if args.dry_run else "Converted"
    print(f"{action} {ok} directories, skipped {skip}.")
    if args.dry_run:
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
