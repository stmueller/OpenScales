#!/usr/bin/env python3
"""Generate README.md for each scale directory.

Usage:
    python3 generate_readmes.py [scales_directory]

Scans scale directories and generates a README.md in each one based on the
scale definition and translation files.
"""

import json
import os
import sys
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_SCALES_DIR = REPO_ROOT / "scales"


def find_definition_file(scale_dir):
    """Find the main .json definition file."""
    p = Path(scale_dir)
    code = p.name
    definition = p / f"{code}.json"
    if definition.exists():
        return definition, code
    for f in p.glob("*.json"):
        if not re.match(r".+\.\w{2}(-\w+)?\.json$", f.name):
            return f, f.stem
    return None, code


def find_languages(scale_dir, code):
    """Find all available languages."""
    p = Path(scale_dir)
    languages = []
    for f in p.glob(f"{code}.*.json"):
        name = f.name
        if name == f"{code}.json":
            continue
        middle = name[len(code) + 1:-5]
        if middle.startswith("pbl-"):
            lang = middle[4:]
        else:
            lang = middle
        languages.append(lang)
    return sorted(languages)


def load_translation(scale_dir, code, lang):
    """Load a translation file, trying both naming conventions."""
    p = Path(scale_dir)
    # Try new format first
    new_path = p / f"{code}.{lang}.json"
    if new_path.exists():
        with open(new_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # Try legacy format
    legacy_path = p / f"{code}.pbl-{lang}.json"
    if legacy_path.exists():
        with open(legacy_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def strip_html(text):
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()


def generate_readme(scale_dir):
    """Generate README.md for a single scale."""
    def_file, code = find_definition_file(scale_dir)
    if def_file is None:
        return None

    try:
        with open(def_file, "r", encoding="utf-8") as f:
            definition = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    info = definition.get("scale_info", {})
    name = info.get("name", code)
    abbrev = info.get("abbreviation", "")
    description = info.get("description", "")
    citation = info.get("citation", "")
    license_text = info.get("license", "")
    url = info.get("url", "")
    version = info.get("version", "")

    languages = find_languages(scale_dir, code)
    trans = load_translation(scale_dir, code, languages[0] if languages else "en")

    questions = definition.get("questions", [])
    dimensions = definition.get("dimensions", [])
    scoring = definition.get("scoring", {})

    # Count scored questions
    scored_count = sum(1 for q in questions if q.get("type", "") not in ("inst", "image"))

    lines = []

    # Title
    title = name
    if abbrev and abbrev != name:
        title = f"{name} ({abbrev})"
    lines.append(f"# {title}")
    lines.append("")

    if description:
        lines.append(description)
        lines.append("")

    # Screenshot
    screenshot_path = Path(scale_dir) / "screenshot.png"
    if screenshot_path.exists():
        lines.append(f"![{name} Screenshot](screenshot.png)")
        lines.append("")

    # Quick info
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Code:** `{code}`")
    lines.append(f"- **Items:** {scored_count}")
    if languages:
        lines.append(f"- **Languages:** {', '.join(languages)}")
    if version:
        lines.append(f"- **Version:** {version}")
    if license_text:
        lines.append(f"- **License:** {license_text}")
    lines.append("")

    # Dimensions
    if dimensions:
        lines.append("## Dimensions")
        lines.append("")
        lines.append("| ID | Name | Description |")
        lines.append("|----|------|-------------|")
        for dim in dimensions:
            dim_id = dim.get("id", "")
            dim_name = dim.get("name", dim_id)
            dim_desc = dim.get("description", "")
            lines.append(f"| `{dim_id}` | {dim_name} | {dim_desc} |")
        lines.append("")

    # Questions
    lines.append("## Questions")
    lines.append("")
    for q in questions:
        qid = q.get("id", "")
        qtype = q.get("type", "")
        text_key = q.get("text_key", qid)

        if qtype == "inst":
            continue

        text = trans.get(text_key, trans.get(text_key.upper(), text_key))
        text = strip_html(str(text))
        if len(text) > 100:
            text = text[:97] + "..."

        dim = q.get("dimension", "")
        coding = q.get("coding", 1)
        coding_str = ""
        # Check scoring for this item's coding
        for score_def in scoring.values():
            if isinstance(score_def, dict) and "item_coding" in score_def:
                if qid in score_def["item_coding"] and score_def["item_coding"][qid] == -1:
                    coding_str = " (R)"
                    break

        lines.append(f"- **{qid}**{coding_str}: {text}")

    lines.append("")

    # Scoring
    if scoring:
        lines.append("## Scoring")
        lines.append("")
        for score_id, score_def in scoring.items():
            if not isinstance(score_def, dict):
                continue
            method = score_def.get("method", "")
            desc = score_def.get("description", "")
            items = score_def.get("items", [])
            lines.append(f"- **{score_id}**: {method} ({len(items)} items)")
            if desc:
                lines.append(f"  - {desc}")
        lines.append("")

    # Citation
    if citation:
        lines.append("## Citation")
        lines.append("")
        lines.append(citation)
        lines.append("")

    if url:
        lines.append(f"**URL:** {url}")
        lines.append("")

    # Files
    lines.append("## Files")
    lines.append("")
    p = Path(scale_dir)
    for f in sorted(p.iterdir()):
        if f.is_file():
            lines.append(f"- `{f.name}`")
    lines.append("")

    lines.append("---")
    lines.append("*This README was auto-generated by `tools/generate_readmes.py`.*")
    lines.append("")

    return "\n".join(lines)


def main():
    scales_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SCALES_DIR

    if not scales_dir.exists():
        print(f"Error: Scales directory '{scales_dir}' does not exist")
        sys.exit(1)

    count = 0
    for child in sorted(scales_dir.iterdir()):
        if not child.is_dir():
            continue

        readme_content = generate_readme(child)
        if readme_content is None:
            continue

        readme_path = child / "README.md"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)

        print(f"  Generated {readme_path}")
        count += 1

    print(f"\nGenerated {count} README(s)")


if __name__ == "__main__":
    main()
