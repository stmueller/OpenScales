#!/usr/bin/env python3
"""Add implementation metadata to all .osd files that don't already have it."""

import json
import os
import sys
import glob

IMPLEMENTATION = {
    "author": "Shane T. Mueller",
    "organization": "OpenScales Project",
    "date": "2026-04-01",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/"
}

def add_implementation(filepath):
    """Add implementation block to an .osd file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"  SKIP (parse error): {filepath}: {e}")
        return False

    # Navigate to definition
    if 'definition' not in data:
        print(f"  SKIP (no definition): {filepath}")
        return False

    defn = data['definition']

    # Skip if already has implementation
    if 'implementation' in defn:
        print(f"  SKIP (already has implementation): {filepath}")
        return False

    # Insert implementation after scale_info
    # Rebuild the definition dict to control key order
    new_defn = {}
    inserted = False
    for key, val in defn.items():
        new_defn[key] = val
        if key == 'scale_info' and not inserted:
            new_defn['implementation'] = IMPLEMENTATION.copy()
            inserted = True

    # If scale_info wasn't found, just append
    if not inserted:
        new_defn['implementation'] = IMPLEMENTATION.copy()

    data['definition'] = new_defn

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')

    return True


def main():
    search_paths = [
        '/home/smueller/Dropbox/Research/pebl/OpenScales/scales/',
        '/home/smueller/Dropbox/Research/pebl/pebl/media/apps/scales/definitions/',
    ]

    total = 0
    updated = 0
    skipped = 0

    for base in search_paths:
        for filepath in sorted(glob.glob(os.path.join(base, '**/*.osd'), recursive=True)):
            total += 1
            if add_implementation(filepath):
                updated += 1
            else:
                skipped += 1

    print(f"\nDone: {updated} updated, {skipped} skipped, {total} total")


if __name__ == '__main__':
    main()
