"""Shared handling of OSD conversion parameters for the export converters.

Parameters (settable via repeatable `--param KEY=VALUE`) come in three kinds; this module
lets every converter honor the format-agnostic ones with a couple of lines:

  1. Substitution params (type `string`/`choice`/`integer`/`number`)
       Item/anchor/title text may contain `[name]` (ESS square-bracket convention) or
       `{name}` (curly) placeholders. `apply_substitutions()` replaces them with the
       parameter's value across every translation string, so the output text is already
       personalized — no per-converter logic needed. Runtime piping tokens ({answer.*},
       {score.*}, {computed.*}) are left untouched (the converter can't resolve them).

  2. show_header (reserved, boolean, default true)
       When false, the respondent-facing scale title/header is blanked so the instrument
       name (e.g. "Bullshit Receptivity Scale") is not revealed. Each converter guards its
       title emission with `show_header(params)`.

  3. shuffle_questions (reserved, boolean, default false)
       Request random item order. Honored ONLY by formats whose import spec has a native
       randomization flag (via `shuffle_questions(params)`); we never bake a fixed random
       order — that is no better than the authored order.

Unspecified params fall back to the default declared in the scale's `definition.parameters`,
matching the runner's behavior (so `[system]` renders its default even with no override).

Security: values arrive from the web layer already `escapeshellarg`-quoted; this module does
plain string substitution and never evaluates or shells out, so a hostile value can only
appear as literal text in the output — it cannot inject a command.
"""
import re

_TRUE = {"1", "true", "yes", "on", "t", "y"}
_FALSE = {"0", "false", "no", "off", "f", "n"}
# curly-brace tokens that are runtime piping, NOT simple parameter substitution
_PIPE_PREFIX = ("answer.", "score.", "computed.", "dim.", "item.", "response.")


def add_param_arg(parser):
    """Register the repeatable --param KEY=VALUE argument on an argparse parser."""
    parser.add_argument(
        "--param", action="append", default=[], metavar="KEY=VALUE",
        help="Set a scale parameter (repeatable), e.g. --param show_header=false or "
             "--param system='Acme Corp'. String values substitute [name]/{name} tokens "
             "in item text; show_header / shuffle_questions are reserved.")


def _coerce(v):
    lv = v.strip().lower()
    if lv in _TRUE:
        return True
    if lv in _FALSE:
        return False
    s = v.strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d*\.\d+", s):
        return float(s)
    return v


def parse_params(pairs):
    """Parse ['k=v', ...] (argparse --param) into a typed dict."""
    out = {}
    for p in (pairs or []):
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        k = k.strip()
        if k:
            out[k] = _coerce(v)
    return out


def effective_params(defn, overrides):
    """Declared parameter defaults (from definition.parameters) merged with CLI overrides."""
    eff = {}
    for name, pdef in (defn.get("parameters") or {}).items():
        if isinstance(pdef, dict) and "default" in pdef:
            eff[name] = pdef["default"]
    eff.update(overrides or {})
    return eff


def _sub_text(text, params):
    if not isinstance(text, str) or not params or ("[" not in text and "{" not in text):
        return text

    def sq(m):
        name = m.group(1).strip()
        return str(params[name]) if name in params else m.group(0)

    def cu(m):
        name = m.group(1).strip()
        if any(name.startswith(p) for p in _PIPE_PREFIX):
            return m.group(0)
        return str(params[name]) if name in params else m.group(0)

    text = re.sub(r"\[([^\[\]]+)\]", sq, text)   # [name] — ESS convention
    text = re.sub(r"\{([^{}]+)\}", cu, text)     # {name} — curly (skip piping)
    return text


def apply_substitutions(translations, params):
    """In place: substitute [name]/{name} param tokens in every translation string."""
    for _lang, strings in (translations or {}).items():
        if isinstance(strings, dict):
            for k, v in strings.items():
                if isinstance(v, str):
                    strings[k] = _sub_text(v, params)


def show_header(params):
    """True unless show_header is explicitly falsy."""
    v = (params or {}).get("show_header", True)
    return v not in (False, 0, "0")


def shuffle_questions(params):
    """True only if shuffle_questions is explicitly truthy."""
    v = (params or {}).get("shuffle_questions", False)
    return v in (True, 1, "1")


def prepare(defn, translations, cli_param_pairs):
    """Convenience: parse CLI params, resolve effective values, apply text substitutions.

    Mutates `translations` in place and returns the effective params dict. Call right after
    load_scale() so all downstream text the converter reads is already substituted.
    """
    params = effective_params(defn, parse_params(cli_param_pairs))
    apply_substitutions(translations, params)
    return params
