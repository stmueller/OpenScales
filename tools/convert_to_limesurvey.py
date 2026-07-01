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
  vas           -> K  (Multiple Numerical slider; set slider_layout=1 after import)
  grid          -> F  (array, flexible) — rows=subquestions, columns=answers
  image         -> X  (text display with image path noted) [note emitted]
  imageresponse -> X  (text display with image path noted) [note emitted]

Limitations (noted to stderr):
  - Scoring, reverse coding, and dimension subscales must be configured
    manually in LimeSurvey after import.
  - VAS exports as K (Multiple Numerical) with one subquestion. Set slider_layout=1
    and slider_min/max in question attributes after import to activate the slider.
  - image/imageresponse become text-display items; images must be uploaded
    manually in LimeSurvey.
  - C9 validation: regex pattern → preg column; number_min/max → numeric
    regex; max_length, min_length, word count constraints not directly
    supported in LimeSurvey TSV and must be configured manually.
"""

import json
import random
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


def escape_em(text):
    """Escape curly braces so LimeSurvey Expression Manager doesn't parse them."""
    return text.replace("{", "&#123;").replace("}", "&#125;")


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
    "multi":         "L",
    "multicheck":    "M",
    "short":         "S",
    "long":          "T",
    "vas":           "K",
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
            relevance, escape_em(text), escape_em(help_), language,
            validation, mandatory, other, default, same_default,
        ])

    def render(self):
        return "\n".join("\t".join(str(cell) for cell in row) for row in self._rows)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _get_effective_scale(question, definition):
    """Resolve the effective response scale opts for a likert question."""
    rs_id = question.get("response_scale")
    if rs_id:
        rs = definition.get("response_scales", {}).get(rs_id)
        if rs:
            return rs
    return definition.get("likert_options", {})


def _get_likert_label_pairs(question, definition, primary_translations):
    """Return list of (numeric_value, label_key) for a likert question."""
    eff = _get_effective_scale(question, definition)
    points = question.get("likert_points", eff.get("points", 5))
    min_val = question.get("likert_min")
    if min_val is None or (isinstance(min_val, int) and min_val < 0):
        min_val = eff.get("min", 1)

    label_keys = question.get("likert_labels") or eff.get("labels") or []
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
# Option-set resolution
# ---------------------------------------------------------------------------

def resolve_options(item, defn):
    """Resolve options for a multi/multicheck item using option_sets fallback.

    Resolution order:
      1. item.get("options")           — inline options (highest priority)
      2. item.get("option_set")        — named set in defn["option_sets"]
      3. defn["option_sets"]["default"]— scale-level default set
      4. []                            — empty fallback
    """
    if "options" in item:
        return item["options"]
    option_sets = defn.get("option_sets", {})
    set_key = item.get("option_set")
    if set_key and set_key in option_sets:
        return option_sets[set_key]
    if "default" in option_sets:
        return option_sets["default"]
    return []


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
    # Survey-level settings. sid/gsid are required by the TSV importer to avoid
    # crashes on PHP 8.3; LS will assign a new sid on import regardless.
    dummy_sid = str(random.randint(100000, 999999))
    w.add(class_="S", name="sid", text=dummy_sid)
    w.add(class_="S", name="gsid", text="1")
    w.add(class_="S", name="format", text="I")
    w.add(class_="S", name="language", text=primary_lang)
    w.add(class_="S", name="template", text="inherit")
    w.add(class_="S", name="anonymized", text="N")
    w.add(class_="S", name="startdate", text="1980-01-01 00:00:00")
    if len(langs) > 1:
        w.add(class_="S", name="additional_languages",
              text=" ".join(langs[1:]))

    # ----------------------------------------------------------------- SL rows
    # Use first inst item text as participant-facing description; skip scale_info
    # description (researcher metadata, not for participants).
    first_inst = next((q for q in questions if q.get("type") == "inst"), None)
    for lang in langs:
        w.add(class_="SL", name="surveyls_title", text=survey_name,
              language=lang)
        if first_inst:
            trans = translations_by_lang.get(lang, {})
            inst_text = strip_html(get_text(trans, first_inst.get("text_key", ""), ""))
            if inst_text:
                w.add(class_="SL", name="surveyls_description", text=inst_text,
                      language=lang)

    # ------------------------------------------------------------------ G rows
    # Groups are emitted lazily: a default group is created only when a question
    # needs one and no section has been seen yet, preventing empty initial groups.
    code = scale_info.get("code", "scale").replace("_", "")
    likert_head_key = likert_opts.get("question_head", "")
    _group_emitted = [False]  # mutable flag for closure

    def _ensure_group():
        if _group_emitted[0]:
            return
        gid = w.next_id()
        for lang in langs:
            trans = translations_by_lang.get(lang, {})
            group_name = get_text(trans, likert_head_key, code) if likert_head_key else code
            w.add(id_=gid, class_="G",
                  name=group_name,
                  relevance="1",
                  language=lang)
        _group_emitted[0] = True

    # ------------------------------------------------------------------ Q rows
    # Likert items are batched into Array (F) questions grouped by response scale.
    # A new array starts when the response scale changes or a non-likert item appears.

    def _scale_key(q):
        """Return a hashable key identifying the response scale of a likert item."""
        rs_id = q.get("response_scale")
        if rs_id:
            return ("rs", rs_id)
        eff = _get_effective_scale(q, definition)
        labels = tuple(eff.get("labels", []))
        return ("lo", eff.get("points", 5), eff.get("min", 1), labels)

    def _flush_likert_block(block, block_scale_key):
        """Emit one Array (F) question for a block of likert items."""
        if not block:
            return
        _ensure_group()
        # Use first item's id as the array question name; LS title col is varchar(20)
        array_name = ("arr" + block[0]["id"].replace("_", ""))[:20]
        array_id = w.next_id()
        mandatory = _get_mandatory(block[0], definition)

        # Q row (type F = array)
        for lang in langs:
            w.add(id_=array_id, class_="Q",
                  type_scale="F",
                  name=array_name,
                  relevance="1",
                  text="",
                  language=lang,
                  mandatory=mandatory,
                  other="N")

        # SQ rows — one per item (the rows of the array)
        for q in block:
            sq_id = w.next_id()
            sq_code = q["id"].replace("_", "")
            text_key = q.get("text_key", q["id"])
            for lang in langs:
                trans = translations_by_lang.get(lang, {})
                text = strip_html(get_text(trans, text_key, q["id"]))
                w.add(id_=sq_id, class_="SQ",
                      type_scale="0",
                      name=sq_code,
                      relevance="1",
                      text=text,
                      language=lang)

        # A rows — scale point columns, from the first item's scale
        label_pairs = _get_likert_label_pairs(block[0], definition, primary_trans)
        for val, label_key in label_pairs:
            ans_code = f"A{val:03d}"
            for lang in langs:
                trans = translations_by_lang.get(lang, {})
                label_text = get_text(trans, label_key, str(val)) if label_key else str(val)
                w.add(id_=array_id, class_="A",
                      type_scale="0",
                      name=ans_code,
                      relevance=str(val),
                      text=label_text,
                      language=lang)

    likert_block = []
    current_scale_key = None

    for q in questions:
        qtype = q.get("type", "short")

        if qtype == "likert":
            sk = _scale_key(q)
            if sk != current_scale_key:
                _flush_likert_block(likert_block, current_scale_key)
                likert_block = []
                current_scale_key = sk
            likert_block.append(q)
            continue

        # Non-likert item — flush any pending block first
        _flush_likert_block(likert_block, current_scale_key)
        likert_block = []
        current_scale_key = None

        if qtype == "section":
            # Each section starts a new group (= page break in LimeSurvey)
            sec_code = q["id"].replace("_", "")[:20]
            text_key = q.get("text_key", q["id"])
            sec_gid = w.next_id()
            for lang in langs:
                trans = translations_by_lang.get(lang, {})
                group_name = get_text(trans, text_key, sec_code)
                w.add(id_=sec_gid, class_="G",
                      name=group_name,
                      relevance="1",
                      language=lang)
            _group_emitted[0] = True
            continue

        qid_str = q["id"].replace("_", "")
        text_key = q.get("text_key", qid_str)
        ls_type = TYPE_MAP.get(qtype, "T")

        _ensure_group()
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

        if qtype == "multi":
            # A rows: one per option, per language
            for i, opt in enumerate(resolve_options(q, definition)):
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
            for i, opt in enumerate(resolve_options(q, definition)):
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
            # Type K (Multiple Numerical) with slider_layout=1 renders as a real slider.
            # Parent Q row carries no text; item text goes on the single SQ row.
            # TSV doesn't support question attributes, so slider config must be set manually.
            min_v = q.get("min", q.get("min_value", 0))
            max_v = q.get("max", q.get("max_value", 100))

            def _anchor_label(anchor, trans):
                if isinstance(anchor, dict):
                    key = anchor.get("label", "")
                    return get_text(trans, key, key) if key else ""
                return get_text(trans, anchor, anchor) if anchor else ""

            sq_id = w.next_id()
            sq_code = (qid_str + "sq")[:20]
            for lang in langs:
                trans = translations_by_lang.get(lang, {})
                item_text = strip_html(get_text(trans, text_key, qid_str))
                anchors = q.get("anchors", [])
                min_label = get_text(trans, q["min_label"], "") if "min_label" in q else (
                    _anchor_label(anchors[0], trans) if anchors else "")
                max_label = get_text(trans, q["max_label"], "") if "max_label" in q else (
                    _anchor_label(anchors[-1], trans) if anchors else "")
                help_text = (min_label + (" | " if min_label and max_label else "") + max_label).strip()
                w.add(id_=sq_id, class_="SQ",
                      related_id=q_num_id,
                      name=sq_code,
                      relevance="1",
                      text=item_text,
                      help_=help_text,
                      language=lang)

            warnings.append(
                f"  {qid_str}: VAS (min={min_v}, max={max_v}) exported as K (Multiple Numerical) slider. "
                f"After import, set question attributes: slider_layout=1, slider_min={min_v}, "
                f"slider_max={max_v}, slider_accuracy=1."
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

    # Flush any trailing likert block
    _flush_likert_block(likert_block, current_scale_key)

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

    # Variant scales: export the primary language's variant (item sets can
    # differ per language, which a single multi-language LimeSurvey cannot represent)
    from osd_variants import flatten_variant
    if definition.get('variants') and args.extra_langs:
        print('Warning: variant scale — exporting only the primary language variant', file=sys.stderr)
    definition = flatten_variant(definition, args.lang)

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
