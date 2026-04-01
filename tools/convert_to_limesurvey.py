#!/usr/bin/env python3
"""Convert Open Scale Definition (OSD) format to LimeSurvey Tab Separated Value (.txt).

Usage:
    python3 convert_to_limesurvey.py <scale_directory> [--output FILE] [--lang LANG]
    python3 convert_to_limesurvey.py scales/grit/ --output grit_limesurvey.txt
    python3 convert_to_limesurvey.py scales/UEQS/ --lang en --extra-langs de fr

Reads {code}.json and {code}.{lang}.json from a scale directory and generates
a LimeSurvey TSV file suitable for import.

Import navigation (LimeSurvey 6.x):
    Home page → "Create new survey" button → "Import" tab → choose .txt file

Import navigation (LimeSurvey 5.x and older):
    Surveys menu → "Import survey" → choose .txt file

IMPORTANT: LimeSurvey requires the output file to have a .txt extension.
The output file uses UTF-8 with BOM as required by LimeSurvey.

Supported conversions:
  inst          -> X  (boilerplate / text display)
  likert        -> L  (list radio) — scale points become answer options
  multi         -> L  (list radio, single select) — options become answers
  multicheck    -> M  (multiple choice checkboxes) — options become subquestions
  short         -> S  (short free text)
  long          -> T  (long free text)
  vas           -> N  (numerical input) [approximation — note emitted]
  grid          -> F  (array, flexible) — rows=subquestions, columns=answers
  image         -> X  (text display with image path noted) [note emitted]
  imageresponse -> X  (text display with image path noted) [note emitted]

Limitations (noted to stderr):
  - Scoring, reverse coding, and dimension subscales must be configured
    manually in LimeSurvey after import.
  - VAS slider is approximated as numerical input (N).
  - image/imageresponse become text-display items; images must be uploaded
    manually in LimeSurvey.
  - C9 validation: regex pattern → preg column; number_min/max → numeric
    regex; max_length, min_length, word count constraints not directly
    supported in LimeSurvey TSV and must be configured manually.
"""

import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as other converters in this directory)
# ---------------------------------------------------------------------------

def find_definition_file(scale_dir):
    """Find the main .json definition file in a scale directory."""
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


def load_translation(scale_dir, code, lang):
    """Load a translation file, trying common naming patterns."""
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


def get_text(translations, key, fallback=None):
    """Look up a translation key, case-insensitively, with optional fallback."""
    if not key:
        return fallback or ""
    if key in translations:
        return translations[key]
    key_lo = key.lower()
    for k, v in translations.items():
        if k.lower() == key_lo:
            return v
    return fallback if fallback is not None else key


def strip_html(text):
    """Strip HTML tags for plain-text output."""
    return re.sub(r"<[^>]+>", "", text).strip()


# ---------------------------------------------------------------------------
# LimeSurvey TSV specifics
# ---------------------------------------------------------------------------

# Standard 14-column header (columns 15+ are optional extended attributes)
COLUMNS = [
    "id", "related_id", "class", "type/scale", "name",
    "relevance", "text", "help", "language",
    "validation", "mandatory", "other", "default", "same_default",
]

# OpenScales type → LimeSurvey one-letter type code
TYPE_MAP = {
    "inst":          "X",
    "likert":        "L",
    "multi":         "L",
    "multicheck":    "M",
    "short":         "S",
    "long":          "T",
    "vas":           "N",
    "grid":          "F",
    "image":         "X",
    "imageresponse": "X",
}


class TSVWriter:
    """Accumulates TSV rows and renders them."""

    def __init__(self):
        self._rows = [COLUMNS]
        self._id_counter = 1

    def next_id(self):
        n = self._id_counter
        self._id_counter += 1
        return n

    def add(self, id_="", related_id="", class_="", type_scale="", name="",
            relevance="", text="", help_="", language="",
            validation="", mandatory="", other="", default="", same_default=""):
        self._rows.append([
            str(id_), str(related_id), class_, type_scale, name,
            relevance, text, help_, language,
            validation, mandatory, other, default, same_default,
        ])

    def render(self):
        return "\n".join("\t".join(str(cell) for cell in row) for row in self._rows)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _get_likert_label_pairs(question, definition, primary_translations):
    """Return list of (numeric_value, label_key) for a likert question."""
    likert_opts = definition.get("likert_options", {})
    points = question.get("likert_points", likert_opts.get("points", 5))
    min_val = question.get("likert_min")
    if min_val is None or (isinstance(min_val, int) and min_val < 0):
        min_val = likert_opts.get("min", 1)

    label_keys = question.get("likert_labels") or likert_opts.get("labels") or []
    # Pad to length if needed
    while len(label_keys) < points:
        label_keys.append(None)

    return [(min_val + i, label_keys[i]) for i in range(points)]


def _get_mandatory(question, definition):
    """Return 'Y' if required, '' otherwise."""
    req = question.get("required")
    if req is None:
        req = question.get("required_state")  # PEBL runner field
    if req is True or req == 1:
        return "Y"
    if req is False or req == 0:
        return ""
    # Scale-level default
    default = definition.get("default_required")
    if default is True:
        return "Y"
    if default is False:
        return ""
    # Type-based defaults: scored types default to required
    scored = {"likert", "vas", "multi", "grid", "multicheck"}
    return "Y" if question.get("type") in scored else ""


OP_MAP = {
    "equals":       "==",
    "not_equals":   "!=",
    "greater_than": ">",
    "less_than":    "<",
}


def _simple_cond(cond):
    """Convert one simple condition dict to a LimeSurvey EM expression fragment."""
    source = (cond.get("question") or cond.get("parameter")
              or cond.get("source_name", "?"))
    op = OP_MAP.get(cond.get("operator", cond.get("op", "equals")), "==")
    value = cond.get("value", "")
    try:
        float(value)
        val_str = str(value)
    except (TypeError, ValueError):
        val_str = f'"{value}"'
    return f"{{{source}}} {op} {val_str}"


def _visible_when_to_relevance(visible_when):
    """Convert OpenScales visible_when to LimeSurvey relevance expression."""
    if not visible_when:
        return "1"
    if "all" in visible_when:
        parts = [_simple_cond(c) for c in visible_when["all"]]
        return "(" + " and ".join(parts) + ")"
    if "any" in visible_when:
        parts = [_simple_cond(c) for c in visible_when["any"]]
        return "(" + " or ".join(parts) + ")"
    return _simple_cond(visible_when)


def _get_validation(question):
    """Map C9 validation rules to LimeSurvey preg (regex) field."""
    val = question.get("validation", {})
    if not val:
        return ""
    if "pattern" in val:
        return val["pattern"]
    if "number_min" in val or "number_max" in val:
        # Restrict to numeric input
        return r"^\-?[0-9]+(\.[0-9]+)?$"
    return ""


def _option_key_and_code(opt, index):
    """Return (text_key_or_text, answer_code) for a multi/multicheck option."""
    if isinstance(opt, dict):
        key = opt.get("text_key", opt.get("value", f"A{index+1:03d}"))
        code = opt.get("value", f"A{index+1:03d}")
    else:
        key = opt
        code = f"A{index+1:03d}"
    return key, code


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_limesurvey(definition, translations_by_lang, primary_lang="en"):
    """Generate LimeSurvey TSV content from an OSD definition.

    Returns (tsv_string, warnings_list).
    """
    w = TSVWriter()
    warnings = []

    scale_info = definition.get("scale_info", {})
    survey_name = scale_info.get("name", "Scale")
    questions = definition.get("items") or definition.get("questions", [])
    likert_opts = definition.get("likert_options", {})

    # Ensure primary language is first
    langs = [primary_lang] + [l for l in translations_by_lang if l != primary_lang]
    primary_trans = translations_by_lang.get(primary_lang, {})

    # ------------------------------------------------------------------ S rows
    # Minimal survey-level settings LimeSurvey needs
    w.add(class_="S", name="format", text="I")          # I = one question per page
    w.add(class_="S", name="language", text=primary_lang)
    if len(langs) > 1:
        w.add(class_="S", name="additional_languages",
              text=" ".join(langs[1:]))

    # ----------------------------------------------------------------- SL rows
    # Localised survey title (and description if present)
    desc = scale_info.get("description", "")
    for lang in langs:
        w.add(class_="SL", name="surveyls_title", text=survey_name,
              language=lang)
        if desc:
            w.add(class_="SL", name="surveyls_description", text=desc,
                  language=lang)

    # ------------------------------------------------------------------ G rows
    # One group containing all questions
    group_id = w.next_id()
    code = scale_info.get("code", "scale")
    for lang in langs:
        w.add(id_=group_id, class_="G",
              name=code,
              relevance="1",
              text="",
              language=lang)

    # ------------------------------------------------------------------ Q rows
    for q in questions:
        qtype = q.get("type", "short")
        qid_str = q["id"]
        text_key = q.get("text_key", qid_str)
        ls_type = TYPE_MAP.get(qtype, "T")

        q_num_id = w.next_id()
        relevance = _visible_when_to_relevance(q.get("visible_when"))
        mandatory = _get_mandatory(q, definition)
        validation = _get_validation(q)

        # Q row — one per language
        for lang in langs:
            trans = translations_by_lang.get(lang, {})
            text = strip_html(get_text(trans, text_key, qid_str))
            help_key = q.get("help_key", "")
            help_text = get_text(trans, help_key, "") if help_key else ""
            w.add(id_=q_num_id, class_="Q",
                  type_scale=ls_type,
                  name=qid_str,
                  relevance=relevance,
                  text=text,
                  help_=help_text,
                  language=lang,
                  validation=validation,
                  mandatory=mandatory,
                  other="N")

        # ---------------------------------------------------------- Sub-rows

        if qtype == "likert":
            # A rows: one per scale point, per language
            label_pairs = _get_likert_label_pairs(q, definition, primary_trans)
            for val, label_key in label_pairs:
                ans_code = f"A{val:03d}"
                for lang in langs:
                    trans = translations_by_lang.get(lang, {})
                    if label_key:
                        label_text = get_text(trans, label_key, str(val))
                    else:
                        label_text = str(val)
                    w.add(id_=q_num_id, class_="A",
                          type_scale="0",
                          name=ans_code,
                          relevance=str(val),   # assessment_value
                          text=label_text,
                          language=lang)

        elif qtype == "multi":
            # A rows: one per option, per language
            for i, opt in enumerate(q.get("options", [])):
                opt_key, opt_code = _option_key_and_code(opt, i)
                for lang in langs:
                    trans = translations_by_lang.get(lang, {})
                    opt_text = get_text(trans, opt_key, opt_key)
                    w.add(id_=q_num_id, class_="A",
                          type_scale="0",
                          name=opt_code,
                          relevance=str(i + 1),
                          text=opt_text,
                          language=lang)

        elif qtype == "multicheck":
            # SQ rows: type M uses subquestions as checkbox options
            for i, opt in enumerate(q.get("options", [])):
                sq_id = w.next_id()
                opt_key, _ = _option_key_and_code(opt, i)
                sq_code = f"SQ{i+1:03d}"
                for lang in langs:
                    trans = translations_by_lang.get(lang, {})
                    opt_text = get_text(trans, opt_key, opt_key)
                    w.add(id_=sq_id, class_="SQ",
                          type_scale="0",
                          name=sq_code,
                          relevance="1",
                          text=opt_text,
                          language=lang)

        elif qtype == "grid":
            # SQ rows for rows, A rows for columns
            for i, row_key in enumerate(q.get("rows", [])):
                sq_id = w.next_id()
                sq_code = f"SQ{i+1:03d}"
                for lang in langs:
                    trans = translations_by_lang.get(lang, {})
                    row_text = get_text(trans, row_key, row_key)
                    w.add(id_=sq_id, class_="SQ",
                          type_scale="0",
                          name=sq_code,
                          relevance="1",
                          text=row_text,
                          language=lang)
            for i, col_key in enumerate(q.get("columns", [])):
                col_code = f"A{i+1:03d}"
                for lang in langs:
                    trans = translations_by_lang.get(lang, {})
                    col_text = get_text(trans, col_key, col_key)
                    w.add(id_=q_num_id, class_="A",
                          type_scale="0",
                          name=col_code,
                          relevance=str(i + 1),
                          text=col_text,
                          language=lang)

        elif qtype == "vas":
            min_v = q.get("min", q.get("min_value", 0))
            max_v = q.get("max", q.get("max_value", 100))
            warnings.append(
                f"  {qid_str}: VAS (min={min_v}, max={max_v}) → N (numerical "
                f"input). Configure slider/range manually in LimeSurvey."
            )

        elif qtype in ("image", "imageresponse"):
            img = q.get("image_file", q.get("image", ""))
            if img:
                warnings.append(
                    f"  {qid_str}: {qtype} → X (text display). "
                    f"Upload '{img}' and embed manually in LimeSurvey."
                )

        # Emit notes for unsupported C9 constraints
        val_obj = q.get("validation", {})
        unsupported = []
        for field in ("min_length", "max_length", "min_words", "max_words",
                      "min_selected", "max_selected"):
            if field in val_obj:
                unsupported.append(f"{field}={val_obj[field]}")
        if unsupported:
            warnings.append(
                f"  {qid_str}: validation constraints not directly supported "
                f"in LimeSurvey TSV: {', '.join(unsupported)}. "
                f"Configure via question attributes after import."
            )

    # ---------------------------------------------------------- Scoring note
    scoring = definition.get("scoring", {})
    if scoring:
        warnings.append(
            "Scoring must be configured manually in LimeSurvey (Assessments "
            "or custom scripting). Subscales in this scale:"
        )
        for score_id, score_def in scoring.items():
            if not isinstance(score_def, dict):
                continue
            method = score_def.get("method", "")
            items = score_def.get("items", [])
            item_coding = score_def.get("item_coding", {})
            reverse = [k for k, v in item_coding.items() if v == -1]
            line = f"  {score_id}: {method} of [{', '.join(items)}]"
            if reverse:
                line += f" — reverse-coded: {', '.join(reverse)}"
            warnings.append(line)

    return w.render(), warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert OSD format to LimeSurvey TSV (.txt)"
    )
    parser.add_argument("scale_dir", help="Path to scale directory")
    parser.add_argument("--output", "-o",
                        help="Output file path (default: stdout)")
    parser.add_argument("--lang", default="en",
                        help="Primary language code (default: en)")
    parser.add_argument("--extra-langs", nargs="*", default=[],
                        metavar="LANG",
                        help="Additional language codes to include (e.g. de fr)")
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

    all_langs = [args.lang] + (args.extra_langs or [])
    translations_by_lang = {}
    for lang in all_langs:
        t = load_translation(scale_dir, code, lang)
        if t:
            translations_by_lang[lang] = t
        else:
            print(f"Warning: No translation file found for language '{lang}'",
                  file=sys.stderr)

    tsv_content, warnings = generate_limesurvey(
        definition, translations_by_lang, primary_lang=args.lang
    )

    if warnings:
        print("Conversion notes:", file=sys.stderr)
        for msg in warnings:
            print(msg, file=sys.stderr)
        print(file=sys.stderr)

    # LimeSurvey TSV requires UTF-8 with BOM
    encoded = tsv_content.encode("utf-8-sig")
    if args.output:
        Path(args.output).write_bytes(encoded)
        print(f"Written: {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
