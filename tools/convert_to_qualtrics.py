#!/usr/bin/env python3
"""Convert Open Scale Definition (OSD) format to Qualtrics Advanced TXT format.

Usage:
    python3 convert_to_qualtrics.py <scale_directory> [--output FILE] [--lang LANG]
    python3 convert_to_qualtrics.py scales/grit/ --output grit_qualtrics.txt

Reads {code}.json and {code}.{lang}.json from a scale directory and generates
a Qualtrics Advanced Format TXT file suitable for import via:
    Survey Tools > Import/Export > Import Survey

Supported conversions:
  - likert (multi-item)  -> [[Question:Matrix]] with [[Choices]] + [[Answers]]
  - likert (single item) -> [[Question:MC]]
  - vas                  -> [[Question:Slider]]
  - multi                -> [[Question:MC]]
  - multicheck           -> [[Question:MC]] with [[MultipleAnswer]]
  - dropdown             -> [[Question:MC:Dropdown]]
  - short                -> [[Question:TE:SingleLine]]
  - long                 -> [[Question:TE:Essay]]
  - number               -> [[Question:TE:SingleLine]] (validation note)
  - date                 -> [[Question:TE:SingleLine]] (validation note)
  - grid                 -> [[Question:Matrix]]
  - inst                 -> [[Question:DB]]
  - rank                 -> [[Question:RO]]
  - constant_sum         -> [[Question:CS]]
  - semantic_differential -> [[Question:Matrix]]
  - image/imageresponse  -> [[Question:DB]] with HTML

Notes:
  - Qualtrics Advanced TXT does not support: scoring, reverse coding
    configuration, slider min/max/endpoint labels, or validation rules.
    These must be configured manually after import.
  - A scoring notes block is appended as a descriptive question for reference.
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


def html_to_qualtrics(text):
    """Convert text for Qualtrics (supports HTML, normalize newlines)."""
    return text.replace("\n", "<br>")


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


def is_reverse_coded(question, scoring):
    """Check if a question is reverse coded."""
    if question.get("coding") == -1:
        return True
    for score_def in scoring.values():
        if isinstance(score_def, dict) and "item_coding" in score_def:
            if question.get("id") in score_def["item_coding"]:
                if score_def["item_coding"][question["id"]] == -1:
                    return True
    return False


def _group_questions(questions, definition):
    """Group contiguous likert questions with the same scale into runs."""
    groups = []
    current_likert_run = []
    current_points = None

    for q in questions:
        qtype = q.get("type", "")
        if qtype == "likert":
            points = q.get("likert_points",
                           definition.get("likert_options", {}).get("points", 5))
            if current_likert_run and points == current_points:
                current_likert_run.append(q)
            else:
                if current_likert_run:
                    groups.append(current_likert_run)
                current_likert_run = [q]
                current_points = points
        else:
            if current_likert_run:
                groups.append(current_likert_run)
                current_likert_run = []
                current_points = None
            groups.append([q])

    if current_likert_run:
        groups.append(current_likert_run)

    return groups


def _emit_likert_matrix(lines, group, definition, translations, scoring):
    """Emit a group of likert items as a Qualtrics Matrix question."""
    first_id = group[0]["id"]
    likert_opts = definition.get("likert_options", {})

    question_head = ""
    if likert_opts.get("question_head"):
        question_head = get_text(translations, likert_opts["question_head"])

    lines.append("[[Question:Matrix]]")
    lines.append(f"[[ID:{first_id}]]")
    if question_head:
        lines.append(html_to_qualtrics(question_head))
    else:
        lines.append("Please rate the following items.")

    lines.append("[[Choices]]")
    for i, q in enumerate(group):
        text = get_text(translations, q.get("text_key", q["id"]))
        text = strip_html(text)
        lines.append(f"{i + 1}. {text}")

    labels = get_likert_labels(group[0], definition, translations)
    min_val = get_likert_min(group[0], definition)

    lines.append("[[Answers]]")
    for i, label in enumerate(labels):
        lines.append(f"{min_val + i}. {label}")

    lines.append("")


def _emit_single_likert(lines, question, definition, translations, scoring):
    """Emit a single likert item as a Qualtrics MC question."""
    text = get_text(translations, question.get("text_key", question["id"]))
    labels = get_likert_labels(question, definition, translations)
    min_val = get_likert_min(question, definition)

    lines.append("[[Question:MC]]")
    lines.append(f"[[ID:{question['id']}]]")
    lines.append(html_to_qualtrics(text))
    lines.append("[[Choices]]")
    for i, label in enumerate(labels):
        lines.append(f"{min_val + i}. {label}")
    lines.append("")


def _emit_single_question(lines, question, definition, translations, scoring):
    """Emit a single non-likert question."""
    qtype = question.get("type", "")
    qid = question["id"]
    text = get_text(translations, question.get("text_key", qid))

    if qtype == "inst":
        lines.append("[[Question:DB]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("")

    elif qtype == "multi":
        lines.append("[[Question:MC]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("[[Choices]]")
        for i, opt in enumerate(question.get("options", [])):
            if isinstance(opt, dict):
                opt_text = get_text(translations,
                                    opt.get("text_key", opt.get("value", "")))
            else:
                opt_text = get_text(translations, opt)
            lines.append(f"{i + 1}. {opt_text}")
        lines.append("")

    elif qtype == "multicheck":
        lines.append("[[Question:MC]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append("[[MultipleAnswer]]")
        lines.append(html_to_qualtrics(text))
        lines.append("[[Choices]]")
        for i, opt in enumerate(question.get("options", [])):
            if isinstance(opt, dict):
                opt_text = get_text(translations,
                                    opt.get("text_key", opt.get("value", "")))
            else:
                opt_text = get_text(translations, opt)
            lines.append(f"{i + 1}. {opt_text}")
        lines.append("")

    elif qtype == "dropdown":
        lines.append("[[Question:MC:Dropdown]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("[[Choices]]")
        for i, opt in enumerate(question.get("options", [])):
            if isinstance(opt, dict):
                opt_text = get_text(translations,
                                    opt.get("text_key", opt.get("value", "")))
            else:
                opt_text = get_text(translations, opt)
            lines.append(f"{i + 1}. {opt_text}")
        lines.append("")

    elif qtype == "short":
        lines.append("[[Question:TE:SingleLine]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("")

    elif qtype == "long":
        lines.append("[[Question:TE:Essay]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("")

    elif qtype == "number":
        lines.append("[[Question:TE:SingleLine]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("")

    elif qtype == "date":
        lines.append("[[Question:TE:SingleLine]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("")

    elif qtype == "vas":
        lines.append("[[Question:Slider]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("[[Choices]]")
        min_label = ""
        max_label = ""
        if "min_label" in question:
            min_label = get_text(translations, question["min_label"])
        if "max_label" in question:
            max_label = get_text(translations, question["max_label"])
        if min_label and max_label:
            label = f"{min_label} — {max_label}"
        else:
            label = "Rating"
        lines.append(f"1. {label}")
        lines.append("")

    elif qtype == "grid":
        columns = question.get("columns", [])
        rows = question.get("rows", [])

        lines.append("[[Question:Matrix]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))

        lines.append("[[Choices]]")
        for i, row in enumerate(rows):
            row_text = get_text(translations, row) if isinstance(row, str) else str(row)
            lines.append(f"{i + 1}. {strip_html(row_text)}")

        lines.append("[[Answers]]")
        for i, col in enumerate(columns):
            col_text = get_text(translations, col) if isinstance(col, str) else str(col)
            lines.append(f"{i + 1}. {strip_html(col_text)}")

        lines.append("")

    elif qtype == "rank":
        lines.append("[[Question:RO]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("[[Choices]]")
        for i, opt in enumerate(question.get("options", [])):
            if isinstance(opt, dict):
                opt_text = get_text(translations,
                                    opt.get("text_key", opt.get("value", "")))
            else:
                opt_text = get_text(translations, opt)
            lines.append(f"{i + 1}. {opt_text}")
        lines.append("")

    elif qtype == "constant_sum":
        lines.append("[[Question:CS]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("[[Choices]]")
        for i, opt in enumerate(question.get("options", [])):
            if isinstance(opt, dict):
                opt_text = get_text(translations,
                                    opt.get("text_key", opt.get("value", "")))
            else:
                opt_text = get_text(translations, opt)
            lines.append(f"{i + 1}. {opt_text}")
        lines.append("")

    elif qtype == "semantic_differential":
        items = question.get("items", [])
        points = question.get("points", 7)

        lines.append("[[Question:Matrix]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))

        lines.append("[[Choices]]")
        for i, item in enumerate(items):
            left = get_text(translations, item.get("left_key", ""))
            right = get_text(translations, item.get("right_key", ""))
            lines.append(f"{i + 1}. {left} — {right}")

        lines.append("[[Answers]]")
        for i in range(points):
            lines.append(f"{i + 1}. {i + 1}")

        lines.append("")

    elif qtype in ("image", "imageresponse"):
        lines.append("[[Question:DB]]")
        lines.append(f"[[ID:{qid}]]")
        img_file = question.get("image_file", "")
        img_html = f'<img src="{img_file}" /><br>' if img_file else ""
        lines.append(f"{img_html}{html_to_qualtrics(text)}")
        lines.append("")

    else:
        lines.append("[[Question:DB]]")
        lines.append(f"[[ID:{qid}]]")
        lines.append(html_to_qualtrics(text))
        lines.append("")


def _emit_question_group(lines, group, definition, translations, scoring):
    """Emit a group of questions to the Qualtrics TXT format."""
    if not group:
        return

    first_type = group[0].get("type", "")

    if first_type == "likert" and len(group) > 1:
        _emit_likert_matrix(lines, group, definition, translations, scoring)
    elif first_type == "likert" and len(group) == 1:
        _emit_single_likert(lines, group[0], definition, translations, scoring)
    else:
        for q in group:
            _emit_single_question(lines, q, definition, translations, scoring)


def _emit_scoring_notes(lines, definition, scoring):
    """Emit a descriptive block with scoring information for reference."""
    code = definition.get("scale_info", {}).get("code", "scale")

    lines.append("[[Question:DB]]")
    lines.append(f"[[ID:{code}_scoring_notes]]")

    parts = ["<b>Scoring Notes</b><br><br>"]
    parts.append("Configure scoring manually in Qualtrics. ")
    parts.append("This scale includes the following subscales:<br><br>")

    for score_id, score_def in scoring.items():
        if not isinstance(score_def, dict):
            continue
        method = score_def.get("method", "")
        items = score_def.get("items", [])
        desc = score_def.get("description", "")
        item_coding = score_def.get("item_coding", {})
        reverse_items = [k for k, v in item_coding.items() if v == -1]

        parts.append(f"<b>{score_id}</b>: {method} of [{', '.join(items)}]")
        if desc:
            parts.append(f" &mdash; {desc}")
        parts.append("<br>")
        if reverse_items:
            parts.append(
                f"&nbsp;&nbsp;Reverse-coded items: {', '.join(reverse_items)}<br>")
        parts.append("<br>")

    lines.append("".join(parts))
    lines.append("")


def generate_qualtrics(definition, translations):
    """Generate Qualtrics Advanced TXT from OSD format."""
    lines = ["[[AdvancedFormat]]", ""]

    name = definition.get("scale_info", {}).get("name", "Scale")
    questions = definition.get("items") or definition.get("questions", [])
    scoring = definition.get("scoring", {})
    pages = definition.get("pages", None)

    lines.append(f"[[Block:{name}]]")
    lines.append("")

    if pages:
        q_by_id = {q["id"]: q for q in questions}
        first_page = True
        for page in pages:
            if not first_page:
                lines.append("[[PageBreak]]")
                lines.append("")
            first_page = False

            page_items = [q_by_id[qid] for qid in page.get("items", [])
                          if qid in q_by_id]
            _emit_question_group(lines, page_items, definition,
                                 translations, scoring)
    else:
        groups = _group_questions(questions, definition)
        first_group = True
        for group in groups:
            if not first_group:
                lines.append("[[PageBreak]]")
                lines.append("")
            first_group = False
            _emit_question_group(lines, group, definition,
                                 translations, scoring)

    if scoring:
        lines.append("[[PageBreak]]")
        lines.append("")
        _emit_scoring_notes(lines, definition, scoring)

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert OSD format to Qualtrics Advanced TXT"
    )
    parser.add_argument("scale_dir", help="Path to scale directory")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
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

    output = generate_qualtrics(definition, translations)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Written: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
