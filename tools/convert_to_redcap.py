#!/usr/bin/env python3
"""Convert Open Scale Definition (OSD) format to REDCap Data Dictionary CSV.

Usage:
    python3 convert_to_redcap.py <scale_directory> [--output FILE] [--lang LANG]
    python3 convert_to_redcap.py scales/grit/ --output grit_redcap.csv

Reads {code}.json and {code}.{lang}.json from a scale directory and generates
a REDCap Data Dictionary CSV file suitable for import via:
    Designer > Data Dictionary > Upload

Supported conversions:
  - likert           -> radio with numbered choices
  - multi            -> radio
  - multicheck       -> checkbox
  - dropdown         -> dropdown
  - short            -> text
  - long             -> notes
  - number           -> text with number validation
  - date             -> text with date_ymd validation
  - vas              -> slider
  - grid             -> multiple radio fields (one per row)
  - inst             -> descriptive
  - constant_sum     -> multiple text fields with number validation
  - image            -> descriptive with HTML
  - Scoring          -> calc fields with REDCap expressions

Notes:
  - Reverse coding is handled in calc field expressions.
  - Grid questions are expanded into one radio field per row.
  - The form name is set to the scale code.
  - Section headers are generated from pages if defined.
"""

import csv
import json
import re
import sys
import io
from pathlib import Path


# REDCap Data Dictionary column headers
REDCAP_COLUMNS = [
    "Variable / Field Name",
    "Form Name",
    "Section Header",
    "Field Type",
    "Field Label",
    "Choices, Calculations, OR Slider Labels",
    "Field Note",
    "Text Validation Type OR Show Slider Number",
    "Text Validation Min",
    "Text Validation Max",
    "Identifier?",
    "Branching Logic (Show field only if...)",
    "Required Field?",
    "Custom Alignment",
    "Question Number (Survey Display)",
    "Matrix Group Name",
    "Matrix Ranking?",
    "Field Annotation",
]


def find_definition_file(scale_dir):
    """Find the main .json definition file."""
    p = Path(scale_dir)
    code = p.name
    definition = p / f"{code}.json"
    if definition.exists():
        return definition, code
    for f in sorted(p.glob("*.json")):
        if not re.match(r".*\.\w{2}(-\w+)?\.json$", f.name):
            return f, f.stem
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


def strip_html(text):
    """Strip HTML tags for plain-text contexts."""
    return re.sub(r"<[^>]+>", "", text).strip()


def clean_field_name(name):
    """Convert a question ID to a valid REDCap variable name.

    REDCap variable names must:
    - Start with a letter
    - Contain only letters, numbers, underscores
    - Be <= 26 characters (recommended, not enforced)
    - Be lowercase
    """
    name = name.lower()
    name = re.sub(r"[^a-z0-9_]", "_", name)
    if name and not name[0].isalpha():
        name = "q_" + name
    return name


def format_choices(labels, min_val=1):
    """Format choice labels as REDCap pipe-delimited string.

    Format: '1, Label 1 | 2, Label 2 | 3, Label 3'
    """
    parts = []
    for i, label in enumerate(labels):
        val = min_val + i
        parts.append(f"{val}, {strip_html(label)}")
    return " | ".join(parts)


def make_row(**kwargs):
    """Create a REDCap Data Dictionary row with defaults."""
    row = {col: "" for col in REDCAP_COLUMNS}
    for key, value in kwargs.items():
        if key in row:
            row[key] = value
    return row


def get_likert_labels(question, definition, translations):
    """Get likert labels for a question (per-item or scale-level)."""
    if "likert_labels" in question:
        return [get_text(translations, lbl) for lbl in question["likert_labels"]]
    likert_opts = definition.get("likert_options", {})
    if likert_opts.get("labels"):
        return [get_text(translations, lbl) for lbl in likert_opts["labels"]]
    points = question.get("likert_points", likert_opts.get("points", 5))
    min_val = likert_opts.get("min", 1)
    return [str(min_val + i) for i in range(points)]


def get_likert_min(question, definition):
    """Get the minimum numeric value for likert scoring."""
    return definition.get("likert_options", {}).get("min", 1)


def get_likert_max(question, definition):
    """Get the maximum numeric value for likert scoring."""
    likert_opts = definition.get("likert_options", {})
    points = question.get("likert_points", likert_opts.get("points", 5))
    min_val = likert_opts.get("min", 1)
    return min_val + points - 1


def build_scoring_expression(score_id, score_def, definition):
    """Build a REDCap calc expression for a scoring definition.

    Returns a string like: round(([q1] + (6-[q2]) + [q3]) / 3, 2)
    """
    method = score_def.get("method", "")
    items = score_def.get("items", [])
    item_coding = score_def.get("item_coding", {})

    if not items:
        return ""

    if method == "sum_correct":
        # Can't easily do string matching in REDCap calc
        # Just sum the items and add a note
        parts = [f"[{clean_field_name(item)}]" for item in items]
        return f"sum({','.join(parts)})"

    # For mean_coded and sum_coded, handle reverse coding
    likert_opts = definition.get("likert_options", {})
    min_val = likert_opts.get("min", 1)
    points = likert_opts.get("points", 5)
    max_val = min_val + points - 1
    reverse_sum = min_val + max_val  # e.g., 6 for a 1-5 scale

    parts = []
    for item in items:
        field = clean_field_name(item)
        coding = item_coding.get(item, 1)
        if coding == -1:
            parts.append(f"({reverse_sum}-[{field}])")
        else:
            parts.append(f"[{field}]")

    if method == "mean_coded":
        n = len(items)
        return f"round(({' + '.join(parts)}) / {n}, 2)"
    elif method == "sum_coded":
        return f"({' + '.join(parts)})"
    elif method == "weighted_sum":
        weights = score_def.get("weights", {})
        weighted_parts = []
        for item in items:
            field = clean_field_name(item)
            w = weights.get(item, 1)
            coding = item_coding.get(item, 1)
            if coding == -1:
                weighted_parts.append(f"({w} * ({reverse_sum}-[{field}]))")
            else:
                weighted_parts.append(f"({w} * [{field}])")
        return f"({' + '.join(weighted_parts)})"
    else:
        parts = [f"[{clean_field_name(item)}]" for item in items]
        return f"sum({','.join(parts)})"


def generate_redcap(definition, translations):
    """Generate REDCap Data Dictionary rows from OSD format."""
    code = definition.get("scale_info", {}).get("code", "scale")
    form_name = clean_field_name(code)
    questions = definition.get("items") or definition.get("questions", [])
    scoring = definition.get("scoring", {})
    pages = definition.get("pages", None)
    likert_opts = definition.get("likert_options", {})

    rows = []
    section_header = ""

    # Track which page we're on for section headers
    q_to_page = {}
    if pages:
        for page in pages:
            for item_id in page.get("items", []):
                q_to_page[item_id] = page

    # Track matrix groups for likert items
    # Group contiguous likert items with same scale
    matrix_groups = _identify_matrix_groups(questions, definition)

    for q in questions:
        qtype = q.get("type", "")
        qid = q["id"]
        field_name = clean_field_name(qid)
        text = get_text(translations, q.get("text_key", qid))
        is_required = q.get("required", qtype in ("likert", "vas", "multi",
                                                    "grid", "multicheck"))

        # Section header from page
        if qid in q_to_page:
            page = q_to_page[qid]
            if page.get("items", [None])[0] == qid:
                title_key = page.get("title_key", "")
                if title_key:
                    section_header = get_text(translations, title_key)
                else:
                    section_header = page.get("id", "")

        if qtype == "likert":
            labels = get_likert_labels(q, definition, translations)
            min_val = get_likert_min(q, definition)
            choices = format_choices(labels, min_val)
            matrix_group = matrix_groups.get(qid, "")

            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "radio",
                "Field Label": text,
                "Choices, Calculations, OR Slider Labels": choices,
                "Required Field?": "y" if is_required else "",
                "Matrix Group Name": matrix_group,
            }))

        elif qtype == "multi":
            options = q.get("options", [])
            choice_parts = []
            for i, opt in enumerate(options):
                if isinstance(opt, dict):
                    val = opt.get("value", str(i + 1))
                    opt_text = get_text(translations,
                                        opt.get("text_key",
                                                 opt.get("value", "")))
                else:
                    val = str(i + 1)
                    opt_text = get_text(translations, opt)
                choice_parts.append(f"{val}, {strip_html(opt_text)}")

            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "radio",
                "Field Label": text,
                "Choices, Calculations, OR Slider Labels": " | ".join(choice_parts),
                "Required Field?": "y" if is_required else "",
            }))

        elif qtype == "multicheck":
            options = q.get("options", [])
            choice_parts = []
            for i, opt in enumerate(options):
                if isinstance(opt, dict):
                    val = opt.get("value", str(i + 1))
                    opt_text = get_text(translations,
                                        opt.get("text_key",
                                                 opt.get("value", "")))
                else:
                    val = str(i + 1)
                    opt_text = get_text(translations, opt)
                choice_parts.append(f"{val}, {strip_html(opt_text)}")

            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "checkbox",
                "Field Label": text,
                "Choices, Calculations, OR Slider Labels": " | ".join(choice_parts),
                "Required Field?": "y" if is_required else "",
            }))

        elif qtype == "dropdown":
            options = q.get("options", [])
            choice_parts = []
            for i, opt in enumerate(options):
                if isinstance(opt, dict):
                    val = opt.get("value", str(i + 1))
                    opt_text = get_text(translations,
                                        opt.get("text_key",
                                                 opt.get("value", "")))
                else:
                    val = str(i + 1)
                    opt_text = get_text(translations, opt)
                choice_parts.append(f"{val}, {strip_html(opt_text)}")

            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "dropdown",
                "Field Label": text,
                "Choices, Calculations, OR Slider Labels": " | ".join(choice_parts),
                "Required Field?": "y" if is_required else "",
            }))

        elif qtype == "short":
            validation_type = ""
            val_min = ""
            val_max = ""
            validation = q.get("validation", {})
            if validation.get("type") == "number":
                validation_type = "number"
                val_min = str(validation.get("min", ""))
                val_max = str(validation.get("max", ""))

            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "text",
                "Field Label": text,
                "Text Validation Type OR Show Slider Number": validation_type,
                "Text Validation Min": val_min,
                "Text Validation Max": val_max,
                "Required Field?": "y" if is_required else "",
            }))

        elif qtype == "long":
            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "notes",
                "Field Label": text,
                "Required Field?": "y" if is_required else "",
            }))

        elif qtype == "number":
            val_min = ""
            val_max = ""
            if "min" in q:
                val_min = str(q["min"])
            if "max" in q:
                val_max = str(q["max"])

            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "text",
                "Field Label": text,
                "Text Validation Type OR Show Slider Number": "number",
                "Text Validation Min": val_min,
                "Text Validation Max": val_max,
                "Required Field?": "y" if is_required else "",
            }))

        elif qtype == "date":
            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "text",
                "Field Label": text,
                "Text Validation Type OR Show Slider Number": "date_ymd",
                "Required Field?": "y" if is_required else "",
            }))

        elif qtype == "vas":
            min_val = q.get("min", 0)
            max_val = q.get("max", 100)
            min_label = ""
            max_label = ""
            if "min_label" in q:
                min_label = get_text(translations, q["min_label"])
            if "max_label" in q:
                max_label = get_text(translations, q["max_label"])

            slider_labels = ""
            if min_label or max_label:
                slider_labels = f"{min_label} | | {max_label}"

            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "slider",
                "Field Label": text,
                "Choices, Calculations, OR Slider Labels": slider_labels,
                "Text Validation Type OR Show Slider Number": "number",
                "Text Validation Min": str(min_val),
                "Text Validation Max": str(max_val),
                "Required Field?": "y" if is_required else "",
            }))

        elif qtype == "grid":
            # Expand grid into one radio field per row
            columns = q.get("columns", [])
            grid_rows = q.get("rows", [])

            col_choices = []
            for i, col in enumerate(columns):
                col_text = get_text(translations, col) if isinstance(col, str) else str(col)
                col_choices.append(f"{i + 1}, {strip_html(col_text)}")
            choices_str = " | ".join(col_choices)

            for j, row in enumerate(grid_rows):
                row_text = get_text(translations, row) if isinstance(row, str) else str(row)
                row_field = f"{field_name}_{j + 1}"

                rows.append(make_row(**{
                    "Variable / Field Name": row_field,
                    "Form Name": form_name,
                    "Section Header": section_header if j == 0 else "",
                    "Field Type": "radio",
                    "Field Label": f"{strip_html(text)}: {strip_html(row_text)}" if j == 0 else strip_html(row_text),
                    "Choices, Calculations, OR Slider Labels": choices_str,
                    "Required Field?": "y" if is_required else "",
                    "Matrix Group Name": field_name,
                }))

        elif qtype == "inst":
            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "descriptive",
                "Field Label": text,
            }))

        elif qtype == "constant_sum":
            # Expand into multiple text fields
            options = q.get("options", [])
            total = q.get("total", 100)

            for i, opt in enumerate(options):
                if isinstance(opt, dict):
                    opt_text = get_text(translations,
                                        opt.get("text_key",
                                                 opt.get("value", "")))
                else:
                    opt_text = get_text(translations, opt)
                opt_field = f"{field_name}_{i + 1}"
                label = (f"{strip_html(text)} (allocate {total} points): "
                         f"{strip_html(opt_text)}") if i == 0 else strip_html(opt_text)

                rows.append(make_row(**{
                    "Variable / Field Name": opt_field,
                    "Form Name": form_name,
                    "Section Header": section_header if i == 0 else "",
                    "Field Type": "text",
                    "Field Label": label,
                    "Text Validation Type OR Show Slider Number": "number",
                    "Text Validation Min": "0",
                    "Text Validation Max": str(total),
                    "Required Field?": "y" if is_required else "",
                }))

        elif qtype in ("image", "imageresponse"):
            img_file = q.get("image_file", "")
            label = text
            if img_file:
                label = f'<img src="{img_file}"/><br>{text}'

            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "descriptive",
                "Field Label": label,
            }))

        else:
            # Unknown type — emit as descriptive
            rows.append(make_row(**{
                "Variable / Field Name": field_name,
                "Form Name": form_name,
                "Section Header": section_header,
                "Field Type": "descriptive",
                "Field Label": f"[{qtype}] {text}",
            }))

        # Clear section header after first use
        section_header = ""

    # Add calculated scoring fields
    for score_id, score_def in scoring.items():
        if not isinstance(score_def, dict):
            continue

        method = score_def.get("method", "")
        expression = build_scoring_expression(score_id, score_def, definition)
        desc = score_def.get("description", "")

        if expression:
            note = f"{method}"
            if desc:
                note += f" — {desc}"

            rows.append(make_row(**{
                "Variable / Field Name": clean_field_name(f"{code}_{score_id}"),
                "Form Name": form_name,
                "Section Header": "Scoring" if score_id == list(scoring.keys())[0] else "",
                "Field Type": "calc",
                "Field Label": f"{score_id} Score",
                "Choices, Calculations, OR Slider Labels": expression,
                "Field Note": note,
            }))

    return rows


def _identify_matrix_groups(questions, definition):
    """Identify contiguous likert groups for REDCap matrix display."""
    groups = {}
    current_group = []
    current_points = None
    group_counter = 0

    for q in questions:
        if q.get("type") == "likert":
            points = q.get("likert_points",
                           definition.get("likert_options", {}).get("points", 5))
            if current_group and points == current_points:
                current_group.append(q["id"])
            else:
                if len(current_group) > 1:
                    group_counter += 1
                    group_name = f"matrix_{group_counter}"
                    for qid in current_group:
                        groups[qid] = group_name
                current_group = [q["id"]]
                current_points = points
        else:
            if len(current_group) > 1:
                group_counter += 1
                group_name = f"matrix_{group_counter}"
                for qid in current_group:
                    groups[qid] = group_name
            current_group = []
            current_points = None

    # Handle trailing group
    if len(current_group) > 1:
        group_counter += 1
        group_name = f"matrix_{group_counter}"
        for qid in current_group:
            groups[qid] = group_name

    return groups


def generate_csv(rows):
    """Convert rows to CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=REDCAP_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert OSD format to REDCap Data Dictionary CSV"
    )
    parser.add_argument("scale_dir", help="Path to scale directory")
    parser.add_argument("--output", "-o", help="Output CSV file (default: stdout)")
    parser.add_argument("--lang", default="en",
                        help="Language code (default: en)")
    args = parser.parse_args()

    scale_dir = Path(args.scale_dir)
    if not scale_dir.exists():
        print(f"Error: '{scale_dir}' not found", file=sys.stderr)
        sys.exit(1)

    def_file, code = find_definition_file(scale_dir)
    if def_file is None:
        print(f"Error: No definition file found in '{scale_dir}'",
              file=sys.stderr)
        sys.exit(1)

    with open(def_file, "r", encoding="utf-8") as f:
        definition = json.load(f)

    # Handle .osd wrapper format
    if 'definition' in definition and 'osd_version' in definition:
        definition = definition['definition']

    translations = load_translation(scale_dir, code, args.lang)

    rows = generate_redcap(definition, translations)
    csv_output = generate_csv(rows)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(csv_output)
        print(f"Written: {args.output} ({len(rows)} fields)")
    else:
        print(csv_output)


if __name__ == "__main__":
    main()
