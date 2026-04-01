#!/usr/bin/env python3
"""
osd_loader.py — Shared helper to load scale definitions from .osd or legacy .json format.

Used by all convert_to_*.py scripts. Provides a unified interface regardless
of whether the scale is in the new .osd format or the old .json + translation files.

Returns a normalized dict with:
  - 'definition': the scale definition (scale_info, items, likert_options, scoring, etc.)
  - 'translations': dict of {lang: {key: text}}
  - 'code': the scale code
"""

import json
import re
import os
from pathlib import Path


def load_scale(scale_dir, lang='en'):
    """Load a scale from a directory, supporting both .osd and legacy .json formats.

    Returns (definition_dict, translations_dict, code_string)
    """
    p = Path(scale_dir)

    # Try .osd first (new format)
    osd_files = sorted(p.glob('*.osd'))
    if osd_files:
        return _load_osd(osd_files[0], lang)

    # Fall back to legacy .json
    json_file, code = _find_legacy_json(p)
    if json_file:
        return _load_legacy(json_file, p, code, lang)

    raise FileNotFoundError(f"No .osd or .json definition file found in '{scale_dir}'")


def _load_osd(osd_path, lang):
    """Load from .osd format (single file with embedded translations)."""
    with open(osd_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    defn = data.get('definition', data)  # handle both wrapped and unwrapped
    translations = data.get('translations', {})
    code = defn.get('scale_info', {}).get('code', osd_path.stem)

    # Build a flat translation dict for the requested language
    trans = translations.get(lang, {})
    if not trans:
        # Try first available language
        available = list(translations.keys())
        if available:
            trans = translations[available[0]]

    return defn, translations, code


def _find_legacy_json(p):
    """Find the main .json definition file (not a translation file)."""
    code = p.name

    # Try {code}.json first
    definition = p / f"{code}.json"
    if definition.exists():
        return definition, code

    # Try any .json that isn't a translation file ({code}.{lang}.json)
    for f in sorted(p.glob("*.json")):
        if not re.match(r".*\.\w{2}(-\w+)?\.json$", f.name):
            return f, f.stem

    return None, None


def _load_legacy(json_file, p, code, lang):
    """Load from legacy .json + separate translation files."""
    with open(json_file, 'r', encoding='utf-8') as f:
        defn = json.load(f)

    # Load translations from separate file
    translations = {}
    for pattern in [f"{code}.{lang}.json", f"{code}.pbl-{lang}.json"]:
        trans_path = p / pattern
        if trans_path.exists():
            with open(trans_path, 'r', encoding='utf-8') as f:
                translations[lang] = json.load(f)
            break

    # Also try to load all available translation files
    for tf in p.glob(f"{code}.*.json"):
        m = re.match(rf"{re.escape(code)}\.(\w{{2}}(?:-\w+)?)\.json$", tf.name)
        if m:
            lang_code = m.group(1)
            if lang_code not in translations:
                with open(tf, 'r', encoding='utf-8') as f:
                    translations[lang_code] = json.load(f)

    for tf in p.glob(f"{code}.pbl-*.json"):
        m = re.match(rf"{re.escape(code)}\.pbl-(\w{{2}}(?:-\w+)?)\.json$", tf.name)
        if m:
            lang_code = m.group(1)
            if lang_code not in translations:
                with open(tf, 'r', encoding='utf-8') as f:
                    translations[lang_code] = json.load(f)

    return defn, translations, code
