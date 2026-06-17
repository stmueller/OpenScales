"""Variant resolution for OSD converters — Python mirror of the JS runner.

Flattens a multi-variant OSD `definition` down to the single variant active for a
given language (and parameter defaults), per
documentation/proposals/variant_strategy_proposal.md:

  * items are dropped unless their `variant_when` passes and (when a
    `variants.sets` block lists them) the active language's set includes them;
  * scoring blocks and dimensions tagged with a `variants` array are dropped
    unless one of their set ids is active.

Single-variant / variant-free OSDs are returned unchanged, so converters can call
`flatten_variant(definition, lang)` unconditionally.
"""

import copy


def _eval_condition(cond, params):
    """Evaluate a variant_when condition against {selector/parameter} values.
    Answer-based leaves (`item`/`question`) can't be resolved at flatten time and
    are treated as satisfied (the item stays; runtime visible_when still applies)."""
    if not cond:
        return True
    if isinstance(cond, str):
        v = params.get(cond)
        return v not in (None, 0, "0", False, "", "NA")
    if "all" in cond:
        return all(_eval_condition(c, params) for c in cond["all"])
    if "any" in cond:
        return any(_eval_condition(c, params) for c in cond["any"])
    if cond.get("selector") == "language":
        lhs = params.get("__lang__")
    elif "parameter" in cond:
        lhs = params.get(cond["parameter"])
    elif "item" in cond or "question" in cond:
        return True  # runtime answer condition — not a variant selector
    else:
        return True
    op, rhs = cond.get("operator"), cond.get("value")
    ls = "" if lhs is None else str(lhs)
    if op in ("in", "not_in"):
        vals = rhs if isinstance(rhs, list) else str(rhs).split(",")
        vals = [str(x).strip() for x in vals]
        return (ls in vals) if op == "in" else (ls not in vals)
    if op == "equals":
        return ls == str(rhs)
    if op == "not_equals":
        return ls != str(rhs)
    return True


def active_variant_set_ids(definition, lang):
    """Set of variant-set ids active for `lang` (sets whose `languages` include
    it; else a string `default`). None when the scale defines no `sets`."""
    v = definition.get("variants") or {}
    sets = v.get("sets")
    if not sets:
        return None
    ids = [sid for sid, sd in sets.items()
           if isinstance(sd, dict) and lang in (sd.get("languages") or [])]
    if not ids and isinstance(v.get("default"), str):
        ids = [v["default"]]
    return set(ids)


def is_scoring_active(score_def, active_sets):
    if not isinstance(score_def, dict):
        return True
    v = score_def.get("variants")
    if not isinstance(v, list):
        return True
    if active_sets is None:
        return True
    return any(s in active_sets for s in v)


def _items_key(definition):
    return "items" if "items" in definition else "questions"


def _governed_sets(definition):
    """item id -> set of variant-set ids that list it (only items in some set)."""
    sets = (definition.get("variants") or {}).get("sets") or {}
    governed = {}
    for sid, sd in sets.items():
        for it in (sd.get("items") or []):
            governed.setdefault(it, set()).add(sid)
    return governed


def item_in_active_variant(item, params, active_sets, governed):
    if not isinstance(item, dict):
        return True
    vw = item.get("variant_when")
    if vw and not _eval_condition(vw, params):
        return False
    if active_sets is not None:
        g = governed.get(item.get("id"))
        if g and not (g & active_sets):
            return False
    return True


def flatten_variant(definition, lang, params=None):
    """Return `definition` reduced to the variant active for `lang`. No-op when
    the scale has no variants. `definition` is the unwrapped OSD definition
    (i.e. the contents of the top-level "definition" key)."""
    items = definition.get("items") or definition.get("questions") or []
    has_vw = any(isinstance(it, dict) and it.get("variant_when") for it in items)
    if not definition.get("variants") and not has_vw:
        return definition

    d = copy.deepcopy(definition)
    p = {}
    for name, pd in (d.get("parameters") or {}).items():
        if isinstance(pd, dict) and "default" in pd:
            p[name] = pd["default"]
    if params:
        p.update(params)
    p["__lang__"] = lang

    active_sets = active_variant_set_ids(d, lang)
    governed = _governed_sets(d)

    ik = _items_key(d)
    d[ik] = [it for it in (d.get(ik) or [])
             if item_in_active_variant(it, p, active_sets, governed)]

    orig_scoring = d.get("scoring") if isinstance(d.get("scoring"), dict) else {}
    active_keys = {k for k, v in orig_scoring.items()
                   if k.startswith("_") or is_scoring_active(v, active_sets)}
    if isinstance(d.get("scoring"), dict):
        d["scoring"] = {k: v for k, v in d["scoring"].items() if k in active_keys}
    if isinstance(d.get("dimensions"), list):
        d["dimensions"] = [
            dim for dim in d["dimensions"]
            if not isinstance(dim, dict)
            or dim.get("id") in active_keys
            or dim.get("id") not in orig_scoring
        ]
    return d
