#!/usr/bin/env python3
"""
apply_phenx_scoring.py — Merge hand-coded scoring stubs into PhenX OSD bundles.

Each PhenX scale directory may contain a {CODE}.scoring.json file with
hand-coded dimensions and scoring that the automated REDCap converter
cannot produce.  After rebuilding .osd files from a new PhenX export,
run this script to overlay the scoring back onto the generated files.

Stub format (scales/phenx/PX{pid}/{CODE}.scoring.json):
    {
      "_note": "...",          // documentation string, ignored by this script
      "dimensions": [...],     // replaces definition.dimensions
      "scoring": { ... }       // replaces definition.scoring
    }

Usage:
    python3 tools/apply_phenx_scoring.py [--scales-dir DIR] [--dry-run] [--verbose]

Run from the repo root.  By default scales-dir = scales/phenx/.

The script reports any scoring item IDs that are no longer present in
the current .osd item list, so you can fix the stub before merging.
"""
import argparse, json, os, sys

BASE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCALES_DIR = os.path.join(BASE, 'scales', 'phenx')


def apply_all(scales_dir, dry_run=False, verbose=False):
    scale_dirs = sorted(d for d in os.listdir(scales_dir) if d.startswith('PX'))

    found = applied = skipped = warn_count = 0
    all_warnings = []

    for code in scale_dirs:
        stub_path = os.path.join(scales_dir, code, f'{code}.scoring.json')
        osd_path  = os.path.join(scales_dir, code, f'{code}.osd')

        if not os.path.exists(stub_path):
            continue
        found += 1

        if not os.path.exists(osd_path):
            print(f"  SKIP {code}: .osd not found")
            skipped += 1
            continue

        stub   = json.load(open(stub_path))
        dims   = stub.get('dimensions', [])
        scoring = stub.get('scoring', {})

        if not dims and not scoring:
            if verbose:
                print(f"  SKIP {code}: stub has no dimensions or scoring")
            skipped += 1
            continue

        bundle = json.load(open(osd_path))
        defn   = bundle.get('definition', bundle)
        item_ids = {i.get('id') for i in defn.get('items', [])}

        # Check for scoring refs that no longer exist
        warnings = []
        for dim_id, block in scoring.items():
            # skip composite dims that reference other scores (not item IDs)
            if block.get('scores'):
                continue
            si = block.get('items', [])
            if isinstance(si, dict):
                si = list(si.keys())
            # also check deprecated item_coding refs
            ic = block.get('item_coding', {})
            si = list(si) + [k for k in ic if k not in si]
            missing = [i for i in si if i not in item_ids]
            if missing:
                warnings.append(f"    {code}/{dim_id}: missing item IDs {missing}")

        if warnings:
            all_warnings += warnings
            warn_count += 1
            print(f"  WARN {code}: scoring refs not found in current items — skipping")
            for w in warnings:
                print(w)
            skipped += 1
            continue

        if not dry_run:
            defn['dimensions'] = dims
            defn['scoring']    = scoring
            if 'definition' in bundle:
                bundle['definition'] = defn
            with open(osd_path, 'w', encoding='utf-8') as f:
                json.dump(bundle, f, indent=2, ensure_ascii=False)

        if verbose:
            ndims = len(dims)
            nblocks = len(scoring)
            print(f"  {'[DRY] ' if dry_run else ''}Applied {code}: {ndims} dim(s), {nblocks} scoring block(s)")
        applied += 1

    print(f"\nStubs found: {found}  Applied: {applied}  Skipped/warned: {skipped + warn_count}")
    if all_warnings:
        print("\nFix the stubs above before re-running (update item IDs to match current .osd).")
    if dry_run:
        print("[DRY RUN — no files written]")


def main():
    p = argparse.ArgumentParser(description='Merge PhenX scoring stubs into .osd bundles')
    p.add_argument('--scales-dir', default=SCALES_DIR,
                   help='Path to scales/phenx/ directory')
    p.add_argument('--dry-run',  action='store_true',
                   help='Parse and validate only; do not write files')
    p.add_argument('--verbose',  action='store_true',
                   help='Print one line per applied scale')
    args = p.parse_args()
    apply_all(os.path.abspath(args.scales_dir),
              dry_run=args.dry_run, verbose=args.verbose)


if __name__ == '__main__':
    main()
