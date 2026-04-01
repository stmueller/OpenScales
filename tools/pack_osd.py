#!/usr/bin/env python3
"""Pack an OSD scale directory into a single .osd bundle file.

An .osd file is a JSON envelope containing the scale definition and all
available translations in one file, suitable for hosting and distribution.

Structure:
  {
    "osd_version": "1.0",
    "definition": { ...{CODE}.json contents... },
    "translations": {
      "en": { ...{CODE}.en.json contents... },
      "de": { ...{CODE}.de.json contents... },
      ...
    }
  }

Usage:
  # Pack a single scale (writes {CODE}.osd alongside the source files)
  python3 tools/pack_osd.py GAD7

  # Pack from a specific input directory, write to a specific output path
  python3 tools/pack_osd.py GAD7 --input openscales/scales/GAD7 --output dist/GAD7.osd

  # Pack all scales in a directory tree
  python3 tools/pack_osd.py --all --input openscales/scales --output dist/
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT  = SCRIPT_DIR.parent
OSD_VERSION = "1.0"


def find_scale_dir(code: str, input_dir: Path | None) -> Path:
    """Locate the scale directory given a code and optional base path."""
    if input_dir:
        candidate = Path(input_dir)
        if candidate.is_dir():
            return candidate
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    # Search default locations
    for search_root in [
        REPO_ROOT / "openscales" / "scales",
        REPO_ROOT / "restricted",
        REPO_ROOT / "data" / "phenx_448" / "osd_output",
    ]:
        candidate = search_root / code
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"Cannot find scale directory for '{code}'. "
        "Use --input to specify the directory."
    )


def find_translations(scale_dir: Path, code: str) -> dict:
    """Collect all translation files for a scale code.

    Handles both OSD format ({CODE}.{lang}.json) and legacy PEBL battery format
    ({CODE}.pbl-{lang}.json).  In both cases the key stored is the bare language
    code (e.g. "en").
    """
    translations = {}
    for f in sorted(scale_dir.glob(f"{code}.*.json")):
        middle = f.name[len(code) + 1 : -5]  # strip "{code}." prefix and ".json" suffix
        # Legacy PEBL format: {CODE}.pbl-{lang}.json  →  lang = middle[4:]
        if middle.startswith("pbl-"):
            lang = middle[4:]
            if re.match(r'^[a-z]{2}(-[A-Za-z]{2,4})?$', lang):
                with open(f, encoding="utf-8") as fh:
                    translations[lang] = json.load(fh)
        # OSD format: {CODE}.{lang}.json  (e.g. GAD7.en.json → "en")
        elif re.match(r'^[a-z]{2}(-[A-Za-z]{2,4})?$', middle):
            with open(f, encoding="utf-8") as fh:
                translations[middle] = json.load(fh)
    return translations


def pack_scale(code: str, scale_dir: Path, output_path: Path,
               delete_source: bool = False) -> None:
    """Pack one scale directory into a .osd file."""
    def_file = scale_dir / f"{code}.json"
    if not def_file.exists():
        # Fallback: any .json that isn't a translation
        candidates = [f for f in scale_dir.glob("*.json")
                      if not re.match(r'.+\.[a-z]{2}(-\w+)?\.json$', f.name)]
        if not candidates:
            raise FileNotFoundError(f"No definition file found in {scale_dir}")
        def_file = candidates[0]

    with open(def_file, encoding="utf-8") as fh:
        definition = json.load(fh)

    translations = find_translations(scale_dir, code)

    bundle = {
        "osd_version": OSD_VERSION,
        "definition":  definition,
        "translations": translations,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    lang_list = ", ".join(translations.keys()) or "(none)"
    print(f"  Packed  {output_path.name}  [{lang_list}]")

    if delete_source:
        # Remove the definition file and all translation files (both formats).
        # Scan for any {code}.*.json to catch both .en.json and .pbl-en.json.
        deleted = []
        if def_file.exists():
            def_file.unlink()
            deleted.append(def_file.name)
        for f in sorted(scale_dir.glob(f"{code}.*.json")):
            # This covers {code}.en.json and {code}.pbl-en.json alike
            f.unlink()
            deleted.append(f.name)
        if deleted:
            print(f"  Deleted {', '.join(deleted)}")


def main():
    parser = argparse.ArgumentParser(
        description="Pack OSD scale files into a single .osd bundle."
    )
    parser.add_argument("code", nargs="?", help="Scale code (e.g. GAD7)")
    parser.add_argument("--input",  "-i", help="Input scale directory (or base dir for --all)")
    parser.add_argument("--output", "-o", help="Output .osd path (or output dir for --all)")
    parser.add_argument("--all",    "-a", action="store_true",
                        help="Pack all scales found under --input directory")
    parser.add_argument("--delete-source", "-d", action="store_true",
                        help="Delete source {CODE}.json and {CODE}.*.json after packing")
    args = parser.parse_args()

    if args.all:
        base_in  = Path(args.input) if args.input else REPO_ROOT / "openscales" / "scales"
        base_out = Path(args.output) if args.output else None  # None = in-place (inside each subdir)
        if not base_in.is_dir():
            print(f"ERROR: {base_in} is not a directory", file=sys.stderr)
            sys.exit(1)
        count = 0
        for child in sorted(base_in.iterdir()):
            if not child.is_dir():
                continue
            code = child.name
            def_file = child / f"{code}.json"
            if not def_file.exists():
                continue
            # In-place: write {CODE}.osd inside each scale subdirectory
            # External output dir: write {CODE}.osd flat inside base_out
            out = (base_out / f"{code}.osd") if base_out else (child / f"{code}.osd")
            try:
                pack_scale(code, child, out, delete_source=args.delete_source)
                count += 1
            except Exception as exc:
                print(f"  WARNING: {code}: {exc}")
        action = "converted" if args.delete_source else "packed"
        dest_label = str(base_out) if base_out else "each scale directory"
        print(f"\n{action.capitalize()} {count} scales into {dest_label}")
    else:
        if not args.code:
            parser.error("Provide a scale CODE or use --all.")
        code = args.code
        scale_dir = find_scale_dir(code, args.input)
        output_path = Path(args.output) if args.output else scale_dir / f"{code}.osd"
        pack_scale(code, scale_dir, output_path, delete_source=args.delete_source)


if __name__ == "__main__":
    main()
