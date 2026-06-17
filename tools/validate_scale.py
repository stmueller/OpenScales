#!/usr/bin/env python3
"""Validate a scale against the Open Scale Definition (OSD) specification.

Handles the current single-file `.osd` format (an `{osd_version, definition,
translations}` wrapper with embedded translations) as well as the legacy flat
`.json` definition + separate `{code}.{lang}.json` translation files.

Validates current spec features: response_scales, likert_options
(suppress_likert_numbers, question_head, likert_reverse, min/max/labels),
object-form scoring coding `{id: 1|-1|0}`, `scores` composites, `value_map`,
`weights`, `transform`, `answer_categories`/`answer_category`, item-level
`question_head`/`response_scale`, `section` items, and the draft `variants`
block (see documentation/proposals/variant_strategy_proposal.md).

Usage:
    python3 validate_scale.py <path>
    python3 validate_scale.py scales/openscales/GSE
    python3 validate_scale.py scales/openscales/GSE/GSE.osd
    python3 validate_scale.py scales/openscales        # all scales under a dir

Exit codes:
    0 - All validations passed (warnings allowed)
    1 - Validation errors found
    2 - Usage error
"""

import json
import sys
import re
from pathlib import Path

VALID_QUESTION_TYPES = {
    "inst", "section", "likert", "vas", "grid", "multi", "multicheck",
    "short", "long", "image", "imageresponse",
    "rank", "audio", "video", "audioresponse", "videoresponse",
}

# Item-scoring methods (operate on coded item responses) and composite/
# aggregation methods (operate on already-computed scores). Unknown methods
# warn rather than error so the validator tolerates spec growth.
SCORING_METHODS = {
    "mean_coded", "sum_coded", "weighted_sum", "weighted_mean", "sum_correct", "sd",
    # composite / aggregation over `scores`
    "sum", "mean", "min", "max", "range", "n", "sd_scores",
    # non-numeric
    "parameter", "shuffle", "constant",
}

# Item types for which text_key is optional.
TEXTLESS_TYPES = {"section"}

PARAMETER_TYPES = {"string", "boolean", "integer", "number", "choice"}

CONDITION_OPERATORS = {
    "equals", "not_equals", "greater_than", "less_than", "greater_equal", "less_equal",
    "in", "not_in", "is_answered", "is_not_answered",
}

CODING_VALUES = {1, -1, 0}


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
            lines.append("    No issues found.")
        return "\n".join(lines)


def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def find_definition_file(scale_dir):
    """Find the main scale file in a directory. Prefers `{code}.osd`, then any
    `.osd`, then `{code}.json`, then any non-translation `.json`."""
    p = Path(scale_dir)
    code = p.name
    for cand in (p / f"{code}.osd", p / f"{code}.json"):
        if cand.exists():
            return cand, code
    osds = sorted(p.glob("*.osd"))
    if osds:
        return osds[0], osds[0].stem
    for f in sorted(p.glob("*.json")):
        # skip files that look like separate translation files: {code}.{lang}.json
        if not re.match(r".+\.\w{2}(-\w+)?\.json$", f.name):
            return f, f.stem
    return None, code


def unwrap(data):
    """Return (definition, embedded_translations, osd_version) for either the
    wrapped `.osd` shape or a legacy flat definition."""
    if isinstance(data, dict) and "definition" in data and isinstance(data["definition"], dict):
        return data["definition"], data.get("translations"), data.get("osd_version")
    # legacy flat: the object itself is the definition; translations may be embedded
    embedded = data.get("translations") if isinstance(data, dict) else None
    definition = {k: v for k, v in data.items() if k != "translations"} if isinstance(data, dict) else {}
    return definition, embedded, data.get("osd_version") if isinstance(data, dict) else None


def find_translation_files(scale_dir, code):
    """Legacy separate translation files: {code}.{lang}.json / {code}.pbl-{lang}.json."""
    p = Path(scale_dir)
    translations = {}
    for f in p.glob(f"{code}.*.json"):
        name = f.name
        if name == f"{code}.json":
            continue
        middle = name[len(code) + 1:-5]
        if middle.startswith("pbl-"):
            translations[middle[4:]] = ("legacy", f)
        else:
            translations[middle] = ("new", f)
    return translations


def get_items(definition):
    return definition.get("items") or definition.get("questions") or []


# --------------------------------------------------------------------------- #
# Component validators
# --------------------------------------------------------------------------- #

def validate_scale_info(definition, result):
    if "scale_info" not in definition:
        result.error("Missing required 'scale_info' object")
        return None
    info = definition["scale_info"]
    if not isinstance(info, dict):
        result.error("'scale_info' must be an object")
        return None
    if not info.get("name"):
        result.error("scale_info.name is required")
    if not info.get("code"):
        result.error("scale_info.code is required")
    for field in ("abbreviation", "description", "citation", "license",
                  "license_url", "version", "url", "domain"):
        if field in info and not isinstance(info[field], str):
            result.warn(f"scale_info.{field} should be a string")
    return info


def validate_dimensions(definition, result):
    dims = definition.get("dimensions")
    if dims is None:
        return set()
    if not isinstance(dims, list):
        result.error("'dimensions' must be an array")
        return set()
    dim_ids = set()
    for i, dim in enumerate(dims):
        if not isinstance(dim, dict):
            result.error(f"Dimension {i} must be an object")
            continue
        if "id" not in dim:
            result.error(f"Dimension {i} missing required 'id' field")
            continue
        if dim["id"] in dim_ids:
            result.error(f"Duplicate dimension ID: '{dim['id']}'")
        if "name" not in dim:
            result.warn(f"Dimension '{dim['id']}' missing 'name' field")
        dim_ids.add(dim["id"])
    return dim_ids


def validate_response_scales(definition, result):
    rs = definition.get("response_scales")
    rs_ids = set()
    if rs is None:
        return rs_ids
    if not isinstance(rs, dict):
        result.error("'response_scales' must be an object")
        return rs_ids
    for sid, sdef in rs.items():
        rs_ids.add(sid)
        if not isinstance(sdef, dict):
            result.error(f"response_scales['{sid}'] must be an object")
            continue
        if "labels" not in sdef and "points" not in sdef:
            result.warn(f"response_scales['{sid}'] has neither 'points' nor 'labels'")
        if "labels" in sdef and not isinstance(sdef["labels"], list):
            result.error(f"response_scales['{sid}'].labels must be an array")
    return rs_ids


def validate_questions(definition, dim_ids, rs_ids, result):
    items = get_items(definition)
    if not items:
        result.error("Missing required 'items' (or 'questions') array")
        return set(), {}
    if not isinstance(items, list):
        result.error("'items' must be an array")
        return set(), {}

    has_default_points = "points" in (definition.get("likert_options") or {})
    qids = set()
    variant_groups = {}  # group -> [item ids]

    for i, q in enumerate(items):
        if not isinstance(q, dict):
            result.error(f"Item {i} must be an object")
            continue
        if "id" not in q:
            result.error(f"Item {i} missing required 'id' field")
            continue
        qid = q["id"]
        if qid in qids:
            result.error(f"Duplicate item ID: '{qid}'")
        qids.add(qid)

        qtype = q.get("type")
        if qtype is None:
            result.error(f"Item '{qid}' missing required 'type' field")
        elif qtype not in VALID_QUESTION_TYPES:
            result.warn(f"Item '{qid}' has unknown type '{qtype}'")

        if "text_key" not in q and qtype not in TEXTLESS_TYPES:
            result.error(f"Item '{qid}' missing required 'text_key' field")

        if q.get("dimension") is not None and q["dimension"] not in dim_ids:
            result.error(f"Item '{qid}' references unknown dimension '{q['dimension']}'")

        if q.get("variant_group"):
            variant_groups.setdefault(q["variant_group"], []).append(qid)

        if qtype == "likert":
            has_item_pts = "likert_points" in q or ("likert_min" in q and "likert_max" in q)
            rsid = q.get("response_scale")
            has_named = bool(rsid) and rsid in rs_ids
            if rsid and not has_named:
                result.error(f"Item '{qid}' references unknown response_scale '{rsid}'")
            if not has_item_pts and not has_named and not has_default_points:
                result.warn(f"Item '{qid}' (likert) has no points and no scale-level default")

        elif qtype in ("multi", "multicheck"):
            if "options" not in q:
                result.error(f"Item '{qid}' ({qtype}) missing required 'options' field")
            elif isinstance(q["options"], list):
                for j, opt in enumerate(q["options"]):
                    if isinstance(opt, dict):
                        if "value" not in opt:
                            result.error(f"Item '{qid}' option {j} missing 'value'")
                        if "text_key" not in opt:
                            result.error(f"Item '{qid}' option {j} missing 'text_key'")

        elif qtype == "grid":
            if "rows" not in q and "columns" not in q:
                result.warn(f"Item '{qid}' (grid) has no rows or columns defined")
            # Register grid sub-item ids so scoring references resolve. Sub-items
            # are addressed as {gridid}_{1-based index} and/or {gridid}_{row id}.
            for idx, row in enumerate(q.get("rows") or [], start=1):
                qids.add(f"{qid}_{idx}")
                if isinstance(row, str):
                    qids.add(f"{qid}_{row}")
                elif isinstance(row, dict) and row.get("id"):
                    qids.add(f"{qid}_{row['id']}")

        elif qtype in ("image", "imageresponse"):
            if "image_file" not in q and "image" not in q:
                result.warn(f"Item '{qid}' ({qtype}) has no image_file specified")

        if "coding" in q and q["coding"] not in CODING_VALUES:
            result.warn(f"Item '{qid}' has unusual coding value: {q['coding']}")

    return qids, variant_groups


def _scoring_item_ids(items_field):
    """Yield (item_id, coding_or_None) from a scoring `items` field (list or object)."""
    if isinstance(items_field, dict):
        for k, v in items_field.items():
            yield k, v
    elif isinstance(items_field, list):
        for k in items_field:
            yield k, None


def validate_scoring(definition, qids, dim_ids, score_ids, variant_ids, result):
    scoring = definition.get("scoring")
    if scoring is None:
        return
    if not isinstance(scoring, dict):
        result.error("'scoring' must be an object")
        return

    # A scoring block's `items` may reference real items OR — for composites
    # built in the `items` field rather than `scores` — dimension/score ids.
    namespace = qids | dim_ids | score_ids
    for sid, sdef in scoring.items():
        if sid.startswith("_"):
            continue  # documentation/meta key (e.g. "_note"), not a scoring block
        if not isinstance(sdef, dict):
            result.error(f"Scoring '{sid}' must be an object")
            continue

        method = sdef.get("method")
        if method is None:
            result.error(f"Scoring '{sid}' missing required 'method' field")
        elif method not in SCORING_METHODS:
            result.warn(f"Scoring '{sid}' has unknown method '{method}'")

        has_items = "items" in sdef
        has_scores = "scores" in sdef
        if not has_items and not has_scores and method not in ("parameter", "shuffle", "constant"):
            result.warn(f"Scoring '{sid}' has neither 'items' nor 'scores'")

        for item_id, coding in _scoring_item_ids(sdef.get("items")):
            if item_id not in namespace:
                result.error(f"Scoring '{sid}' references unknown item/score '{item_id}'")
            if coding is not None and coding not in CODING_VALUES:
                result.warn(f"Scoring '{sid}' coding for '{item_id}' has unusual value: {coding}")

        if has_scores:
            if not isinstance(sdef["scores"], (list, dict)):
                result.error(f"Scoring '{sid}'.scores must be an array or object")
            else:
                refs = sdef["scores"].keys() if isinstance(sdef["scores"], dict) else sdef["scores"]
                for ref in refs:
                    if ref not in score_ids and ref not in dim_ids:
                        result.error(f"Scoring '{sid}'.scores references unknown score/dimension '{ref}'")

        # deprecated item_coding
        if isinstance(sdef.get("item_coding"), dict):
            for item_id, coding in sdef["item_coding"].items():
                if item_id not in qids:
                    result.error(f"Scoring '{sid}' item_coding references unknown item '{item_id}'")
                if coding not in CODING_VALUES:
                    result.warn(f"Scoring '{sid}' item_coding for '{item_id}' has unusual value: {coding}")

        # value_map keys should be known items (or 'default')
        if isinstance(sdef.get("value_map"), dict):
            for item_id, arr in sdef["value_map"].items():
                if item_id != "default" and item_id not in qids:
                    result.error(f"Scoring '{sid}' value_map references unknown item '{item_id}'")
                if not isinstance(arr, list):
                    result.error(f"Scoring '{sid}' value_map['{item_id}'] must be an array")

        if isinstance(sdef.get("weights"), dict):
            for ref in sdef["weights"]:
                if ref not in qids and ref not in score_ids and ref not in dim_ids:
                    result.warn(f"Scoring '{sid}' weights references unknown item/score '{ref}'")
        if method == "weighted_sum" and "weights" not in sdef:
            result.warn(f"Scoring '{sid}' uses weighted_sum but has no 'weights'")
        if method == "weighted_mean" and "weights" not in sdef:
            result.warn(f"Scoring '{sid}' uses weighted_mean but has no 'weights'")
        if method == "sum_correct" and not ("correct_answers" in sdef or "answer_category" in sdef):
            result.error(f"Scoring '{sid}' uses sum_correct but has no 'correct_answers'/'answer_category'")

        if "variants" in sdef:
            if not isinstance(sdef["variants"], list):
                result.error(f"Scoring '{sid}'.variants must be an array")
            else:
                for v in sdef["variants"]:
                    if variant_ids and v not in variant_ids:
                        result.error(f"Scoring '{sid}'.variants references unknown variant '{v}'")

        if "transform" in sdef and not isinstance(sdef["transform"], list):
            result.error(f"Scoring '{sid}'.transform must be an array")


def validate_likert_options(definition, result):
    lo = definition.get("likert_options")
    if lo is None:
        return
    if not isinstance(lo, dict):
        result.error("'likert_options' must be an object")
        return
    for nf in ("points", "min", "max"):
        if nf in lo and not isinstance(lo[nf], (int, float)):
            result.error(f"likert_options.{nf} must be numeric")
    if "labels" in lo and not isinstance(lo["labels"], list):
        result.error("likert_options.labels must be an array")
    if "suppress_likert_numbers" in lo and not isinstance(lo["suppress_likert_numbers"], bool):
        result.warn("likert_options.suppress_likert_numbers should be boolean")


def validate_variants(definition, qids, result):
    """Validate the draft `variants` block (variant_strategy_proposal.md)."""
    v = definition.get("variants")
    if v is None:
        return set()
    if not isinstance(v, dict):
        result.error("'variants' must be an object")
        return set()
    sets = v.get("sets")
    axes = v.get("axes")
    if sets is None and axes is None:
        result.error("variants must define 'sets' (single-axis sugar) and/or 'axes' (multi-axis)")
        return set()
    if sets is not None and (not isinstance(sets, dict) or not sets):
        result.error("variants.sets must be a non-empty object")
        return set()
    set_ids = set(sets.keys()) if isinstance(sets, dict) else set()
    default = v.get("default")
    # default is a set id in the sugar form, or a coordinate object in the multi-axis form
    if isinstance(default, str) and default not in set_ids:
        result.error(f"variants.default '{default}' is not a defined set")

    # build item->groups for mutual-exclusivity checks
    item_group = {}
    for q in get_items(definition):
        if isinstance(q, dict) and q.get("variant_group"):
            item_group[q["id"]] = q["variant_group"]

    for sid, sdef in (sets.items() if isinstance(sets, dict) else []):
        if not isinstance(sdef, dict):
            result.error(f"variants.sets['{sid}'] must be an object")
            continue
        member_items = sdef.get("items")
        if member_items is None and not sdef.get("base"):
            result.error(f"variants.sets['{sid}'] must list 'items' (or inherit via 'base')")
        if isinstance(member_items, list):
            seen_groups = {}
            for it in member_items:
                if it not in qids:
                    result.error(f"variants.sets['{sid}'] references unknown item '{it}'")
                g = item_group.get(it)
                if g is not None:
                    seen_groups.setdefault(g, []).append(it)
            for g, members in seen_groups.items():
                if len(members) > 1:
                    result.error(f"variants.sets['{sid}'] includes >1 member of variant_group "
                                 f"'{g}': {members} (must be mutually exclusive)")
        if sdef.get("base") and sdef["base"] not in set_ids:
            result.error(f"variants.sets['{sid}'].base '{sdef['base']}' is not a defined set")
        if "scoring" in sdef and not isinstance(sdef["scoring"], list):
            result.error(f"variants.sets['{sid}'].scoring must be an array of scoring-block ids")
    return set_ids


def _cond_languages(cond):
    """The set of languages a variant_when condition restricts to, or None
    (unrestricted). Only `selector: language` leaves constrain language; a
    parameter-only condition leaves language unrestricted (the item appears in
    every language when that parameter value is chosen)."""
    if not isinstance(cond, dict):
        return None
    if "all" in cond:
        res = None
        for sub in cond["all"]:
            r = _cond_languages(sub)
            if r is not None:
                res = r if res is None else (res & r)
        return res
    if "any" in cond:
        res = set()
        for sub in cond["any"]:
            r = _cond_languages(sub)
            if r is None:
                return None  # one branch unrestricted ⇒ whole disjunction unrestricted
            res |= r
        return res
    if cond.get("selector") == "language":
        val = cond.get("value")
        if isinstance(val, list):
            return set(val)
        if isinstance(val, str):
            return {val}
    return None


def _intersect_langs(a, b):
    """Intersect two language restrictions where None means 'all languages'."""
    if a is None:
        return b
    if b is None:
        return a
    return a & b


def build_item_languages(definition):
    """item id -> set of languages it is administered in, or None (= all).
    Combines `sets` membership (the language axis) with `variant_when` language
    leaves; both must hold (AND), per the variant proposal §3.2b."""
    v = definition.get("variants") or {}
    sets = v.get("sets") if isinstance(v, dict) else None
    set_langs = {}
    if isinstance(sets, dict):
        for sdef in sets.values():
            if not isinstance(sdef, dict):
                continue
            langs, members = sdef.get("languages"), sdef.get("items")
            if isinstance(langs, list) and isinstance(members, list):
                for it in members:
                    set_langs.setdefault(it, set()).update(langs)
    sets_present = bool(set_langs)
    out = {}
    for q in get_items(definition):
        if not isinstance(q, dict):
            continue
        iid = q.get("id")
        vw = _cond_languages(q.get("variant_when")) if "variant_when" in q else None
        # an item listed in no set (when a sets block exists) is shared across all
        sl = set_langs.get(iid) if (sets_present and iid in set_langs) else None
        out[iid] = _intersect_langs(vw, sl)
    return out


def collect_required_keys(definition):
    """Map each referenced translation key -> the set of languages that need it
    (or None for all). Item text keys inherit the item's variant language
    restriction; shared structure (anchors, heads, response scales, page titles)
    is required in every language."""
    item_langs = build_item_languages(definition)
    keymap = {}

    def add(key, langs):
        if not key:
            return
        if key not in keymap:
            keymap[key] = set(langs) if langs is not None else None
        elif keymap[key] is None or langs is None:
            keymap[key] = None
        else:
            keymap[key] = keymap[key] | set(langs)

    rs = definition.get("response_scales") or {}
    for q in get_items(definition):
        if not isinstance(q, dict):
            continue
        langs = item_langs.get(q.get("id"))
        if "text_key" in q:
            add(q["text_key"], langs)
        for kf in ("question_head", "min_label", "max_label", "left", "right"):
            if q.get(kf):
                add(q[kf], langs)
        if isinstance(q.get("likert_labels"), list):
            for k in q["likert_labels"]:
                add(k, langs)
        rsid = q.get("response_scale")
        if rsid and rsid in rs:
            sdef = rs[rsid]
            for k in (sdef.get("labels") or []):
                add(k, None)  # response-scale labels are shared structure
            if sdef.get("question_head"):
                add(sdef["question_head"], None)
        if isinstance(q.get("options"), list):
            for opt in q["options"]:
                if isinstance(opt, dict) and opt.get("text_key"):
                    add(opt["text_key"], langs)
                elif isinstance(opt, str):
                    add(opt, langs)

    lo = definition.get("likert_options") or {}
    for k in (lo.get("labels") or []):
        add(k, None)
    if lo.get("question_head"):
        add(lo["question_head"], None)
    for sdef in rs.values():
        if isinstance(sdef, dict):
            for k in (sdef.get("labels") or []):
                add(k, None)
            if sdef.get("question_head"):
                add(sdef["question_head"], None)
    for page in (definition.get("pages") or []):
        if isinstance(page, dict) and page.get("title_key"):
            add(page["title_key"], None)
    return keymap


def validate_translations(translations, keymap, result):
    """translations: dict lang -> dict(key->text). A key is required for a
    language only if that language administers it (per-variant completeness)."""
    if not translations:
        result.error("No translations found (embedded 'translations' or {code}.{lang}.json)")
        return
    if "en" not in {l.lower() for l in translations}:
        result.warn("No English ('en') translation present")
    for lang, trans in translations.items():
        if not isinstance(trans, dict):
            result.error(f"Translation '{lang}' must be an object")
            continue
        present = {k.lower() for k in trans}
        missing = [k for k, langs in keymap.items()
                   if (langs is None or lang in langs) and k.lower() not in present]
        if missing:
            shown = ", ".join(sorted(missing)[:8])
            more = f" (+{len(missing) - 8} more)" if len(missing) > 8 else ""
            result.warn(f"Translation '{lang}' missing {len(missing)} key(s): {shown}{more}")


def validate_parameters(definition, result):
    params = definition.get("parameters")
    if params is None:
        return
    if not isinstance(params, dict):
        result.error("'parameters' must be an object")
        return
    for name, pdef in params.items():
        if not isinstance(pdef, dict):
            result.error(f"Parameter '{name}' must be an object")
            continue
        if pdef.get("type") and pdef["type"] not in PARAMETER_TYPES:
            result.warn(f"Parameter '{name}' has unknown type '{pdef['type']}'")
        if "default" not in pdef:
            result.warn(f"Parameter '{name}' has no default value")
        if pdef.get("type") == "choice" and "options" not in pdef:
            result.error(f"Parameter '{name}' is type 'choice' but has no 'options'")


def validate_pages(definition, qids, result):
    pages = definition.get("pages")
    if pages is None:
        return
    if not isinstance(pages, list):
        result.error("'pages' must be an array")
        return
    page_ids = set()
    referenced = set()
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
        if isinstance(page.get("items"), list):
            for item_id in page["items"]:
                if isinstance(item_id, str):
                    if item_id not in qids:
                        result.error(f"Page '{page['id']}' references unknown item '{item_id}'")
                    referenced.add(item_id)


VALID_SELECTORS = {"language"}


def validate_condition(condition, qids, result, context, param_ids=()):
    """Validate a visible_when / variant_when condition. Leaves may reference an
    item ('question'), the 'language' selector, or a 'parameter'."""
    if not isinstance(condition, dict):
        result.warn(f"{context}: condition must be an object")
        return
    if "all" in condition:
        for sub in condition["all"]:
            validate_condition(sub, qids, result, context, param_ids)
    elif "any" in condition:
        for sub in condition["any"]:
            validate_condition(sub, qids, result, context, param_ids)
    else:
        if condition.get("question") and condition["question"] not in qids:
            result.warn(f"{context}: references unknown item '{condition['question']}'")
        if "selector" in condition and condition["selector"] not in VALID_SELECTORS:
            result.warn(f"{context}: unknown selector '{condition['selector']}'")
        if condition.get("parameter") and param_ids and condition["parameter"] not in param_ids:
            result.warn(f"{context}: references unknown parameter '{condition['parameter']}'")
        if condition.get("operator") and condition["operator"] not in CONDITION_OPERATORS:
            result.warn(f"{context}: unknown operator '{condition['operator']}'")


def validate_scale(scale_dir):
    result = ValidationResult(scale_dir)

    def_file, code = find_definition_file(scale_dir)
    if def_file is None:
        result.error("No scale definition found (expected {code}.osd or {code}.json)")
        return result

    try:
        data = load_json(def_file)
    except json.JSONDecodeError as e:
        result.error(f"{def_file.name} is invalid JSON: {e}")
        return result
    if not isinstance(data, dict):
        result.error(f"{def_file.name} must be a JSON object")
        return result

    definition, embedded_trans, osd_version = unwrap(data)
    if osd_version is None:
        result.warn("Missing top-level 'osd_version'")

    info = validate_scale_info(definition, result)
    if info and info.get("code"):
        dir_name = Path(scale_dir).name
        if info["code"] != dir_name:
            result.warn(f"scale_info.code '{info['code']}' doesn't match directory name '{dir_name}'")

    dim_ids = validate_dimensions(definition, result)
    rs_ids = validate_response_scales(definition, result)
    scoring = definition.get("scoring") or {}
    # `_`-prefixed scoring keys are documentation/meta (e.g. "_note"), not blocks.
    score_ids = {k for k in scoring if not k.startswith("_")} if isinstance(scoring, dict) else set()
    # An item may tag a formal dimension OR a composite score id; accept both.
    qids, _vgroups = validate_questions(definition, dim_ids | score_ids, rs_ids, result)
    variant_ids = validate_variants(definition, qids, result)
    validate_likert_options(definition, result)
    validate_scoring(definition, qids, dim_ids, score_ids, variant_ids, result)
    validate_parameters(definition, result)
    validate_pages(definition, qids, result)

    # Translations: prefer embedded; else legacy separate files.
    if isinstance(embedded_trans, dict) and embedded_trans:
        translations = embedded_trans
    else:
        legacy = find_translation_files(scale_dir, code)
        translations = {}
        for lang, (fmt, fp) in legacy.items():
            if fmt == "legacy":
                result.warn(f"Translation '{lang}' uses legacy naming (.pbl-{lang}); rename to .{lang}.json")
            try:
                translations[lang] = load_json(fp)
            except json.JSONDecodeError as e:
                result.error(f"Translation file {fp.name} is invalid JSON: {e}")
    validate_translations(translations, collect_required_keys(definition), result)

    param_ids = set((definition.get("parameters") or {}).keys())
    for q in get_items(definition):
        if not isinstance(q, dict):
            continue
        if "visible_when" in q:
            validate_condition(q["visible_when"], qids, result, f"Item '{q.get('id', '?')}' visible_when", param_ids)
        if "variant_when" in q:
            validate_condition(q["variant_when"], qids, result, f"Item '{q.get('id', '?')}' variant_when", param_ids)
    for page in (definition.get("pages") or []):
        if isinstance(page, dict) and "visible_when" in page:
            validate_condition(page["visible_when"], qids, result, f"Page '{page.get('id', '?')}' visible_when", param_ids)

    return result


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    target_path = Path(sys.argv[1])
    if not target_path.exists():
        print(f"Error: '{target_path}' does not exist")
        sys.exit(2)

    scale_dirs = []
    if target_path.is_file():
        scale_dirs.append(target_path.parent)
    elif find_definition_file(target_path)[0] is not None:
        scale_dirs.append(target_path)
    else:
        for child in sorted(target_path.iterdir()):
            if child.is_dir() and find_definition_file(child)[0] is not None:
                scale_dirs.append(child)

    if not scale_dirs:
        print(f"Error: No scale definitions found in '{target_path}'")
        sys.exit(2)

    print(f"Validating {len(scale_dirs)} scale(s)...\n")
    all_passed = True
    n_pass = 0
    for scale_dir in scale_dirs:
        result = validate_scale(scale_dir)
        # In bulk mode, stay quiet about clean passes; always show problems.
        if len(scale_dirs) == 1 or not result.passed or result.warnings:
            print(result.summary())
            print()
        if result.passed:
            n_pass += 1
        else:
            all_passed = False

    print(f"Results: {n_pass}/{len(scale_dirs)} passed, {len(scale_dirs) - n_pass} failed")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
