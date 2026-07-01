#!/usr/bin/env python3
"""Convert Open Scale Definition (OSD) format to ReproSchema JSON-LD format.

Usage:
    python3 convert_to_reproschema.py <scale_directory> [--output DIR] [--lang LANG] [--all-langs]
    python3 convert_to_reproschema.py scales/GAD7/
    python3 convert_to_reproschema.py scales/GAD7/ --output GAD7_reproschema/
    python3 convert_to_reproschema.py scales/GAD7/ --lang de
    python3 convert_to_reproschema.py scales/GAD7/ --all-langs

Reads {code}.osd (or {code}.json) and translation files from a scale directory
and generates a ReproSchema JSON-LD activity directory:

    {CODE}/
      {CODE}_schema          # activity schema (no file extension)
      items/
        {item_id}            # one file per item (no extension)
      valueConstraints       # shared Likert response options (if applicable)

Item type mapping:
  likert       -> radio (shared valueConstraints file)
  multi        -> radio (inline choices, multipleChoice: false)
  multicheck   -> radio (inline choices, multipleChoice: true)
  short        -> text  (xsd:string)
  long         -> text  (xsd:string)
  number       -> xsd:int (xsd:integer)
  vas          -> slider
  grid         -> one radio item per grid row (approximation)
  inst         -> static (display only)
  section      -> skipped from ui.order (structural only)
  Scoring      -> readonly compute items + jsExpression in activity schema
"""

import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# ReproSchema context URL
# ---------------------------------------------------------------------------

REPROSCHEMA_CONTEXT = (
    "https://raw.githubusercontent.com/ReproNim/reproschema/"
    "main/releases/1.0.0/reproschema"
)
SCHEMA_VERSION = "1.0.0"
ACTIVITY_VERSION = "0.0.1"


# ---------------------------------------------------------------------------
# OSD loading helpers (standalone, mirroring convert_to_xlsform.py patterns)
# ---------------------------------------------------------------------------

def find_definition_file(scale_dir):
    """Find the main .osd or .json definition file in scale_dir.

    Returns (path, code) where code is the scale identifier string.
    """
    p = Path(scale_dir)
    code = p.name
    # Prefer explicit {code}.osd
    for f in sorted(p.glob("*.osd")):
        return f, f.stem
    # Fall back to a .json that doesn't look like a translation file
    definition = p / f"{code}.json"
    if definition.exists():
        return definition, code
    for f in sorted(p.glob("*.json")):
        if not re.match(r".*\.\w{2}(-\w+)?\.json$", f.name):
            return f, f.stem
    return None, code


def load_translation(scale_dir, code, lang="en"):
    """Load a single translation dict for the given language.

    Checks (in order):
      - {code}.{lang}.json
      - {code}.pbl-{lang}.json
      - Embedded translations in any .osd file
    Returns {} if nothing found.
    """
    p = Path(scale_dir)
    for pattern in [f"{code}.{lang}.json", f"{code}.pbl-{lang}.json"]:
        path = p / pattern
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    # Fall back to embedded .osd translations
    for osd_file in p.glob("*.osd"):
        try:
            with open(osd_file, "r", encoding="utf-8") as f:
                osd_data = json.load(f)
            embedded = osd_data.get("translations", {})
            if lang in embedded:
                return embedded[lang]
            if embedded:
                return next(iter(embedded.values()))
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def load_all_translations(scale_dir, code, primary_lang="en"):
    """Return {lang: translation_dict} for all available languages.

    Collects from embedded .osd translations and legacy separate files.
    """
    p = Path(scale_dir)
    translations = {}

    # Embedded translations in .osd
    for osd_file in sorted(p.glob("*.osd")):
        try:
            with open(osd_file, "r", encoding="utf-8") as f:
                osd_data = json.load(f)
            translations.update(osd_data.get("translations", {}))
        except (json.JSONDecodeError, KeyError):
            pass
        break  # expect at most one .osd

    # Legacy separate translation files: {code}.{lang}.json
    for tf in p.glob(f"{code}.*.json"):
        m = re.match(rf"{re.escape(code)}\.(\w{{2}}(?:-\w+)?)\.json$", tf.name)
        if m:
            lang_code = m.group(1)
            if lang_code not in translations:
                try:
                    with open(tf, "r", encoding="utf-8") as f:
                        translations[lang_code] = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass

    # Legacy: {code}.pbl-{lang}.json
    for tf in p.glob(f"{code}.pbl-*.json"):
        m = re.match(rf"{re.escape(code)}\.pbl-(\w{{2}}(?:-\w+)?)\.json$", tf.name)
        if m:
            lang_code = m.group(1)
            if lang_code not in translations:
                try:
                    with open(tf, "r", encoding="utf-8") as f:
                        translations[lang_code] = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass

    if primary_lang not in translations:
        t = load_translation(scale_dir, code, primary_lang)
        if t:
            translations[primary_lang] = t

    return translations


def get_text(translations, key, fallback=None):
    """Look up key in translations dict with case-insensitive fallback."""
    if not key:
        return fallback if fallback is not None else ""
    if key in translations:
        return translations[key]
    key_lo = key.lower()
    for k, v in translations.items():
        if k.lower() == key_lo:
            return v
    return fallback if fallback is not None else key


def get_effective_scale(item, definition):
    """Return the response scale options dict for a likert item."""
    rs_id = item.get("response_scale")
    if rs_id:
        rs = definition.get("response_scales", {}).get(rs_id)
        if rs:
            return rs
    return definition.get("likert_options", {})


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


def get_likert_choices(item, definition, translations_by_lang, primary_lang):
    """Build a list of {name, value} choice dicts for a likert item.

    translations_by_lang: {lang: trans_dict}
    Returns list of {"name": {"en": "label", ...}, "value": int}
    """
    eff = get_effective_scale(item, definition)
    min_val = eff.get("min", 1)
    label_keys = item.get("likert_labels") or eff.get("labels", [])
    points = item.get("likert_points", eff.get("points", 5))

    choices = []
    for i in range(points):
        val = min_val + i
        lbl_key = label_keys[i] if i < len(label_keys) else None
        name_dict = {}
        for lang, trans in translations_by_lang.items():
            if lbl_key:
                text = get_text(trans, lbl_key, "")
            else:
                text = str(val)
            name_dict[lang] = text
        choices.append({"name": name_dict, "value": val})
    return choices


def _scoring_item_pairs(score_def):
    """Return list of (item_id, coding) from a score definition.

    Handles:
      - items: ["id1", "id2"] with optional item_coding: {"id1": -1}
      - items: {"id1": 1, "id2": -1}  (coding embedded in dict)
      - items: [["id1", 1], ["id2", -1]]  (list of pairs)
    """
    items_raw = score_def.get("items", [])
    item_coding = score_def.get("item_coding", {})

    if isinstance(items_raw, dict):
        return list(items_raw.items())
    if isinstance(items_raw, list):
        if items_raw and isinstance(items_raw[0], (list, tuple)):
            # List of [item_id, coding] pairs
            return [(pair[0], pair[1]) for pair in items_raw]
        # Plain list of ids
        return [(iid, item_coding.get(iid, 1)) for iid in items_raw]
    return []


# ---------------------------------------------------------------------------
# visible_when → ReproSchema isVis JavaScript expression
# ---------------------------------------------------------------------------

def _leaf_condition_to_js(cond):
    """Convert a single OSD condition dict to a JS expression string."""
    if not isinstance(cond, dict):
        return "true"

    # Parameter-only conditions resolve at launch — always visible at runtime
    if "parameter" in cond and "item" not in cond and "question" not in cond:
        return "true"

    item = cond.get("item") or cond.get("question")
    if not item:
        return "true"

    op = cond.get("operator", cond.get("op", "equals"))
    value = cond.get("value")

    if op == "equals":
        val_str = _js_literal(value)
        return f"{item} === {val_str}"
    elif op == "not_equals":
        val_str = _js_literal(value)
        return f"{item} !== {val_str}"
    elif op == "greater_than":
        return f"{item} > {value}"
    elif op == "less_than":
        return f"{item} < {value}"
    elif op == "is_answered":
        return f"{item} !== null && {item} !== undefined && {item} !== ''"
    elif op == "is_not_answered":
        return f"{item} === null || {item} === undefined || {item} === ''"
    elif op == "is_true":
        return f"{item} === true || {item} === 1 || {item} === 'true'"
    elif op == "is_false":
        return f"{item} === false || {item} === 0 || {item} === 'false'"
    else:
        val_str = _js_literal(value)
        return f"{item} === {val_str}"


def _js_literal(value):
    """Return a JS literal string for value (quoted if string, bare if numeric)."""
    if value is None:
        return "null"
    try:
        float(str(value))
        return str(value)
    except (TypeError, ValueError):
        return f"'{value}'"


def visible_when_to_is_vis(visible_when):
    """Convert OSD visible_when to a ReproSchema isVis value.

    Returns True (always visible), or a JS expression string.
    """
    if not visible_when:
        return True
    if isinstance(visible_when, str):
        # String shorthand: parameter name — resolves at launch, treat as visible
        return True
    if not isinstance(visible_when, dict):
        return True

    if "all" in visible_when:
        parts = [visible_when_to_is_vis(c) for c in visible_when["all"]]
        # If any sub-condition is always True (bool), simplify
        js_parts = [p if isinstance(p, str) else ("true" if p else "false")
                    for p in parts]
        return "(" + ") && (".join(js_parts) + ")"
    if "any" in visible_when:
        parts = [visible_when_to_is_vis(c) for c in visible_when["any"]]
        js_parts = [p if isinstance(p, str) else ("true" if p else "false")
                    for p in parts]
        return "(" + ") || (".join(js_parts) + ")"
    if "not" in visible_when:
        inner = visible_when_to_is_vis(visible_when["not"])
        if isinstance(inner, bool):
            return not inner
        return f"!({inner})"

    # Leaf condition
    parameter_only = ("parameter" in visible_when
                      and "item" not in visible_when
                      and "question" not in visible_when)
    if parameter_only:
        return True

    return _leaf_condition_to_js(visible_when)


# ---------------------------------------------------------------------------
# Scoring → jsExpression
# ---------------------------------------------------------------------------

def build_js_expression(score_def, definition, code, all_score_ids,
                        active_item_ids=None):
    """Build a ReproSchema jsExpression for a score.

    Returns expression string, or None if not computable.
    """
    method = score_def.get("method", "")
    raw_pairs = _scoring_item_pairs(score_def)
    if active_item_ids is not None:
        item_pairs = [(iid, c) for iid, c in raw_pairs if iid in active_item_ids]
    else:
        item_pairs = raw_pairs
    scores_refs = score_def.get("scores", [])

    # Likert range for reverse coding
    eff = definition.get("likert_options", {})
    min_val = eff.get("min", 1)
    points = eff.get("points", 5)
    max_val = eff.get("max", min_val + points - 1)

    def item_expr(item_id, coding):
        if coding == -1:
            return f"({min_val + max_val} - {item_id})"
        return item_id

    def score_ref(sid):
        return f"{code}_{sid}"

    if method in ("sum", "sum_coded"):
        if scores_refs and not item_pairs:
            return " + ".join(score_ref(s) for s in scores_refs)
        if scores_refs:
            parts = [item_expr(iid, c) for iid, c in item_pairs]
            parts += [score_ref(s) for s in scores_refs]
            return " + ".join(parts)
        if not item_pairs:
            return None
        return " + ".join(item_expr(iid, c) for iid, c in item_pairs)

    elif method in ("mean", "mean_coded"):
        if scores_refs and not item_pairs:
            n = len(scores_refs)
            return f"({' + '.join(score_ref(s) for s in scores_refs)}) / {n}"
        if not item_pairs:
            return None
        parts = [item_expr(iid, c) for iid, c in item_pairs]
        refs = [score_ref(s) for s in scores_refs]
        all_parts = parts + refs
        n = len(all_parts)
        return f"({' + '.join(all_parts)}) / {n}"

    elif method == "weighted_sum":
        weights = score_def.get("weights", {})
        if scores_refs and not item_pairs:
            return " + ".join(f"({weights.get(s, 1)} * {score_ref(s)})"
                              for s in scores_refs)
        if not item_pairs:
            return None
        parts = [f"({weights.get(iid, 1)} * {item_expr(iid, c)})"
                 for iid, c in item_pairs]
        return " + ".join(parts)

    elif method == "sum_correct":
        if not item_pairs:
            return None
        return " + ".join(iid for iid, _ in item_pairs)

    else:
        # Generic fallback — plain sum
        if scores_refs and not item_pairs:
            return " + ".join(score_ref(s) for s in scores_refs)
        if not item_pairs:
            return None
        return " + ".join(item_expr(iid, c) for iid, c in item_pairs)


# ---------------------------------------------------------------------------
# ReproSchema JSON-LD builders
# ---------------------------------------------------------------------------

def _base_item(item_id):
    """Return the base structure shared by all item files."""
    return {
        "@context": REPROSCHEMA_CONTEXT,
        "id": item_id,
        "category": "Item",
        "schemaVersion": SCHEMA_VERSION,
        "version": ACTIVITY_VERSION,
        "prefLabel": {},
    }


def build_item_file(item, definition, translations_by_lang, primary_lang):
    """Build the JSON-LD dict for a single item file.

    Returns (item_id, dict).
    """
    item_id = item["id"]
    item_type = item.get("type", "short")
    text_key = item.get("text_key", item_id)

    obj = _base_item(item_id)

    # prefLabel: item id in each lang
    for lang in translations_by_lang:
        obj["prefLabel"][lang] = item_id

    # question text (multilingual)
    question = {}
    for lang, trans in translations_by_lang.items():
        question[lang] = get_text(trans, text_key, item_id)
    if question:
        obj["question"] = question

    if item_type == "likert":
        choices = get_likert_choices(item, definition, translations_by_lang,
                                     primary_lang)
        obj["ui"] = {"inputType": "radio"}
        obj["responseOptions"] = "../valueConstraints"

    elif item_type == "multi":
        options = resolve_options(item, definition)
        choices = _build_option_choices(options, translations_by_lang)
        obj["ui"] = {"inputType": "radio"}
        obj["responseOptions"] = {
            "choices": choices,
            "multipleChoice": False,
            "valueType": ["xsd:integer"],
        }

    elif item_type == "multicheck":
        options = resolve_options(item, definition)
        choices = _build_option_choices(options, translations_by_lang)
        obj["ui"] = {"inputType": "radio"}
        obj["responseOptions"] = {
            "choices": choices,
            "multipleChoice": True,
            "valueType": ["xsd:anyURI"],
        }

    elif item_type == "short":
        obj["ui"] = {"inputType": "text"}
        obj["responseOptions"] = {"valueType": ["xsd:string"]}

    elif item_type == "long":
        obj["ui"] = {"inputType": "text"}
        obj["responseOptions"] = {"valueType": ["xsd:string"]}

    elif item_type == "number":
        obj["ui"] = {"inputType": "xsd:int"}
        obj["responseOptions"] = {"valueType": ["xsd:integer"]}

    elif item_type == "vas":
        obj["ui"] = {"inputType": "slider"}
        min_val = item.get("min", item.get("min_value", 0))
        max_val = item.get("max", item.get("max_value", 100))
        obj["responseOptions"] = {
            "valueType": ["xsd:integer"],
            "minValue": min_val,
            "maxValue": max_val,
        }

    elif item_type in ("inst", "section"):
        obj["ui"] = {"inputType": "static"}
        # question already set above; no responseOptions for display-only

    elif item_type == "grid":
        # Grid items are handled by expanding into per-row items outside this
        # function; this path should not normally be reached.
        obj["ui"] = {"inputType": "radio"}
        obj["responseOptions"] = {"valueType": ["xsd:integer"]}

    else:
        # Unknown — treat as text
        obj["ui"] = {"inputType": "text"}
        obj["responseOptions"] = {"valueType": ["xsd:string"]}

    return item_id, obj


def _build_option_choices(options, translations_by_lang):
    """Build ReproSchema choices list from OSD options list."""
    choices = []
    for i, opt in enumerate(options):
        if isinstance(opt, dict):
            val = opt.get("value", i + 1)
            text_key = opt.get("text_key", str(val))
        else:
            val = i + 1
            text_key = str(opt)
        name_dict = {}
        for lang, trans in translations_by_lang.items():
            name_dict[lang] = get_text(trans, str(text_key), str(text_key))
        try:
            val_int = int(val)
        except (TypeError, ValueError):
            val_int = val
        choices.append({"name": name_dict, "value": val_int})
    return choices


def build_value_constraints(definition, translations_by_lang, primary_lang):
    """Build the shared valueConstraints file for Likert scales.

    Returns the JSON-LD dict, or None if the scale has no likert_options.
    """
    eff = definition.get("likert_options", {})
    if not eff:
        return None
    # Use a dummy item to reuse get_likert_choices
    dummy_item = {}
    choices = get_likert_choices(dummy_item, definition, translations_by_lang,
                                 primary_lang)
    if not choices:
        return None

    min_val = eff.get("min", 1)
    max_val = eff.get("max", min_val + eff.get("points", 5) - 1)

    return {
        "@context": REPROSCHEMA_CONTEXT,
        "id": "valueConstraints",
        "category": "ResponseOption",
        "minValue": min_val,
        "maxValue": max_val,
        "choices": choices,
        "multipleChoice": False,
        "valueType": ["xsd:integer"],
    }


def build_score_item_file(score_id, code):
    """Build the JSON-LD dict for a computed score item."""
    full_id = f"{code}_{score_id}"
    return {
        "@context": REPROSCHEMA_CONTEXT,
        "id": full_id,
        "category": "Item",
        "schemaVersion": SCHEMA_VERSION,
        "version": ACTIVITY_VERSION,
        "prefLabel": {"en": full_id},
        "ui": {"readonlyValue": True, "inputType": "xsd:int"},
        "responseOptions": {"valueType": ["xsd:integer"]},
    }


def build_activity_schema(definition, translations_by_lang, primary_lang, code,
                           ordered_item_ids, add_properties, compute_entries):
    """Build the activity schema JSON-LD dict.

    ordered_item_ids: list of 'items/{id}' paths for ui.order
    add_properties: list of property dicts for ui.addProperties
    compute_entries: list of {jsExpression, variableName} dicts
    """
    scale_info = definition.get("scale_info", {})
    name = scale_info.get("name", code)
    description = scale_info.get("description", "")
    citation = scale_info.get("citation", "")

    # Preamble from likert question_head
    eff = definition.get("likert_options", {})
    qh_key = eff.get("question_head", "")
    preamble = {}
    if qh_key:
        for lang, trans in translations_by_lang.items():
            text = get_text(trans, qh_key, "")
            if text:
                preamble[lang] = text

    schema = {
        "@context": REPROSCHEMA_CONTEXT,
        "id": f"{code}_schema",
        "category": "Activity",
        "schemaVersion": SCHEMA_VERSION,
        "version": ACTIVITY_VERSION,
        "prefLabel": {lang: code for lang in translations_by_lang or {"en": code}},
        "description": {lang: description for lang in translations_by_lang or {"en": description}},
    }

    if citation:
        schema["citation"] = {lang: citation for lang in translations_by_lang or {"en": citation}}

    if preamble:
        schema["preamble"] = preamble

    if compute_entries:
        schema["compute"] = compute_entries

    schema["ui"] = {
        "order": ordered_item_ids,
        "addProperties": add_properties,
        "shuffle": False,
    }

    return schema


# ---------------------------------------------------------------------------
# Grid item expansion
# ---------------------------------------------------------------------------

def expand_grid_item(item, definition, translations_by_lang, primary_lang):
    """Expand a grid item into a list of (item_id, item_file_dict) tuples.

    Returns list of (expanded_item_id, item_dict) and a list of
    item_ids in display order.
    """
    grid_id = item["id"]
    columns = item.get("columns", [])
    rows = item.get("rows", [])

    # Build choices from columns
    col_choices = []
    for i, col in enumerate(columns):
        if isinstance(col, dict):
            val = col.get("value", i + 1)
            text_key = col.get("text_key", str(val))
        else:
            val = i + 1
            text_key = str(col)
        name_dict = {}
        for lang, trans in translations_by_lang.items():
            name_dict[lang] = get_text(trans, str(text_key), str(text_key))
        try:
            val_int = int(val)
        except (TypeError, ValueError):
            val_int = val
        col_choices.append({"name": name_dict, "value": val_int})

    expanded = []
    for j, row_key in enumerate(rows):
        row_item_id = f"{grid_id}_{j + 1}"
        question = {}
        for lang, trans in translations_by_lang.items():
            question[lang] = get_text(trans, str(row_key), str(row_key))

        obj = _base_item(row_item_id)
        for lang in translations_by_lang:
            obj["prefLabel"][lang] = row_item_id
        obj["question"] = question
        obj["ui"] = {"inputType": "radio"}
        obj["responseOptions"] = {
            "choices": col_choices,
            "multipleChoice": False,
            "valueType": ["xsd:integer"],
        }
        expanded.append((row_item_id, obj))

    return expanded


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert(definition, translations_by_lang, primary_lang, code, output_dir):
    """Convert a parsed OSD definition to ReproSchema and write to output_dir.

    Returns a summary dict with counts of written files.
    """
    output_dir = Path(output_dir)
    items_dir = output_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    items = definition.get("items") or definition.get("questions", [])
    scoring = definition.get("scoring", {})
    has_likert = any(it.get("type") == "likert" for it in items)

    active_item_ids = {it.get("id") for it in items if isinstance(it, dict)}
    all_score_ids = set(scoring.keys())

    # --- Write individual item files ---
    written_item_files = []
    ordered_item_ids = []    # for ui.order (items/* paths)
    add_properties = []      # for ui.addProperties

    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type", "short")
        item_id = item.get("id", "")
        if not item_id:
            continue

        visible_when = item.get("visible_when")
        is_vis = visible_when_to_is_vis(visible_when) if visible_when else True

        if item_type == "section":
            # Structural only — skip from ui.order but still emit an item file
            _, obj = build_item_file(item, definition, translations_by_lang,
                                     primary_lang)
            _write_json(items_dir / item_id, obj)
            written_item_files.append(item_id)
            # Not added to ordered_item_ids or addProperties
            continue

        elif item_type == "grid":
            # Expand into per-row items
            expanded = expand_grid_item(item, definition, translations_by_lang,
                                        primary_lang)
            for row_item_id, row_obj in expanded:
                _write_json(items_dir / row_item_id, row_obj)
                written_item_files.append(row_item_id)
                ref = f"items/{row_item_id}"
                ordered_item_ids.append(ref)
                add_properties.append({
                    "isAbout": ref,
                    "variableName": row_item_id,
                    "isVis": is_vis,
                    "valueRequired": True,
                })
            continue

        else:
            _, obj = build_item_file(item, definition, translations_by_lang,
                                     primary_lang)
            _write_json(items_dir / item_id, obj)
            written_item_files.append(item_id)
            ref = f"items/{item_id}"
            ordered_item_ids.append(ref)
            add_properties.append({
                "isAbout": ref,
                "variableName": item_id,
                "isVis": is_vis,
                "valueRequired": item_type not in ("inst",),
            })

    # --- Build scoring compute entries and score item files ---
    compute_entries = []
    n_score_items = 0

    for score_id, score_def in scoring.items():
        if not isinstance(score_def, dict):
            continue
        method = score_def.get("method", "")
        expr = build_js_expression(score_def, definition, code, all_score_ids,
                                   active_item_ids=active_item_ids)
        if expr is None:
            continue

        full_var = f"{code}_{score_id}"
        compute_entries.append({
            "jsExpression": expr,
            "variableName": full_var,
        })

        # Score item file
        score_obj = build_score_item_file(score_id, code)
        _write_json(items_dir / full_var, score_obj)
        written_item_files.append(full_var)
        n_score_items += 1

        # Score items appear in addProperties but NOT in ui.order
        ref = f"items/{full_var}"
        add_properties.append({
            "isAbout": ref,
            "variableName": full_var,
            "isVis": False,
        })

    # --- Write valueConstraints if scale has likert items ---
    wrote_vc = False
    if has_likert:
        vc = build_value_constraints(definition, translations_by_lang, primary_lang)
        if vc:
            _write_json(output_dir / "valueConstraints", vc)
            wrote_vc = True

    # --- Write activity schema ---
    schema = build_activity_schema(
        definition, translations_by_lang, primary_lang, code,
        ordered_item_ids, add_properties, compute_entries,
    )
    schema_path = output_dir / f"{code}_schema"
    _write_json(schema_path, schema)

    return {
        "schema": str(schema_path),
        "items": written_item_files,
        "score_items": n_score_items,
        "compute_entries": len(compute_entries),
        "value_constraints": wrote_vc,
        "output_dir": str(output_dir),
    }


def _write_json(path, obj):
    """Write obj as JSON (no extension, indented, non-ASCII preserved)."""
    path = Path(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert OSD format to ReproSchema JSON-LD"
    )
    parser.add_argument("scale_dir", help="Path to scale directory")
    parser.add_argument(
        "--output", "-o",
        help="Output directory (default: {CODE}_reproschema/ in cwd)",
    )
    parser.add_argument(
        "--lang", default="en",
        help="Primary language code (default: en)",
    )
    parser.add_argument(
        "--all-langs", action="store_true",
        help="Include all available languages in multilingual fields",
    )
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
        raw = json.load(f)

    # Unwrap OSD envelope if present
    if "definition" in raw and "osd_version" in raw:
        definition = raw["definition"]
    else:
        definition = raw

    # Try variant flattening if available
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from osd_variants import flatten_variant
        definition = flatten_variant(definition, args.lang, None)
    except ImportError:
        pass

    # Load translations
    if args.all_langs:
        translations_by_lang = load_all_translations(scale_dir, code, args.lang)
        if not translations_by_lang:
            print("Warning: No translations found for any language",
                  file=sys.stderr)
            translations_by_lang = {args.lang: {}}
    else:
        primary = load_translation(scale_dir, code, args.lang)
        if not primary:
            print(f"Warning: No translation found for language '{args.lang}'",
                  file=sys.stderr)
            primary = {}
        translations_by_lang = {args.lang: primary}

    if args.lang not in translations_by_lang:
        translations_by_lang[args.lang] = {}

    # Determine output — if --output ends in .zip, write dir then zip it
    zip_output = args.output and args.output.endswith(".zip")

    if zip_output:
        import tempfile, shutil
        tmp_dir = Path(tempfile.mkdtemp(prefix="reproschema_"))
        output_dir = tmp_dir
    elif args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path(f"{code}_reproschema")

    output_dir.mkdir(parents=True, exist_ok=True)

    summary = convert(definition, translations_by_lang, args.lang, code,
                      output_dir)

    if zip_output:
        import zipfile
        zip_path = Path(args.output)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(output_dir.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(output_dir))
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"Written to: {zip_path}")
    else:
        print(f"Written to: {summary['output_dir']}/")

    # Print summary
    n_regular = len(summary["items"]) - summary["score_items"]
    print(f"  Activity schema : {code}_schema")
    print(f"  Item files      : {n_regular} content items"
          + (f", {summary['score_items']} score items" if summary["score_items"] else ""))
    if summary["value_constraints"]:
        print(f"  valueConstraints: written (shared Likert response options)")
    if summary["compute_entries"]:
        print(f"  Compute entries : {summary['compute_entries']} score expressions")
    if args.all_langs:
        langs = sorted(translations_by_lang.keys())
        print(f"  Languages       : {', '.join(langs)}")


if __name__ == "__main__":
    main()
