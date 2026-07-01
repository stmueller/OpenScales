#!/usr/bin/env python3
"""Convert Open Scale Definition (OSD) format to SurveyJS JSON format (Pavlovia-compatible).

Usage:
    python3 convert_to_surveyjs.py <scale_directory> [--lang LANG] [--output FILE]

Reads {code}.osd and emits a SurveyJS survey JSON.

Item type mapping:
  likert     -> matrix (grouped by shared likert_options block)
  multi      -> radiogroup (per item, integer values)
  multicheck -> checkbox (per item, integer values)
  short      -> text
  long       -> comment
  number     -> text (inputType: number)
  vas        -> rating (approximation)
  inst       -> html
  section    -> html (header)
  Scoring    -> html block at end (researcher note)

visibleIf: {item} operator value  ->  SurveyJS "{name} op value"
  operators: equals -> =, not_equals -> !=
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from osd_loader import load_scale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _t(translations, lang, key, fallback=""):
    """Resolve a text key from translations, falling back to 'en'."""
    val = translations.get(lang, {}).get(key)
    if val is not None:
        return val
    val = translations.get("en", {}).get(key)
    if val is not None:
        return val
    return fallback


def _visible_if(cond):
    """Convert OSD visible_when dict to SurveyJS visibleIf expression string."""
    if not cond:
        return None
    item = cond.get("item", "")
    op = cond.get("operator", "equals")
    value = cond.get("value", "")

    if op == "equals":
        surv_op = "="
    elif op == "not_equals":
        surv_op = "!="
    elif op == "greater_than":
        surv_op = ">"
    elif op == "less_than":
        surv_op = "<"
    else:
        surv_op = "="

    if isinstance(value, str):
        return f"{{{item}}} {surv_op} '{value}'"
    else:
        return f"{{{item}}} {surv_op} {value}"


def _build_likert_columns(lo, translations, lang):
    """Build SurveyJS column list from OSD likert_options."""
    points = lo.get("points", 5)
    labels = lo.get("labels", [])
    min_val = lo.get("min", 1)

    columns = []
    for i in range(points):
        val = min_val + i
        label_key = labels[i] if i < len(labels) else None
        if label_key:
            text = _t(translations, lang, label_key)
            if text:
                columns.append({"value": val, "text": text})
                continue
        columns.append(val)
    return columns


def resolve_options(item, defn):
    """Resolve the options list for a multi/multicheck item.

    Resolution order:
    1. item['options']          — inline options (highest priority)
    2. item['option_set']       — named set in defn['option_sets']
    3. defn['option_sets']['default'] — default set
    4. []                       — fallback
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


def _build_multi_choices(options, translations, lang):
    """Build SurveyJS choices list from OSD multi/multicheck options."""
    choices = []
    for opt in options:
        text_key = opt.get("text_key", "")
        text = _t(translations, lang, text_key, text_key)
        value = opt.get("value", text_key)
        choices.append({"value": value, "text": text})
    return choices


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert(scale_dir, lang="en"):
    """Convert an OSD scale directory to a SurveyJS survey dict."""
    defn, translations, code = load_scale(scale_dir, lang)

    scale_info = defn.get("scale_info", {})
    title = scale_info.get("name", code)
    _rs = defn.get("response_scales", {})
    lo = _rs.get("default") or defn.get("likert_options")

    items = defn.get("items", [])

    # Build SurveyJS elements
    elements = []

    # Track pending likert rows to group into matrix blocks
    pending_matrix = []
    pending_matrix_visible_if = None
    # Map item_id -> matrix_name for scoring expression generation
    item_to_matrix = {}

    def flush_matrix():
        """Emit accumulated likert rows as a single matrix element."""
        if not pending_matrix:
            return
        q_head_key = lo.get("question_head") if lo else None
        q_head = _t(translations, lang, q_head_key) if q_head_key else ""

        matrix_name = f"matrix_{pending_matrix[0]['name']}"
        for r in pending_matrix:
            item_to_matrix[r["name"]] = matrix_name

        matrix = {
            "type": "matrix",
            "name": matrix_name,
            "title": q_head,
            "columns": _build_likert_columns(lo, translations, lang),
            "rows": [{"value": r["name"], "text": r["title"]} for r in pending_matrix],
            "isAllRowRequired": False,
        }
        if pending_matrix_visible_if:
            matrix["visibleIf"] = pending_matrix_visible_if
        elements.append(matrix)
        pending_matrix.clear()

    for item in items:
        itype = item.get("type", "likert")
        iid = item.get("id", "")
        text_key = item.get("text_key", iid)
        text = _t(translations, lang, text_key)
        cond = item.get("visible_when")
        vis = _visible_if(cond)

        if itype == "likert":
            # If visible_when changes, flush and start new matrix
            if cond != pending_matrix_visible_if and pending_matrix:
                flush_matrix()
                pending_matrix_visible_if = cond
            elif not pending_matrix:
                pending_matrix_visible_if = cond

            pending_matrix.append({"name": iid, "title": text})

        elif itype in ("inst", "section"):
            flush_matrix()
            el = {
                "type": "html",
                "name": iid,
                "html": f"<p>{text}</p>",
            }
            if vis:
                el["visibleIf"] = vis
            elements.append(el)

        elif itype == "multi":
            flush_matrix()
            options = resolve_options(item, defn)
            el = {
                "type": "radiogroup",
                "name": iid,
                "title": text,
                "choices": _build_multi_choices(options, translations, lang),
                "colCount": 0,
            }
            if vis:
                el["visibleIf"] = vis
            elements.append(el)

        elif itype == "multicheck":
            flush_matrix()
            options = resolve_options(item, defn)
            el = {
                "type": "checkbox",
                "name": iid,
                "title": text,
                "choices": _build_multi_choices(options, translations, lang),
            }
            if vis:
                el["visibleIf"] = vis
            elements.append(el)

        elif itype == "short":
            flush_matrix()
            el = {"type": "text", "name": iid, "title": text}
            if vis:
                el["visibleIf"] = vis
            elements.append(el)

        elif itype == "long":
            flush_matrix()
            el = {"type": "comment", "name": iid, "title": text}
            if vis:
                el["visibleIf"] = vis
            elements.append(el)

        elif itype == "number":
            flush_matrix()
            el = {"type": "text", "name": iid, "title": text, "inputType": "number"}
            if vis:
                el["visibleIf"] = vis
            elements.append(el)

        elif itype == "vas":
            flush_matrix()
            lo_vas = lo or {}
            el = {
                "type": "rating",
                "name": iid,
                "title": text,
                "rateMin": lo_vas.get("min", 0),
                "rateMax": lo_vas.get("min", 0) + lo_vas.get("points", 100) - 1,
            }
            if vis:
                el["visibleIf"] = vis
            elements.append(el)

        elif itype == "grid":
            flush_matrix()
            # Grid rows become individual radiogroup questions
            rows = item.get("rows", [])
            cols = item.get("cols") or (lo.get("labels") if lo else None) or []
            for row in rows:
                row_key = row.get("text_key", row.get("id", ""))
                row_text = _t(translations, lang, row_key, row_key)
                choices = []
                for j, col in enumerate(cols):
                    col_key = col if isinstance(col, str) else col.get("text_key", "")
                    col_text = _t(translations, lang, col_key, col_key)
                    choices.append({"value": j, "text": col_text})
                el = {
                    "type": "radiogroup",
                    "name": f"{iid}_{row.get('id', j)}",
                    "title": row_text,
                    "choices": choices,
                }
                if vis:
                    el["visibleIf"] = vis
                elements.append(el)

    flush_matrix()

    # Build calculatedValues for numeric scoring dimensions
    calc_values = _build_calculated_values(defn, items, lo, item_to_matrix)

    # Debrief + scoring note go into completedHtml (shown after submission, not on survey page)
    completed_parts = []
    debrief = _t(translations, lang, "debrief")
    if debrief:
        completed_parts.append(f"<p>{debrief}</p>")
    scoring_html = _build_scoring_html(defn, code)
    if scoring_html:
        completed_parts.append(scoring_html)

    survey = {
        "title": title,
        "description": scale_info.get("description", ""),
        "pages": [{"name": "page1", "elements": elements}],
    }
    if completed_parts:
        survey["completedHtml"] = "".join(completed_parts)
    if calc_values:
        survey["calculatedValues"] = calc_values

    return survey


def _build_scoring_html(defn, code):
    """Build a researcher-facing scoring note HTML string."""
    scoring = defn.get("scoring", {})
    if not scoring:
        return ""

    lines = ["Note for researcher:<br><br>"]
    for dim_id, dim_score in scoring.items():
        desc = dim_score.get("description", "")
        method = dim_score.get("method", "")
        if desc:
            lines.append(f"<b>{dim_id}:</b> {desc}<br>")
        elif method:
            lines.append(f"<b>{dim_id}:</b> method={method}<br>")

        # Thresholds
        norms = dim_score.get("norms", {})
        thresholds = norms.get("thresholds", [])
        for t in thresholds:
            lo = t.get("min", "")
            hi = t.get("max", "")
            label = t.get("label", "")
            lines.append(f"&nbsp;&nbsp;{lo}–{hi}: {label}<br>")

    return "".join(lines)


def _build_calculated_values(defn, items, lo, item_to_matrix=None):
    """Build SurveyJS calculatedValues for scoring dimensions.

    Matrix row answers are accessed as {matrixName.rowId} in SurveyJS expressions.
    item_to_matrix maps item_id -> matrix element name for likert items.
    """
    scoring = defn.get("scoring", {})
    if not scoring:
        return []

    if item_to_matrix is None:
        item_to_matrix = {}

    calc = []
    for dim_id, dim_score in scoring.items():
        raw_items = dim_score.get("items", [])
        if isinstance(raw_items, dict):
            item_weights = raw_items
        else:
            item_weights = {iid: 1 for iid in raw_items}

        if not item_weights:
            continue

        parts = []
        for iid, weight in item_weights.items():
            itype = next((it.get("type", "likert") for it in items if it.get("id") == iid), "likert")
            if itype == "likert" and lo and iid in item_to_matrix:
                # SurveyJS matrix answers: {matrixName.rowValue}
                matrix_name = item_to_matrix[iid]
                ref = f"{{{matrix_name}.{iid}}}"
                if weight == 1:
                    parts.append(ref)
                elif weight == -1:
                    max_val = lo.get("min", 1) + lo.get("points", 5) - 1
                    min_val = lo.get("min", 1)
                    parts.append(f"({min_val + max_val} - {ref})")
                else:
                    parts.append(f"({weight} * {ref})")
            else:
                ref = f"{{{iid}}}"
                if weight == 1:
                    parts.append(ref)
                elif weight == -1:
                    parts.append(f"(-1 * {ref})")
                else:
                    parts.append(f"({weight} * {ref})")

        expr = " + ".join(parts)
        calc.append({
            "name": dim_id,
            "expression": expr,
            "includeIntoResult": True,
        })

    return calc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert OSD scale to SurveyJS JSON")
    parser.add_argument("scale_dir", help="Path to scale directory containing .osd file")
    parser.add_argument("--lang", default="en", help="Language code (default: en)")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    args = parser.parse_args()

    survey = convert(args.scale_dir, lang=args.lang)
    out = json.dumps(survey, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Written: {args.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()
