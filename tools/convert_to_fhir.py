#!/usr/bin/env python3
"""
convert_to_fhir.py — Convert an OpenScales .osd scale to an HL7 FHIR R4 `Questionnaire`.

Output is a valid, renderable FHIR R4 Questionnaire (JSON) that loads into any FHIR
server (HAPI, Medplum, Aidbox, cloud FHIR) and SDC renderer (NLM LForms, CSIRO Smart
Forms). Item scores are carried on each answer option via the `ordinalValue` (legacy) and
`itemWeight` (current SDC) extensions, so score-aware renderers can compute totals.

Mapping (.osd item type -> FHIR Questionnaire.item.type):
  likert / multi   -> choice        (answerOption: valueCoding {code,display} + ordinal/itemWeight)
  multicheck       -> choice, repeats=true
  vas              -> integer        (slider itemControl + minValue/maxValue extensions)
  short            -> string
  long / text      -> text
  number           -> decimal
  inst / section   -> display
  grid             -> group          (one choice child per row)

Terminology codes: if a scale carries an (optional, Roadmap R3) `codes` object on
scale_info / items / answer options, they are emitted as Coding(s). Absent otherwise —
the output is still a valid, local-coded Questionnaire.

Scope (v1): full structure + answers + weights + skip logic (`enableWhen`) + slider VAS +
codes. Full total-score `calculatedExpression` (reverse coding / value_map parity) is a
documented follow-up; scoring is carried as per-option weights + a description note.

Usage:
  python3 convert_to_fhir.py scales/openscales/DEMO5 --lang en -o DEMO5.Questionnaire.json
  python3 convert_to_fhir.py <scale_dir>            # prints JSON to stdout
"""

import sys
import os
import json
import re
import html
import argparse
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from osd_loader import load_scale
import osd_params

FHIR_BASE = "https://openscales.net/fhir"
EXT_ORDINAL = "http://hl7.org/fhir/StructureDefinition/ordinalValue"
EXT_ITEMWEIGHT = "http://hl7.org/fhir/StructureDefinition/itemWeight"
EXT_ITEMCONTROL = "http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl"
EXT_MINVALUE = "http://hl7.org/fhir/StructureDefinition/minValue"
EXT_MAXVALUE = "http://hl7.org/fhir/StructureDefinition/maxValue"
EXT_SLIDERSTEP = "http://hl7.org/fhir/StructureDefinition/questionnaire-sliderStepValue"
ITEMCONTROL_CS = "http://hl7.org/fhir/questionnaire-item-control"


def _t(translations, lang, key, fallback=""):
    if key is None:
        return fallback
    val = translations.get(lang, {}).get(key)
    if val is not None:
        return val
    val = translations.get("en", {}).get(key)
    if val is not None:
        return val
    return fallback


def _resolve_scale(item, defn):
    """Resolve the response scale (points/min/labels) for a likert item."""
    rs = defn.get("response_scales", {}) or {}
    key = item.get("response_scale")
    if key and key in rs:
        return rs[key]
    if "default" in rs:
        return rs["default"]
    return defn.get("likert_options", {}) or {}


def _resolve_options(item, defn):
    if "options" in item:
        return item["options"]
    option_sets = defn.get("option_sets", {}) or {}
    key = item.get("option_set")
    if key and key in option_sets:
        return option_sets[key]
    if "default" in option_sets:
        return option_sets["default"]
    return []


DEFAULT_SYSTEM_URI = {
    "loinc": "http://loinc.org",
    "loinc_answer": "http://loinc.org",
    "snomed": "http://snomed.info/sct",
    "hpo": "http://human-phenotype-ontology.org",
    "orphanet": "http://www.orpha.net",
    "cadsr": "https://cadsr.cancer.gov",
    "icd10": "http://hl7.org/fhir/sid/icd-10",
    "icd10cm": "http://hl7.org/fhir/sid/icd-10-cm",
}


def _codes_to_coding(codes, systems=None):
    """Convert a codes dict {loinc:.., hpo:[..,..]} -> list of FHIR Coding.

    A value may be a scalar, a {code, display} dict, or a LIST of either (a scale can
    map to several concepts in one system, e.g. multiple HPO codes). `systems` is the
    overlay's optional `codes.systems` map ({short: {uri, version}}) — used to override
    the canonical URI and stamp a code-system version on each Coding.
    """
    systems = systems or {}
    out = []
    for k, v in (codes or {}).items():
        if not v:
            continue
        decl = systems.get(k, {}) if isinstance(systems.get(k), dict) else {}
        uri = decl.get("uri") or DEFAULT_SYSTEM_URI.get(k, k)
        ver = decl.get("version")
        for item in (v if isinstance(v, list) else [v]):
            if not item:
                continue
            if isinstance(item, dict):  # {code, display}
                c = {"system": uri, "code": str(item.get("code"))}
                if item.get("display"):
                    c["display"] = item["display"]
            else:
                c = {"system": uri, "code": str(item)}
            if ver:
                c["version"] = ver
            out.append(c)
    return out


def _system_map(defn):
    return (defn.get("codes") or {}).get("systems") or {}


def _answer_overlay(item, defn):
    """Return {str(value): codes_dict} of answer codes for the response scale this item uses.

    Answer codes live ONCE on the shared response scale in the overlay
    (`codes.response_scales.<key>.options`), so they are never repeated per item in the
    source; the converter fans them onto each item that uses that scale at convert time.
    An optional per-item override (`codes.items.<id>.options`) wins when present.
    """
    ov = (defn.get("codes") or {}).get("response_scales") or {}
    key = item.get("response_scale") or item.get("option_set") or "default"
    entry = ov.get(key) or ov.get("default") or {}
    merged = {str(k): dict(v) for k, v in (entry.get("options") or {}).items()}
    item_ov = ((defn.get("codes") or {}).get("items") or {}).get(item.get("id"), {})
    for k, v in (item_ov.get("options") or {}).items():
        merged[str(k)] = dict(v)
    return merged


def _weight_ext(val):
    return [{"url": EXT_ORDINAL, "valueDecimal": val},
            {"url": EXT_ITEMWEIGHT, "valueDecimal": val}]


def _likert_answer_options(item, defn, translations, lang, code):
    scale = _resolve_scale(item, defn)
    points = scale.get("points", 5)
    min_val = scale.get("min", 1)
    labels = scale.get("labels", []) or []
    local_system = f"{FHIR_BASE}/CodeSystem/{code}"
    answer_ov = _answer_overlay(item, defn)
    systems = _system_map(defn)
    opts = []
    for i in range(points):
        val = min_val + i
        label_key = labels[i] if i < len(labels) else None
        display = (_t(translations, lang, label_key, str(val)) if label_key else str(val)).strip() or str(val)
        # An overlay answer code (e.g. SNOMED) becomes the semantic Coding; scoring is
        # preserved via the itemWeight extension. Otherwise fall back to the local code.
        term = _codes_to_coding(answer_ov.get(str(val)), systems)
        coding = {**term[0], "display": display} if term else \
                 {"system": local_system, "code": str(val), "display": display}
        opts.append({"valueCoding": coding, "extension": _weight_ext(val)})
    return opts


def _multi_answer_options(item, defn, translations, lang, code):
    local_system = f"{FHIR_BASE}/CodeSystem/{code}"
    answer_ov = _answer_overlay(item, defn)
    systems = _system_map(defn)
    opts = []
    for opt in _resolve_options(item, defn):
        if isinstance(opt, str):
            tk, value = opt, opt
        else:
            tk = opt.get("text_key", "")
            value = opt.get("value", tk)
        display = (_t(translations, lang, tk, str(value)) or "").strip() or str(value)
        # A terminology code — from the overlay (keyed by value or text_key) or inline on the
        # option — becomes the answer's Coding (semantic, ingestible); otherwise the local code.
        # Scoring is preserved regardless via the itemWeight/ordinalValue extension.
        oc = answer_ov.get(str(value)) or answer_ov.get(str(tk)) \
            or (opt.get("codes") if isinstance(opt, dict) else None)
        term = _codes_to_coding(oc, systems)
        coding = {**term[0], "display": display} if term else \
                 {"system": local_system, "code": str(value), "display": display}
        entry = {"valueCoding": coding}
        # numeric option values double as scoring weights
        if isinstance(value, (int, float)):
            entry["extension"] = _weight_ext(value)
        opts.append(entry)
    return opts


def _enable_when(item, index, code):
    """Map .osd visible_when -> FHIR enableWhen (best-effort)."""
    cond = item.get("visible_when")
    if not cond or not cond.get("item"):
        return None
    opmap = {"equals": "=", "not_equals": "!=", "greater_than": ">",
             "less_than": "<", "greater_or_equal": ">=", "less_or_equal": "<=",
             "exists": "exists"}
    op = opmap.get(cond.get("operator", "equals"), "=")
    q = cond["item"]
    value = cond.get("value")
    ew = {"question": q, "operator": op}
    if op == "exists":
        ew["answerBoolean"] = bool(value)
        return [ew]
    # a condition with no value can't produce a valid enableWhen answer[x] — drop it
    # (better to omit skip-logic than emit an empty, invalid element)
    if value is None or str(value).strip() == "":
        return None
    ref = index.get(q, {})
    if ref.get("type") in ("likert", "multi", "multicheck"):
        ew["answerCoding"] = {"system": f"{FHIR_BASE}/CodeSystem/{code}", "code": str(value)}
    elif isinstance(value, bool):
        ew["answerBoolean"] = value
    elif isinstance(value, (int, float)):
        ew["answerInteger"] = int(value)
    else:
        ew["answerString"] = str(value)
    return [ew]


def _default_required(defn):
    return defn.get("default_required", True)


def convert(scale_dir, lang="en", status="active", param_pairs=None):
    defn, translations, code = load_scale(scale_dir, lang)
    params = osd_params.prepare(defn, translations, param_pairs)  # substitute [name]/{name}
    si = defn.get("scale_info", {})
    _title = si.get("name", code) if osd_params.show_header(params) else ""
    items = defn.get("items", [])
    index = {it.get("id"): it for it in items}
    def_req = _default_required(defn)
    systems = _system_map(defn)
    overlay_items = (defn.get("codes") or {}).get("items", {})

    fhir_items = []
    for it in items:
        itype = it.get("type", "likert")
        iid = it.get("id", "")
        text = (_t(translations, lang, it.get("text_key", iid), "") or "").strip()

        # per-item shared stem (question_head): prepend to text so it survives flat rendering
        qh = it.get("question_head")
        if qh:
            head = (_t(translations, lang, qh, "") or "").strip()
            if head and head not in text:
                text = (head + "\n" + text).strip() if text else head

        # FHIR: never emit an empty `text` element (violates ele-1); omit it instead
        node = {"linkId": iid}
        if text:
            node["text"] = text

        if itype in ("inst", "section"):
            if not text:
                continue  # empty divider carries no content — nothing to render
            node["type"] = "display"
            fhir_items.append(node)
            continue

        required = it.get("required", def_req)

        if itype in ("likert", "multi"):
            node["type"] = "choice"
            node["answerOption"] = _likert_answer_options(it, defn, translations, lang, code) \
                if itype == "likert" else _multi_answer_options(it, defn, translations, lang, code)
        elif itype == "multicheck":
            node["type"] = "choice"
            node["repeats"] = True
            node["answerOption"] = _multi_answer_options(it, defn, translations, lang, code)
        elif itype == "vas":
            node["type"] = "integer"
            mn = it.get("min", 0)
            mx = it.get("max", 100)
            step = it.get("step", 1)
            lo_lab = _t(translations, lang, it.get("min_label"), "") if it.get("min_label") else ""
            hi_lab = _t(translations, lang, it.get("max_label"), "") if it.get("max_label") else ""
            if lo_lab or hi_lab:
                node["text"] = (node.get("text", "") + f"  ({mn} = {lo_lab}; {mx} = {hi_lab})").strip()
            node["extension"] = [
                {"url": EXT_ITEMCONTROL, "valueCodeableConcept":
                    {"coding": [{"system": ITEMCONTROL_CS, "code": "slider"}]}},
                {"url": EXT_MINVALUE, "valueInteger": mn},
                {"url": EXT_MAXVALUE, "valueInteger": mx},
                {"url": EXT_SLIDERSTEP, "valueInteger": step},
            ]
        elif itype == "short":
            node["type"] = "string"
        elif itype in ("long", "text"):
            node["type"] = "text"
        elif itype == "number":
            node["type"] = "decimal"
        elif itype == "grid":
            node["type"] = "group"
            cols = it.get("columns", [])
            rows = it.get("rows", [])
            children = []
            for r in rows:
                rid = r if isinstance(r, str) else r.get("id", "")
                rtext = _t(translations, lang, rid, rid)
                child = {"linkId": f"{iid}_{rid}", "text": rtext, "type": "choice",
                         "required": required, "answerOption": _likert_answer_options(it, defn, translations, lang, code)}
                children.append(child)
            node["item"] = children
        else:
            node["type"] = "string"

        if itype not in ("grid",):
            node["required"] = required

        ew = _enable_when(it, index, code)
        if ew:
            node["enableWhen"] = ew

        # terminology codes on the item: overlay (codes.items.<id>) + any inline codes.
        # `options` under an overlay item entry is answer-level (handled on answerOption).
        item_codes = {k: v for k, v in overlay_items.get(iid, {}).items() if k != "options"}
        item_codes.update(it.get("codes") or {})
        if item_codes:
            node["code"] = _codes_to_coding(item_codes, systems)

        fhir_items.append(node)

    # ---- enforce unique linkIds (FHIR que-2) — defensive against dup ids in source ----
    _seen_ids = {}

    def _dedupe_ids(nodes):
        for n in nodes:
            lid = n.get("linkId", "")
            if lid in _seen_ids:
                _seen_ids[lid] += 1
                n["linkId"] = f"{lid}__{_seen_ids[lid]}"
            else:
                _seen_ids[lid] = 1
            if n.get("item"):
                _dedupe_ids(n["item"])

    _dedupe_ids(fhir_items)

    # ---- assemble the Questionnaire ----
    name = re.sub(r"[^A-Za-z0-9]", "", code) or "Scale"
    desc = si.get("description", "")
    # scoring summary appended to description (v1 carries scoring as per-option weights)
    scoring = defn.get("scoring", {})
    if scoring:
        dims = "; ".join(f"{k} ({v.get('method','?')})" for k, v in scoring.items())
        desc = (desc + f"\n\nScoring dimensions (weights carried on answer options via "
                       f"ordinalValue/itemWeight): {dims}.").strip()
    cite = si.get("citation", "")
    lic = si.get("license", "")
    copyright_ = " ".join(x for x in [cite, ("License: " + lic) if lic else ""] if x).strip()

    q = {
        "resourceType": "Questionnaire",
        "url": f"{FHIR_BASE}/Questionnaire/{name}",
        "version": str(si.get("version", "1.0")),
        "name": name,
        "status": status,
        "subjectType": ["Patient"],
        "experimental": True,
        "publisher": (defn.get("implementation", {}) or {}).get("organization", "OpenScales Project"),
        "description": desc,
        "text": {
            "status": "generated",
            "div": ('<div xmlns="http://www.w3.org/1999/xhtml"><p><b>'
                    + html.escape(_title or code)
                    + '</b> - ' + str(len([i for i in fhir_items if i.get("type") not in ("display", "group")]))
                    + ' scored item(s). Generated from an OpenScales .osd by convert_to_fhir.py.</p></div>'),
        },
        "item": fhir_items,
    }
    if _title:                       # FHIR: omit empty title (show_header=false) — ele-1
        q["title"] = _title
    if copyright_:
        q["copyright"] = copyright_
    # scale/panel code: overlay (codes.scale) + any inline scale_info.codes
    scale_codes = dict((defn.get("codes") or {}).get("scale", {}))
    scale_codes.update(si.get("codes") or {})
    if scale_codes:
        q["code"] = _codes_to_coding(scale_codes, systems)
    return q


def main():
    ap = argparse.ArgumentParser(description="Convert an OSD scale to a FHIR R4 Questionnaire.")
    ap.add_argument("scale_dir", help="Path to the scale directory (containing a .osd file)")
    ap.add_argument("--lang", default="en", help="Language code (default: en)")
    ap.add_argument("--status", default="active", choices=["draft", "active", "retired", "unknown"])
    ap.add_argument("-o", "--out", "--output", dest="out", help="Output file (default: stdout)")
    osd_params.add_param_arg(ap)
    args = ap.parse_args()

    q = convert(args.scale_dir, lang=args.lang, status=args.status, param_pairs=args.param)
    text = json.dumps(q, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
