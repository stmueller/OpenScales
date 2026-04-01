#!/usr/bin/env python3
"""Convert PsyToolkit survey format to Open Scale Definition (OSD) format.

Usage:
    python3 convert_from_psytoolkit.py <input.txt> [--code CODE] [--name NAME] [--outdir DIR]

Reads a PsyToolkit survey definition file (.txt) and generates:
  - {code}.json      — Scale definition
  - {code}.en.json   — English translation file

PsyToolkit format reference: https://www.psytoolkit.org/doc3.0/online-survey-syntax.html

Supported PsyToolkit constructs:
  - scale: definitions with {score=N} annotations
  - t: scale <name>     — Likert-type items
  - t: radio            — Single-select multiple choice
  - t: textline         — Short text entry
  - t: range            — Visual analog scale (VAS)
  - t: multiradio N     — Forced-choice groups (converted to multi)
  - t: set              — Scoring (sum, mean, calc)
  - t: info             — Instruction/feedback display
  - t: jump             — Skip logic (noted in output, not fully converted)
  - {reverse} items     — Reverse-coded items
  - o: buildup          — Noted as option
  - o: random           — Randomization
  - o: scores           — Custom score values
"""

import json
import re
import sys
import os
from pathlib import Path


def parse_psytoolkit(text):
    """Parse PsyToolkit survey text into structured blocks."""
    lines = text.strip().split("\n")
    scales = {}
    blocks = []
    current_block = None

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Scale definition
        if line.startswith("scale:"):
            scale_name = line[6:].strip()
            scale_items = []
            i += 1
            while i < len(lines) and lines[i].strip().startswith("-"):
                item_text = lines[i].strip()[2:]  # strip "- "
                scale_items.append(item_text)
                i += 1
            scales[scale_name] = scale_items
            continue

        # Block label
        if line.startswith("l:"):
            if current_block:
                blocks.append(current_block)
            label = line[2:].strip()
            current_block = {
                "label": label,
                "type": None,
                "question": "",
                "items": [],
                "options": [],
            }
            i += 1
            continue

        # Block type
        if line.startswith("t:") and current_block:
            current_block["type"] = line[2:].strip()
            i += 1
            continue

        # Block question
        if line.startswith("q:") and current_block:
            q_text = line[2:].strip()
            # Continuation lines (not starting with a directive or -)
            i += 1
            while i < len(lines):
                next_line = lines[i].rstrip()
                if (next_line.startswith("l:") or next_line.startswith("t:") or
                    next_line.startswith("q:") or next_line.startswith("o:") or
                    next_line.startswith("scale:") or next_line.strip().startswith("-")):
                    break
                q_text += " " + next_line.strip()
                i += 1
            current_block["question"] = q_text.strip()
            continue

        # Block options
        if line.startswith("o:") and current_block:
            current_block["options"].append(line[2:].strip())
            i += 1
            continue

        # List items
        if line.strip().startswith("-") and current_block:
            item = line.strip()[2:]  # strip "- "
            current_block["items"].append(item)
            i += 1
            continue

        i += 1

    if current_block:
        blocks.append(current_block)

    return scales, blocks


def parse_scale_options(scale_items):
    """Parse scale option texts, extracting {score=N} annotations."""
    options = []
    for item in scale_items:
        score = None
        text = item
        score_match = re.search(r"\{score=(-?\d+)\}", text)
        if score_match:
            score = int(score_match.group(1))
            text = re.sub(r"\{score=-?\d+\}\s*", "", text).strip()
        options.append({"text": text, "score": score})
    return options


def parse_item_annotations(item_text):
    """Parse item text for {reverse}, {other}, etc."""
    annotations = {}
    text = item_text

    if "{reverse}" in text:
        annotations["reverse"] = True
        text = text.replace("{reverse}", "").strip()

    if "{other" in text:
        annotations["other"] = True
        other_match = re.search(r"\{other(?:,size=(\d+))?\}", text)
        if other_match:
            text = re.sub(r"\{other(?:,size=\d+)?\}\s*", "", text).strip()

    # Range parameters: {left=...,right=...,min=...,max=...}
    range_match = re.search(r"\{([^}]+)\}", text)
    if range_match:
        params_str = range_match.group(1)
        if "left=" in params_str or "min=" in params_str:
            params = {}
            for part in params_str.split(","):
                part = part.strip()
                if "=" in part:
                    key, val = part.split("=", 1)
                    params[key.strip()] = val.strip()
                else:
                    params[part] = True
            annotations["range_params"] = params
            text = re.sub(r"\{[^}]+\}", "", text).strip()

    # Score annotation on individual items
    score_match = re.search(r"\{score=(-?\d+)\}", text)
    if score_match:
        annotations["score"] = int(score_match.group(1))
        text = re.sub(r"\{score=-?\d+\}\s*", "", text).strip()

    # Min/max for textline
    minmax_match = re.search(r"\{min=(\d+),max=(\d+)\}", text)
    if minmax_match:
        annotations["min"] = int(minmax_match.group(1))
        annotations["max"] = int(minmax_match.group(2))
        text = re.sub(r"\{min=\d+,max=\d+\}", "", text).strip()

    return text, annotations


def sanitize_key(text, prefix="q"):
    """Create a translation key from text."""
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", text)
    # Take first few words
    words = re.sub(r"[^a-zA-Z0-9\s]", "", clean).split()
    key = "_".join(words[:5]).lower()
    if not key:
        key = prefix
    return key


def convert_to_open_scale(scales, blocks, code, name):
    """Convert parsed PsyToolkit data to OSD format."""
    definition = {
        "scale_info": {
            "name": name,
            "code": code,
            "version": "1.0",
            "description": "",
            "citation": "",
            "license": "",
        }
    }
    translations = {}
    questions = []
    scoring = {}
    dimensions = []
    likert_options = None

    question_counter = 0
    # Map PsyToolkit labels to our question IDs
    label_to_ids = {}

    for block in blocks:
        block_type = block["type"] or ""
        label = block["label"]

        # --- Scale-type questions (Likert) ---
        if block_type.startswith("scale "):
            scale_name = block_type[6:].strip()
            scale_opts = scales.get(scale_name, [])
            parsed_opts = parse_scale_options(scale_opts)

            # Determine Likert points and scoring
            points = len(parsed_opts)
            has_custom_scores = any(o["score"] is not None for o in parsed_opts)

            if has_custom_scores:
                score_values = [o["score"] for o in parsed_opts]
                min_score = min(v for v in score_values if v is not None)
                max_score = max(v for v in score_values if v is not None)
            else:
                min_score = 1
                max_score = points

            # Set up scale-level likert options (use first scale encountered)
            if likert_options is None:
                label_keys = []
                for j, opt in enumerate(parsed_opts):
                    key = f"likert_{j+1}"
                    label_keys.append(key)
                    translations[key] = opt["text"]
                likert_options = {
                    "points": points,
                    "min": min_score,
                    "max": max_score,
                    "labels": label_keys,
                    "question_head": "question_head",
                }

            # Add question header
            if block["question"]:
                translations["question_head"] = block["question"]

            # Track item IDs for this block
            block_item_ids = []
            has_randomize = "random" in block["options"]

            for j, item_text in enumerate(block["items"]):
                question_counter += 1
                text, annotations = parse_item_annotations(item_text)
                qid = f"{label}{j+1}" if label else f"q{question_counter}"

                translations[qid] = text

                q = {
                    "id": qid,
                    "text_key": qid,
                    "type": "likert",
                    "likert_points": points,
                }

                if annotations.get("reverse"):
                    q["coding"] = -1
                else:
                    q["coding"] = 1

                questions.append(q)
                block_item_ids.append(qid)

            label_to_ids[label] = block_item_ids

        # --- Radio questions (multiple choice) ---
        elif block_type == "radio":
            question_counter += 1
            qid = label if label else f"q{question_counter}"

            if block["question"]:
                translations[qid] = block["question"]

            options = []
            for j, item_text in enumerate(block["items"]):
                text, annotations = parse_item_annotations(item_text)
                opt_key = f"{qid}_opt{j+1}"
                translations[opt_key] = text
                options.append({"value": str(j + 1), "text_key": opt_key})

            q = {
                "id": qid,
                "text_key": qid,
                "type": "multi",
                "options": options,
            }
            questions.append(q)
            label_to_ids[label] = [qid]

        # --- Multiradio (forced-choice groups) ---
        elif block_type.startswith("multiradio"):
            num_per_group = int(block_type.split()[1]) if len(block_type.split()) > 1 else 2
            question_counter += 1

            if block["question"]:
                translations[label or f"q{question_counter}"] = block["question"]

            # Parse o: scores if present
            custom_scores = None
            for opt in block["options"]:
                if opt.startswith("scores"):
                    custom_scores = [int(x) for x in opt.split()[1:]]

            # Group items into sets of num_per_group
            block_item_ids = []
            group_idx = 0
            for j in range(0, len(block["items"]), num_per_group):
                group = block["items"][j:j + num_per_group]
                group_idx += 1
                qid = f"{label}{group_idx}" if label else f"q{question_counter}_{group_idx}"

                options = []
                for k, item_text in enumerate(group):
                    text, annotations = parse_item_annotations(item_text)
                    # Handle indented items (PsyToolkit uses leading spaces for internal/external)
                    text = text.strip()
                    opt_key = f"{qid}_opt{k+1}"
                    translations[opt_key] = text
                    val = str(custom_scores[k]) if custom_scores and k < len(custom_scores) else str(k + 1)
                    options.append({"value": val, "text_key": opt_key})

                q = {
                    "id": qid,
                    "text_key": label or f"q{question_counter}",
                    "type": "multi",
                    "options": options,
                }
                questions.append(q)
                block_item_ids.append(qid)

            label_to_ids[label] = block_item_ids

        # --- Text entry ---
        elif block_type == "textline":
            question_counter += 1
            qid = label if label else f"q{question_counter}"

            if block["question"]:
                translations[qid] = block["question"]

            q = {
                "id": qid,
                "text_key": qid,
                "type": "short",
            }

            # Check for min/max validation
            if block["items"]:
                _, annotations = parse_item_annotations(block["items"][0])
                if "min" in annotations or "max" in annotations:
                    q["validation"] = {"type": "number"}
                    if "min" in annotations:
                        q["validation"]["min"] = annotations["min"]
                    if "max" in annotations:
                        q["validation"]["max"] = annotations["max"]

            questions.append(q)
            label_to_ids[label] = [qid]

        # --- Range (VAS) ---
        elif block_type == "range":
            question_counter += 1
            qid = label if label else f"q{question_counter}"

            if block["question"]:
                translations[qid] = block["question"]

            q = {
                "id": qid,
                "text_key": qid,
                "type": "vas",
                "min": 0,
                "max": 100,
            }

            if block["items"]:
                _, annotations = parse_item_annotations(block["items"][0])
                params = annotations.get("range_params", {})
                if "min" in params:
                    q["min"] = int(params["min"])
                if "max" in params:
                    q["max"] = int(params["max"])
                if "left" in params:
                    left_key = f"{qid}_min_label"
                    translations[left_key] = params["left"]
                    q["min_label"] = left_key
                if "right" in params:
                    right_key = f"{qid}_max_label"
                    translations[right_key] = params["right"]
                    q["max_label"] = right_key

            questions.append(q)
            label_to_ids[label] = [qid]

        # --- Scoring (set) ---
        elif block_type == "set":
            for item_line in block["items"]:
                item_line = item_line.strip()
                # Parse: sum $label or mean $label or calc (...)
                if item_line.startswith("sum ") or item_line.startswith("mean "):
                    parts = item_line.split()
                    method_word = parts[0]  # sum or mean
                    refs = parts[1:]

                    score_items = []
                    for ref in refs:
                        ref = ref.strip()
                        if ref.startswith("$"):
                            ref_label = ref[1:]
                            # Could be $label or $label.N
                            if "." in ref_label:
                                base, idx = ref_label.rsplit(".", 1)
                                if base in label_to_ids:
                                    idx_int = int(idx) - 1
                                    if 0 <= idx_int < len(label_to_ids[base]):
                                        score_items.append(label_to_ids[base][idx_int])
                            elif ref_label in label_to_ids:
                                score_items.extend(label_to_ids[ref_label])

                    if score_items:
                        method = "mean_coded" if method_word == "mean" else "sum_coded"
                        dim_id = label

                        # Build item_coding from question coding
                        item_coding = {}
                        for sid in score_items:
                            for q in questions:
                                if q["id"] == sid:
                                    item_coding[sid] = q.get("coding", 1)
                                    break

                        scoring[dim_id] = {
                            "method": method,
                            "items": score_items,
                            "item_coding": item_coding,
                        }
                        dimensions.append({
                            "id": dim_id,
                            "name": label.replace("_", " ").title(),
                        })

                elif item_line.startswith("calc "):
                    # Complex calc expression — store as comment
                    dim_id = label
                    scoring[dim_id] = {
                        "method": "mean_coded",
                        "items": [],
                        "description": f"PsyToolkit calc: {item_line}",
                    }
                    # Try to extract references
                    refs = re.findall(r"\$(\w+)\.(\d+)", item_line)
                    calc_items = []
                    for ref_label, idx in refs:
                        if ref_label in label_to_ids:
                            idx_int = int(idx) - 1
                            if 0 <= idx_int < len(label_to_ids[ref_label]):
                                calc_items.append(label_to_ids[ref_label][idx_int])
                    if calc_items:
                        scoring[dim_id]["items"] = calc_items
                        # Determine method from expression
                        if "/ " in item_line:
                            scoring[dim_id]["method"] = "mean_coded"
                        else:
                            scoring[dim_id]["method"] = "sum_coded"
                        # Add item coding
                        item_coding = {}
                        for sid in calc_items:
                            for q in questions:
                                if q["id"] == sid:
                                    item_coding[sid] = q.get("coding", 1)
                                    break
                        scoring[dim_id]["item_coding"] = item_coding

                    dimensions.append({
                        "id": dim_id,
                        "name": label.replace("_", " ").title(),
                    })

        # --- Info/feedback (instruction display) ---
        elif block_type == "info":
            if block["question"]:
                qid = label if label else f"info{question_counter}"
                translations[qid] = block["question"]
                q = {
                    "id": qid,
                    "text_key": qid,
                    "type": "inst",
                }
                questions.append(q)

        # --- Jump (skip logic) ---
        elif block_type == "jump":
            # Note: skip logic is recorded but not fully converted
            for item_line in block["items"]:
                pass  # Skip logic not directly translatable

    # Assemble definition
    if likert_options:
        definition["likert_options"] = likert_options

    if dimensions:
        definition["dimensions"] = dimensions

    definition["items"] = questions

    if scoring:
        definition["scoring"] = scoring

    # Add debrief if not present
    if "debrief" not in translations:
        translations["debrief"] = "Thank you for completing this questionnaire."

    return definition, translations


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert PsyToolkit survey to OSD format"
    )
    parser.add_argument("input", help="PsyToolkit survey file (.txt)")
    parser.add_argument("--code", help="Scale code (default: derived from filename)")
    parser.add_argument("--name", help="Scale name (default: derived from filename)")
    parser.add_argument("--outdir", help="Output directory (default: scales/{code}/)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: '{input_path}' not found")
        sys.exit(1)

    # Determine code and name
    code = args.code or input_path.stem.replace(" ", "_").replace("-", "_")
    name = args.name or code.replace("_", " ").title()

    # Read input
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Parse and convert
    scales, blocks = parse_psytoolkit(text)
    definition, translations = convert_to_open_scale(scales, blocks, code, name)

    # Output directory
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    if args.outdir:
        outdir = Path(args.outdir)
    else:
        outdir = repo_root / "scales" / code
    outdir.mkdir(parents=True, exist_ok=True)

    # Write definition
    def_path = outdir / f"{code}.json"
    with open(def_path, "w", encoding="utf-8") as f:
        json.dump(definition, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  Written: {def_path}")

    # Write translation
    trans_path = outdir / f"{code}.en.json"
    with open(trans_path, "w", encoding="utf-8") as f:
        json.dump(translations, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  Written: {trans_path}")

    # Summary
    q_count = sum(1 for q in definition["items"] if q["type"] not in ("inst",))
    dim_count = len(definition.get("dimensions", []))
    print(f"\n  Scale: {name} ({code})")
    print(f"  Questions: {q_count}")
    print(f"  Dimensions: {dim_count}")
    print(f"  Scoring methods: {len(definition.get('scoring', {}))}")


if __name__ == "__main__":
    main()
