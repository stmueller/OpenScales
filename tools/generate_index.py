#!/usr/bin/env python3
"""Generate index.json catalog from scale directories.

Usage:
    python3 generate_index.py [scales_directory]

Scans the scales/ directory (or specified directory) and produces index.json
in the repository root.
"""

import json
import os
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_SCALES_DIR = REPO_ROOT / "scales"
OUTPUT_FILE = REPO_ROOT / "index.json"

# Features detected from definition content
STANDARD_FEATURES = {
    "visible_when": "conditional_logic",
    "computed": "computed_variables",
    "gate": "screening_gates",
    "feedback": "feedback",
    "norms": "norms",
    "randomize": "randomization",
    "randomize_options": "option_randomization",
    "time_limit_seconds": "timing",
    "min_display_seconds": "timing",
}

ADVANCED_FEATURES = {
    "branches": "branching",
    "item_pools": "item_pools",
    "loop_over": "looping",
    "includes": "composition",
}


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
    """Find all available languages for a scale."""
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


def list_files(scale_dir, code):
    """List all files in the scale directory."""
    p = Path(scale_dir)
    files = []
    for f in sorted(p.iterdir()):
        if f.is_file() and f.name != "README.md":
            files.append(f.name)
    return files


def detect_features(definition):
    """Detect which Standard/Advanced features a scale uses."""
    features = set()
    text = json.dumps(definition)

    # Check top-level keys
    for key, feature in ADVANCED_FEATURES.items():
        if key in definition:
            features.add(feature)

    # Check for norms in scoring
    for score_id, score_def in definition.get("scoring", {}).items():
        if isinstance(score_def, dict) and "norms" in score_def:
            features.add("norms")

    # Check questions for standard features
    for q in definition.get("questions", []):
        if not isinstance(q, dict):
            continue
        for key, feature in STANDARD_FEATURES.items():
            if key in q:
                features.add(feature)
        if "correct" in q:
            features.add("feedback")

    # Check pages for features
    for page in definition.get("pages", []):
        if not isinstance(page, dict):
            continue
        for key, feature in STANDARD_FEATURES.items():
            if key in page:
                features.add(feature)

    # Top-level standard features
    if "computed" in definition:
        features.add("computed_variables")
    if "pages" in definition:
        features.add("pages")

    return sorted(features)


def count_scored_questions(definition):
    """Count questions that are not instructions or display-only."""
    count = 0
    for q in definition.get("questions", []):
        if isinstance(q, dict):
            qtype = q.get("type", "")
            if qtype not in ("inst", "image"):
                count += 1
    return count


def get_dimension_ids(definition):
    """Get list of dimension IDs."""
    dims = []
    for dim in definition.get("dimensions", []):
        if isinstance(dim, dict) and "id" in dim:
            dims.append(dim["id"])
    return dims


def generate_index(scales_dir):
    """Generate the index catalog."""
    scales_dir = Path(scales_dir)
    scales = []

    for child in sorted(scales_dir.iterdir()):
        if not child.is_dir():
            continue

        def_file, code = find_definition_file(child)
        if def_file is None:
            continue

        try:
            with open(def_file, "r", encoding="utf-8") as f:
                definition = json.load(f)
        except (json.JSONDecodeError, OSError):
            print(f"  WARNING: Skipping {child.name} (invalid JSON)")
            continue

        info = definition.get("scale_info", {})
        languages = find_languages(child, code)
        files = list_files(child, code)
        features = detect_features(definition)
        question_count = count_scored_questions(definition)
        dimensions = get_dimension_ids(definition)

        scale_entry = {
            "code": info.get("code", code),
            "name": info.get("name", code),
        }

        if info.get("description"):
            scale_entry["description"] = info["description"]
        if info.get("citation"):
            scale_entry["author"] = info["citation"].split("(")[0].strip().rstrip(",")
        scale_entry["question_count"] = question_count
        if dimensions:
            scale_entry["dimensions"] = dimensions
        scale_entry["languages"] = languages
        scale_entry["version"] = info.get("version", "1.0")
        if info.get("license"):
            scale_entry["license"] = info["license"]
        if features:
            scale_entry["features"] = features
        scale_entry["has_screenshot"] = (child / "screenshot.png").exists()
        scale_entry["files"] = files

        scales.append(scale_entry)

    index = {
        "format_version": 1,
        "spec_version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scales": scales,
    }

    return index


def main():
    scales_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SCALES_DIR

    if not scales_dir.exists():
        print(f"Error: Scales directory '{scales_dir}' does not exist")
        sys.exit(1)

    print(f"Scanning {scales_dir}...")
    index = generate_index(scales_dir)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Generated {OUTPUT_FILE} with {len(index['scales'])} scale(s)")

    # Print summary
    for scale in index["scales"]:
        langs = ", ".join(scale.get("languages", []))
        print(f"  {scale['code']}: {scale['name']} ({scale['question_count']} items) [{langs}]")


if __name__ == "__main__":
    main()
