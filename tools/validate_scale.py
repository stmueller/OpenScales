#!/usr/bin/env python3
"""Validate a scale directory against the Open Scale Definition (OSD) specification v1.0.

Usage:
    python3 validate_scale.py <scale_directory>
    python3 validate_scale.py scales/grit/
    python3 validate_scale.py scales/        # Validate all scales

Exit codes:
    0 - All validations passed
    1 - Validation errors found
    2 - Usage error
"""

import json
import os
import sys
import re
from pathlib import Path

VALID_QUESTION_TYPES = {
    "inst", "likert", "vas", "grid", "multi", "multicheck",
    "short", "long", "image", "imageresponse",
    # Advanced types
    "rank", "audio", "video", "audioresponse", "videoresponse",
}

SCORING_METHODS = {"mean_coded", "sum_coded", "weighted_sum", "sum_correct"}

PARAMETER_TYPES = {"string", "boolean", "integer", "number", "choice"}

CONDITION_OPERATORS = {
    "equals", "not_equals", "greater_than", "less_than",
    "in", "not_in", "is_answered", "is_not_answered",
}


class ValidationResult:
    def __init__(self, scale_dir):
        self.scale_dir = scale_dir
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    @property
    def passed(self):
        return len(self.errors) == 0

    def summary(self):
        lines = []
        status = "PASS" if self.passed else "FAIL"
        lines.append(f"  [{status}] {self.scale_dir}")
        for e in self.errors:
            lines.append(f"    ERROR: {e}")
        for w in self.warnings:
            lines.append(f"    WARNING: {w}")
        if self.passed and not self.warnings:
            lines.append(f"    No issues found.")
        return "\n".join(lines)


def find_definition_file(scale_dir):
    """Find the main .json definition file in a scale directory."""
    p = Path(scale_dir)
    code = p.name
    definition = p / f"{code}.json"
    if definition.exists():
        return definition, code
    # Try to find any .json that isn't a translation file
    for f in p.glob("*.json"):
        if not re.match(r".+\.\w{2}(-\w+)?\.json$", f.name):
            return f, f.stem
    return None, code


def find_translation_files(scale_dir, code):
    """Find translation files matching {code}.{lang}.json or {code}.pbl-{lang}.json."""
    p = Path(scale_dir)
    translations = {}

    # New format: {code}.{lang}.json
    for f in p.glob(f"{code}.*.json"):
        name = f.name
        if name == f"{code}.json":
            continue
        # Extract language code
        middle = name[len(code) + 1:-5]  # strip "{code}." and ".json"
        if middle.startswith("pbl-"):
            lang = middle[4:]
            translations[lang] = ("legacy", f)
        else:
            lang = middle
            translations[lang] = ("new", f)

    return translations


def load_json(filepath):
    """Load and parse a JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_scale_info(definition, result):
    """Validate C1: Scale Metadata."""
    if "scale_info" not in definition:
        result.error("Missing required 'scale_info' object")
        return None

    info = definition["scale_info"]
    if not isinstance(info, dict):
        result.error("'scale_info' must be an object")
        return None

    if "name" not in info or not info["name"]:
        result.error("scale_info.name is required")
    if "code" not in info or not info["code"]:
        result.error("scale_info.code is required")

    # Optional field type checks
    for field in ("abbreviation", "description", "citation", "license", "version", "url"):
        if field in info and not isinstance(info[field], str):
            result.warn(f"scale_info.{field} should be a string")

    return info


def validate_questions(definition, result):
    """Validate C2: Question Types."""
    if "items" not in definition and "questions" not in definition:
        result.error("Missing required 'questions' array")
        return []

    questions = definition.get("items") or definition.get("questions", [])
    if not isinstance(questions, list):
        result.error("'questions' must be an array")
        return []

    question_ids = set()
    dimension_ids = set()
    if "dimensions" in definition:
        for dim in definition.get("dimensions", []):
            if "id" in dim:
                dimension_ids.add(dim["id"])

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            result.error(f"Question {i} must be an object")
            continue

        # Required fields
        if "id" not in q:
            result.error(f"Question {i} missing required 'id' field")
            continue

        qid = q["id"]
        if qid in question_ids:
            result.error(f"Duplicate question ID: '{qid}'")
        question_ids.add(qid)

        if "type" not in q:
            result.error(f"Question '{qid}' missing required 'type' field")
            continue

        qtype = q["type"]
        if qtype not in VALID_QUESTION_TYPES:
            result.warn(f"Question '{qid}' has unknown type '{qtype}'")

        if "text_key" not in q:
            result.error(f"Question '{qid}' missing required 'text_key' field")

        # Dimension reference check
        if "dimension" in q and q["dimension"] is not None:
            if q["dimension"] not in dimension_ids:
                result.error(f"Question '{qid}' references unknown dimension '{q['dimension']}'")

        # Type-specific validation
        if qtype == "likert":
            if "likert_points" not in q:
                # Check if scale-level likert_options provides a default
                if "likert_options" not in definition or "points" not in definition.get("likert_options", {}):
                    result.warn(f"Question '{qid}' (likert) has no likert_points and no scale-level default")

        elif qtype in ("multi", "multicheck"):
            if "options" not in q:
                result.error(f"Question '{qid}' ({qtype}) missing required 'options' field")
            elif isinstance(q["options"], list):
                for j, opt in enumerate(q["options"]):
                    if isinstance(opt, dict):
                        if "value" not in opt:
                            result.error(f"Question '{qid}' option {j} missing 'value'")
                        if "text_key" not in opt:
                            result.error(f"Question '{qid}' option {j} missing 'text_key'")

        elif qtype == "grid":
            if "rows" not in q and "columns" not in q:
                result.warn(f"Question '{qid}' (grid) has no rows or columns defined")

        elif qtype in ("image", "imageresponse"):
            if "image_file" not in q and "image" not in q:
                result.warn(f"Question '{qid}' ({qtype}) has no image_file specified")

        # Coding validation
        if "coding" in q and q["coding"] not in (0, 1, -1):
            result.warn(f"Question '{qid}' has unusual coding value: {q['coding']}")

    return list(question_ids)


def validate_dimensions(definition, result):
    """Validate C3: Dimensions."""
    if "dimensions" not in definition:
        return []

    dimensions = definition["dimensions"]
    if not isinstance(dimensions, list):
        result.error("'dimensions' must be an array")
        return []

    dim_ids = set()
    for i, dim in enumerate(dimensions):
        if not isinstance(dim, dict):
            result.error(f"Dimension {i} must be an object")
            continue
        if "id" not in dim:
            result.error(f"Dimension {i} missing required 'id' field")
            continue
        if "name" not in dim:
            result.warn(f"Dimension '{dim['id']}' missing 'name' field")
        if dim["id"] in dim_ids:
            result.error(f"Duplicate dimension ID: '{dim['id']}'")
        dim_ids.add(dim["id"])

    return list(dim_ids)


def validate_scoring(definition, question_ids, result):
    """Validate C3: Scoring."""
    if "scoring" not in definition:
        return

    scoring = definition["scoring"]
    if not isinstance(scoring, dict):
        result.error("'scoring' must be an object")
        return

    for score_id, score_def in scoring.items():
        if not isinstance(score_def, dict):
            result.error(f"Scoring '{score_id}' must be an object")
            continue

        if "method" not in score_def:
            result.error(f"Scoring '{score_id}' missing required 'method' field")
        elif score_def["method"] not in SCORING_METHODS:
            result.warn(f"Scoring '{score_id}' has unknown method '{score_def['method']}'")

        if "items" not in score_def:
            result.error(f"Scoring '{score_id}' missing required 'items' array")
        elif isinstance(score_def["items"], list):
            for item_id in score_def["items"]:
                if item_id not in question_ids:
                    result.error(f"Scoring '{score_id}' references unknown question '{item_id}'")

        # Validate item_coding references
        if "item_coding" in score_def and isinstance(score_def["item_coding"], dict):
            for item_id, coding in score_def["item_coding"].items():
                if item_id not in question_ids:
                    result.error(f"Scoring '{score_id}' item_coding references unknown question '{item_id}'")
                if coding not in (1, -1):
                    result.warn(f"Scoring '{score_id}' item_coding for '{item_id}' has unusual value: {coding}")

        # Method-specific checks
        method = score_def.get("method")
        if method == "weighted_sum" and "weights" not in score_def:
            result.warn(f"Scoring '{score_id}' uses weighted_sum but has no 'weights'")
        if method == "sum_correct" and "correct_answers" not in score_def:
            result.error(f"Scoring '{score_id}' uses sum_correct but has no 'correct_answers'")


def validate_translations(definition, translations, question_ids, result):
    """Validate C4: Translations."""
    if not translations:
        result.error("No translation files found")
        return

    # Collect all text_key references from the definition
    required_keys = set()
    for q in definition.get("items") or definition.get("questions", []):
        if "text_key" in q:
            required_keys.add(q["text_key"])
        if "likert_labels" in q:
            required_keys.update(q["likert_labels"])
        if "options" in q and isinstance(q["options"], list):
            for opt in q["options"]:
                if isinstance(opt, dict) and "text_key" in opt:
                    required_keys.add(opt["text_key"])
        for key_field in ("min_label", "max_label", "left", "right"):
            if key_field in q:
                required_keys.add(q[key_field])

    # Likert option labels
    likert_opts = definition.get("likert_options", {})
    if "labels" in likert_opts:
        required_keys.update(likert_opts["labels"])
    if "question_head" in likert_opts:
        required_keys.add(likert_opts["question_head"])

    # Page title keys
    for page in definition.get("pages", []):
        if "title_key" in page:
            required_keys.add(page["title_key"])

    # Check each translation file
    for lang, (fmt, filepath) in translations.items():
        if fmt == "legacy":
            result.warn(f"Translation file uses legacy naming (.pbl-{lang}); consider renaming to .{lang}.json")

        try:
            trans = load_json(filepath)
        except json.JSONDecodeError as e:
            result.error(f"Translation file {filepath.name} is invalid JSON: {e}")
            continue

        if not isinstance(trans, dict):
            result.error(f"Translation file {filepath.name} must be a JSON object")
            continue

        # Check for missing keys
        trans_keys_lower = {k.lower(): k for k in trans.keys()}
        for key in required_keys:
            if key.lower() not in trans_keys_lower and key not in trans:
                result.warn(f"Translation '{lang}' missing key '{key}'")


def validate_parameters(definition, result):
    """Validate C8: Parameters."""
    if "parameters" not in definition:
        return

    params = definition["parameters"]
    if not isinstance(params, dict):
        result.error("'parameters' must be an object")
        return

    for name, param_def in params.items():
        if not isinstance(param_def, dict):
            result.error(f"Parameter '{name}' must be an object")
            continue
        if "type" in param_def and param_def["type"] not in PARAMETER_TYPES:
            result.warn(f"Parameter '{name}' has unknown type '{param_def['type']}'")
        if "default" not in param_def:
            result.warn(f"Parameter '{name}' has no default value")
        if param_def.get("type") == "choice" and "options" not in param_def:
            result.error(f"Parameter '{name}' is type 'choice' but has no 'options'")


def validate_pages(definition, question_ids, result):
    """Validate C5: Pages."""
    if "pages" not in definition:
        return

    pages = definition["pages"]
    if not isinstance(pages, list):
        result.error("'pages' must be an array")
        return

    page_ids = set()
    referenced_items = set()

    for i, page in enumerate(pages):
        if not isinstance(page, dict):
            result.error(f"Page {i} must be an object")
            continue
        if "id" not in page:
            result.error(f"Page {i} missing required 'id' field")
            continue
        if page["id"] in page_ids:
            result.error(f"Duplicate page ID: '{page['id']}'")
        page_ids.add(page["id"])

        if "items" not in page:
            result.error(f"Page '{page['id']}' missing required 'items' field")
        elif isinstance(page["items"], list):
            for item_id in page["items"]:
                if isinstance(item_id, str) and item_id not in question_ids:
                    result.error(f"Page '{page['id']}' references unknown question '{item_id}'")
                referenced_items.add(item_id)

    # Warn about questions not on any page
    unreferenced = set(question_ids) - referenced_items
    if unreferenced and pages:
        result.warn(f"Questions not on any page: {', '.join(sorted(unreferenced))}")


def validate_condition(condition, question_ids, result, context):
    """Validate a visible_when condition object."""
    if not isinstance(condition, dict):
        result.warn(f"{context}: visible_when must be an object")
        return

    if "all" in condition:
        for sub in condition["all"]:
            validate_condition(sub, question_ids, result, context)
    elif "any" in condition:
        for sub in condition["any"]:
            validate_condition(sub, question_ids, result, context)
    else:
        if "question" in condition:
            if condition["question"] not in question_ids:
                result.warn(f"{context}: visible_when references unknown question '{condition['question']}'")
        if "operator" in condition:
            if condition["operator"] not in CONDITION_OPERATORS:
                result.warn(f"{context}: visible_when has unknown operator '{condition['operator']}'")


def validate_scale(scale_dir):
    """Run full validation on a scale directory."""
    result = ValidationResult(scale_dir)

    # Find definition file
    def_file, code = find_definition_file(scale_dir)
    if def_file is None:
        result.error(f"No definition file found (expected {code}.json)")
        return result

    # Load definition
    try:
        definition = load_json(def_file)
    except json.JSONDecodeError as e:
        result.error(f"Definition file is invalid JSON: {e}")
        return result

    if not isinstance(definition, dict):
        result.error("Definition file must be a JSON object")
        return result

    # Validate components
    info = validate_scale_info(definition, result)

    # Check code matches directory name
    if info and "code" in info:
        dir_name = Path(scale_dir).name
        if info["code"] != dir_name:
            result.warn(f"scale_info.code '{info['code']}' doesn't match directory name '{dir_name}'")

    dim_ids = validate_dimensions(definition, result)
    question_ids = validate_questions(definition, result)
    validate_scoring(definition, set(question_ids), result)
    validate_parameters(definition, result)
    validate_pages(definition, set(question_ids), result)

    # Find and validate translations
    translations = find_translation_files(scale_dir, code)
    validate_translations(definition, translations, question_ids, result)

    # Validate visible_when conditions on questions
    for q in definition.get("items") or definition.get("questions", []):
        if "visible_when" in q:
            validate_condition(q["visible_when"], set(question_ids), result, f"Question '{q.get('id', '?')}'")

    # Validate visible_when conditions on pages
    for page in definition.get("pages", []):
        if "visible_when" in page:
            validate_condition(page["visible_when"], set(question_ids), result, f"Page '{page.get('id', '?')}'")

    return result


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    target = sys.argv[1]
    target_path = Path(target)

    if not target_path.exists():
        print(f"Error: '{target}' does not exist")
        sys.exit(2)

    # Determine what to validate
    scale_dirs = []
    if target_path.is_file():
        # Single file — validate its parent directory
        scale_dirs.append(target_path.parent)
    elif find_definition_file(target_path)[0] is not None:
        # This is a scale directory (definition file found)
        scale_dirs.append(target_path)
    else:
        # This might be a parent directory containing scale subdirectories
        for child in sorted(target_path.iterdir()):
            if child.is_dir():
                def_file, _ = find_definition_file(child)
                if def_file is not None:
                    scale_dirs.append(child)

    if not scale_dirs:
        print(f"Error: No scale definitions found in '{target}'")
        sys.exit(2)

    print(f"Validating {len(scale_dirs)} scale(s)...\n")

    all_passed = True
    for scale_dir in scale_dirs:
        result = validate_scale(scale_dir)
        print(result.summary())
        print()
        if not result.passed:
            all_passed = False

    # Summary
    total = len(scale_dirs)
    passed = sum(1 for d in scale_dirs if validate_scale(d).passed)
    failed = total - passed
    print(f"Results: {passed}/{total} passed, {failed} failed")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
