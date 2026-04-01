#!/usr/bin/env python3
"""Convert Open Scale Definition (OSD) format to PsyToolkit survey format.

Usage:
    python3 convert_to_psytoolkit.py <scale_directory> [--output FILE]
    python3 convert_to_psytoolkit.py scales/grit/ --output grit.psytoolkit.txt

Reads {code}.json and {code}.{lang}.json from a scale directory and generates
a PsyToolkit-compatible survey definition file.

Supported conversions:
  - likert     -> scale + t: scale
  - vas        -> t: range
  - multi      -> t: radio
  - multicheck -> t: radio (with note)
  - short      -> t: textline
  - long       -> t: textline (PsyToolkit has no direct equivalent)
  - grid       -> t: scale (one block per grid)
  - inst       -> t: info
  - Scoring (mean_coded, sum_coded) -> t: set with mean/sum
  - Reverse coding -> {reverse} annotation
  - Feedback with score interpolation
"""

import json
import re
import sys
from pathlib import Path


def find_definition_file(scale_dir):
    """Find the main .json definition file."""
    p = Path(scale_dir)
    code = p.name
    definition = p / f"{code}.json"
    if definition.exists():
        return definition, code
    # Try .osd format
    for f in sorted(p.glob("*.osd")):
        return f, f.stem
    return None, code


def load_translation(scale_dir, code, lang="en"):
    """Load a translation file."""
    p = Path(scale_dir)
    for pattern in [f"{code}.{lang}.json", f"{code}.pbl-{lang}.json"]:
        path = p / pattern
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    # Fallback: try loading from .osd file
    for osd_file in p.glob("*.osd"):
        try:
            with open(osd_file, "r", encoding="utf-8") as f:
                osd_data = json.load(f)
            translations = osd_data.get("translations", {})
            if lang in translations:
                return translations[lang]
            # Try first available language
            if translations:
                return next(iter(translations.values()))
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def get_text(translations, key):
    """Get translated text, trying case-insensitive lookup."""
    if key in translations:
        return translations[key]
    for k, v in translations.items():
        if k.lower() == key.lower():
            return v
    return key


def escape_psytoolkit(text):
    """Ensure text is safe for PsyToolkit format (already supports HTML)."""
    # PsyToolkit supports HTML, so most content passes through
    # Just ensure no bare newlines (use <br> instead)
    return text.replace("\n", "<br>\n")


def generate_psytoolkit(definition, translations):
    """Generate PsyToolkit survey text from OSD format."""
    lines = []
    code = definition.get("scale_info", {}).get("code", "scale")

    questions = definition.get("items") or definition.get("questions", [])
    scoring = definition.get("scoring", {})
    likert_opts = definition.get("likert_options", {})

    # Track which scale definitions and labels we've emitted
    emitted_scales = set()
    emitted_labels = set()
    # Deferred feedback blocks (inst questions referencing score variables)
    deferred_feedback = []

    # Collect all likert questions to group them by their response scale
    # Most scales have one global likert scale, so we emit it first
    if likert_opts and likert_opts.get("labels"):
        scale_name = code.lower()
        labels = likert_opts["labels"]
        points = likert_opts.get("points", len(labels))
        min_val = likert_opts.get("min", 1)

        lines.append(f"scale: {scale_name}")
        for i, label_key in enumerate(labels):
            label_text = get_text(translations, label_key)
            score_val = min_val + i
            lines.append(f"- {{score={score_val}}} {label_text}")
        lines.append("")
        emitted_scales.add(scale_name)

    # Separate questions into groups by type for output
    # PsyToolkit works best with one block per logical group

    # Find contiguous runs of likert questions (the main block)
    likert_runs = []
    current_run = []
    for q in questions:
        if q.get("type") == "likert":
            current_run.append(q)
        else:
            if current_run:
                likert_runs.append(current_run)
                current_run = []
            # Non-likert questions get individual treatment
            likert_runs.append([q])
    if current_run:
        likert_runs.append(current_run)

    # Map question IDs to block labels and item indices for scoring
    qid_to_ref = {}
    block_counter = 0

    for run in likert_runs:
        if not run:
            continue

        first_type = run[0].get("type", "")

        # --- Likert block ---
        if first_type == "likert" and len(run) > 1:
            block_counter += 1
            block_label = code.lower()
            scale_name = code.lower()

            # Question head
            question_head = ""
            if likert_opts.get("question_head"):
                question_head = get_text(translations, likert_opts["question_head"])

            lines.append(f"l: {block_label}")
            lines.append(f"t: scale {scale_name}")
            lines.append("o: buildup")
            if question_head:
                lines.append(f"q: {escape_psytoolkit(question_head)}")

            emitted_labels.add(block_label)
            for i, q in enumerate(run):
                text = get_text(translations, q.get("text_key", q["id"]))
                # Check reverse coding
                is_reverse = False
                for score_def in scoring.values():
                    if isinstance(score_def, dict) and "item_coding" in score_def:
                        if q["id"] in score_def["item_coding"]:
                            if score_def["item_coding"][q["id"]] == -1:
                                is_reverse = True
                                break
                if q.get("coding") == -1:
                    is_reverse = True

                prefix = "{reverse} " if is_reverse else ""
                lines.append(f"- {prefix}{text}")
                qid_to_ref[q["id"]] = f"${block_label}.{i+1}"

            lines.append("")

        # --- Single likert question ---
        elif first_type == "likert" and len(run) == 1:
            q = run[0]
            block_label = q["id"].lower()
            scale_name = code.lower()

            text = get_text(translations, q.get("text_key", q["id"]))
            is_reverse = q.get("coding") == -1
            for score_def in scoring.values():
                if isinstance(score_def, dict) and "item_coding" in score_def:
                    if q["id"] in score_def["item_coding"] and score_def["item_coding"][q["id"]] == -1:
                        is_reverse = True

            lines.append(f"l: {block_label}")
            lines.append(f"t: scale {scale_name}")
            prefix = "{reverse} " if is_reverse else ""
            lines.append(f"- {prefix}{text}")
            lines.append("")
            emitted_labels.add(block_label)
            qid_to_ref[q["id"]] = f"${block_label}"

        # --- Instruction ---
        elif first_type == "inst":
            q = run[0]
            text = get_text(translations, q.get("text_key", q["id"]))
            label = q['id'].lower()

            # Check if this inst references score variables — if so, defer
            # it to after scoring blocks so PsyToolkit can resolve them
            has_score_ref = "{$" in text
            if not has_score_ref and scoring:
                for score_id in scoring:
                    if "{" + score_id.lower() + "}" in text.lower():
                        has_score_ref = True
                        break

            if has_score_ref and scoring:
                deferred_feedback.append((label, text))
            else:
                lines.append(f"l: {label}")
                lines.append("t: info")
                lines.append(f"q: {escape_psytoolkit(text)}")
                lines.append("")
            emitted_labels.add(label)

        # --- Multiple choice ---
        elif first_type in ("multi", "multicheck"):
            q = run[0]
            text = get_text(translations, q.get("text_key", q["id"]))
            block_label = q["id"].lower()

            lines.append(f"l: {block_label}")
            lines.append("t: radio")
            lines.append(f"q: {escape_psytoolkit(text)}")

            for opt in q.get("options", []):
                if isinstance(opt, dict):
                    opt_text = get_text(translations, opt.get("text_key", opt.get("value", "")))
                else:
                    opt_text = get_text(translations, opt)
                lines.append(f"- {opt_text}")

            lines.append("")
            qid_to_ref[q["id"]] = f"${block_label}"

        # --- Short text ---
        elif first_type == "short":
            q = run[0]
            text = get_text(translations, q.get("text_key", q["id"]))
            block_label = q["id"].lower()

            lines.append(f"l: {block_label}")
            lines.append("t: textline")
            lines.append(f"q: {escape_psytoolkit(text)}")

            validation = q.get("validation", {})
            if validation.get("type") == "number":
                min_v = validation.get("min", "")
                max_v = validation.get("max", "")
                if min_v != "" and max_v != "":
                    lines.append(f"- {{min={min_v},max={max_v}}}")
            elif q.get("maxlength"):
                lines.append(f"- {{max={q['maxlength']}}}")

            lines.append("")
            qid_to_ref[q["id"]] = f"${block_label}"

        # --- Long text ---
        elif first_type == "long":
            q = run[0]
            text = get_text(translations, q.get("text_key", q["id"]))
            block_label = q["id"].lower()

            lines.append(f"l: {block_label}")
            lines.append("t: textline")
            lines.append(f"q: {escape_psytoolkit(text)}")
            lines.append("")
            qid_to_ref[q["id"]] = f"${block_label}"

        # --- VAS ---
        elif first_type == "vas":
            q = run[0]
            text = get_text(translations, q.get("text_key", q["id"]))
            block_label = q["id"].lower()

            min_val = q.get("min", 0)
            max_val = q.get("max", 100)

            min_label = ""
            max_label = ""
            if "min_label" in q:
                min_label = get_text(translations, q["min_label"])
            if "max_label" in q:
                max_label = get_text(translations, q["max_label"])

            lines.append(f"l: {block_label}")
            lines.append("t: range")
            lines.append(f"q: {escape_psytoolkit(text)}")

            range_params = f"min={min_val},max={max_val},start={int((min_val+max_val)/2)}"
            if min_label:
                range_params += f",left={min_label}"
            if max_label:
                range_params += f",right={max_label}"
            lines.append(f"- {{{range_params},no_number}}")
            lines.append("")
            qid_to_ref[q["id"]] = f"${block_label}"

        # --- Grid ---
        elif first_type == "grid":
            q = run[0]
            text = get_text(translations, q.get("text_key", q["id"]))
            block_label = q["id"].lower()

            # Grid columns become scale options
            columns = q.get("columns", [])
            rows = q.get("rows", [])

            if columns:
                grid_scale = f"{block_label}_scale"
                if grid_scale not in emitted_scales:
                    lines.append(f"scale: {grid_scale}")
                    for i, col in enumerate(columns):
                        col_text = get_text(translations, col) if isinstance(col, str) else str(col)
                        lines.append(f"- {{score={i+1}}} {col_text}")
                    lines.append("")
                    emitted_scales.add(grid_scale)

                lines.append(f"l: {block_label}")
                lines.append(f"t: scale {grid_scale}")
                lines.append(f"q: {escape_psytoolkit(text)}")

                for row in rows:
                    row_text = get_text(translations, row) if isinstance(row, str) else str(row)
                    lines.append(f"- {row_text}")
                lines.append("")

            qid_to_ref[q["id"]] = f"${block_label}"

        # --- Image types ---
        elif first_type in ("image", "imageresponse"):
            q = run[0]
            text = get_text(translations, q.get("text_key", q["id"]))
            lines.append(f"l: {q['id'].lower()}")
            lines.append("t: info")
            lines.append(f"q: {escape_psytoolkit(text)}")
            lines.append("")

    # --- Scoring blocks ---
    for score_id, score_def in scoring.items():
        if not isinstance(score_def, dict):
            continue

        method = score_def.get("method", "")
        items = score_def.get("items", [])

        if not items:
            continue

        # Check if all items belong to one block
        refs = []
        single_block = None
        for item_id in items:
            if item_id in qid_to_ref:
                refs.append(qid_to_ref[item_id])
                # Extract block name from $block.N or $block
                ref = qid_to_ref[item_id]
                block = ref.split(".")[0] if "." in ref else ref
                if single_block is None:
                    single_block = block
                elif single_block != block:
                    single_block = None

        if not refs:
            continue

        psyt_method = "mean" if "mean" in method else "sum"

        lines.append(f"l: {score_id.lower()}")
        lines.append("t: set")

        # If all items from one block, use shorthand $block
        if single_block and len(refs) == len([q for q in questions if q.get("type") not in ("inst", "image")]):
            lines.append(f"- {psyt_method} {single_block}")
        else:
            lines.append(f"- {psyt_method} {' '.join(refs)}")

        lines.append("")

    # --- Deferred feedback blocks (inst questions that reference scores) ---
    for label, text in deferred_feedback:
        lines.append(f"l: {label}")
        lines.append("t: info")
        lines.append(f"q: {escape_psytoolkit(text)}")
        lines.append("")

    # --- Feedback block ---
    # Only generate generic feedback if the scale doesn't already have one
    if scoring and "feedback" not in emitted_labels:
        lines.append("l: feedback")
        lines.append("t: info")
        feedback_parts = ["q: Your scores are as follows:<br>"]
        feedback_parts.append("<ul>")
        for score_id in scoring:
            feedback_parts.append(f"<li><b>{score_id}</b>: {{{score_id.lower()}}}")
        feedback_parts.append("</ul>")
        lines.append("\n".join(feedback_parts))
        lines.append("")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert OSD format to PsyToolkit survey format"
    )
    parser.add_argument("scale_dir", help="Path to scale directory")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--lang", default="en", help="Language code (default: en)")
    args = parser.parse_args()

    scale_dir = Path(args.scale_dir)
    if not scale_dir.exists():
        print(f"Error: '{scale_dir}' not found")
        sys.exit(1)

    def_file, code = find_definition_file(scale_dir)
    if def_file is None:
        print(f"Error: No definition file found in '{scale_dir}'")
        sys.exit(1)

    with open(def_file, "r", encoding="utf-8") as f:
        definition = json.load(f)

    # Handle .osd wrapper format
    if 'definition' in definition and 'osd_version' in definition:
        definition = definition['definition']

    translations = load_translation(scale_dir, code, args.lang)

    output = generate_psytoolkit(definition, translations)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Written: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
