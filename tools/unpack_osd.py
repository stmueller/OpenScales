#!/usr/bin/env python3
"""Unpack a .osd bundle back into separate definition and translation files.

Required by the PEBL launcher (local and PeblHub), which expects:
  {CODE}.json          — scale definition
  {CODE}.en.json       — English strings
  {CODE}.de.json       — German strings (if present)
  ...

Usage:
  # Unpack into the same directory as the .osd file
  python3 tools/unpack_osd.py GAD7.osd

  # Unpack into a specific output directory
  python3 tools/unpack_osd.py GAD7.osd --output /path/to/output/

  # Unpack only specific languages
  python3 tools/unpack_osd.py GAD7.osd --langs en,de

  # Unpack all .osd files in a directory
  python3 tools/unpack_osd.py --all dist/ --output scales/
"""

import argparse
import json
import sys
from pathlib import Path


def unpack_osd(osd_path: Path, output_dir: Path, langs: list | None = None) -> None:
    """Unpack one .osd file into separate definition and translation files."""
    with open(osd_path, encoding="utf-8") as fh:
        bundle = json.load(fh)

    osd_version = bundle.get("osd_version", "?")
    definition  = bundle.get("definition", {})
    translations = bundle.get("translations", {})

    if not definition:
        raise ValueError(f"No 'definition' key found in {osd_path.name}")

    # Derive the scale code from the definition, falling back to filename stem
    code = (definition.get("scale_info", {}).get("code")
            or osd_path.stem)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write definition
    def_path = output_dir / f"{code}.json"
    with open(def_path, "w", encoding="utf-8") as fh:
        json.dump(definition, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"  Wrote  {def_path.name}")

    # Write each translation
    written_langs = []
    for lang, strings in sorted(translations.items()):
        if langs and lang not in langs:
            continue
        lang_path = output_dir / f"{code}.{lang}.json"
        with open(lang_path, "w", encoding="utf-8") as fh:
            json.dump(strings, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        written_langs.append(lang)
        print(f"  Wrote  {lang_path.name}")

    if not written_langs:
        print(f"  (no translations written — bundle had: {list(translations.keys())})")


def main():
    parser = argparse.ArgumentParser(
        description="Unpack a .osd bundle into separate definition and translation files."
    )
    parser.add_argument("osd_path", nargs="?", help=".osd file to unpack (or dir for --all)")
    parser.add_argument("--output", "-o", help="Output directory (default: same as .osd file)")
    parser.add_argument("--langs",  "-l", help="Comma-separated language codes to extract (default: all)")
    parser.add_argument("--all",    "-a", action="store_true",
                        help="Unpack all .osd files in the given directory")
    args = parser.parse_args()

    langs = [l.strip() for l in args.langs.split(",")] if args.langs else None

    if args.all:
        in_dir = Path(args.osd_path) if args.osd_path else Path(".")
        osd_files = sorted(in_dir.glob("*.osd"))
        if not osd_files:
            print(f"No .osd files found in {in_dir}", file=sys.stderr)
            sys.exit(1)
        for osd_file in osd_files:
            out_dir = Path(args.output) / osd_file.stem if args.output else osd_file.parent / osd_file.stem
            print(f"\n{osd_file.name} → {out_dir}/")
            try:
                unpack_osd(osd_file, out_dir, langs)
            except Exception as exc:
                print(f"  ERROR: {exc}")
    else:
        if not args.osd_path:
            parser.error("Provide a .osd file path or use --all.")
        osd_file = Path(args.osd_path)
        if not osd_file.exists():
            print(f"ERROR: {osd_file} not found", file=sys.stderr)
            sys.exit(1)
        out_dir = Path(args.output) if args.output else osd_file.parent
        print(f"\n{osd_file.name} → {out_dir}/")
        unpack_osd(osd_file, out_dir, langs)


if __name__ == "__main__":
    main()
