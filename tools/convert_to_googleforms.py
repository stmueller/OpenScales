#!/usr/bin/env python3
"""Convert Open Scale Definition (OSD) format to a Google Apps Script (.gs).

Usage:
    python3 convert_to_googleforms.py <scale_directory> [--output FILE] [--lang LANG]
    python3 convert_to_googleforms.py scales/openscales/PHQ9/ --output PHQ9_googleforms.gs
    python3 convert_to_googleforms.py scales/openscales/PHQ9/ --lang de

The output is a self-contained Google Apps Script that, when pasted into the
Script Editor of any Google Form and run, builds the complete form in the user's
Google Drive.

How to use the output:
  1. Go to forms.google.com → create a blank form
  2. Click the three-dot menu → Script editor
  3. Paste the entire .gs file contents, replacing any existing code
  4. Click Save, then Run → createForm
  5. Grant permissions when prompted
  6. Find the new form in Google Drive

Item type mapping:
  likert (grouped, shared scale) -> GridItem (matrix of rows × columns)
  likert (single item)           -> MultipleChoiceItem
  multi                          -> MultipleChoiceItem
  multicheck                     -> CheckboxItem
  short                          -> TextItem
  long                           -> ParagraphTextItem
  vas                            -> ScaleItem (min/max, labeled endpoints)
  grid                           -> GridItem
  inst                           -> SectionHeaderItem (text only)
  section                        -> PageBreakItem with title

Limitations:
  - Scoring and reverse coding must be configured manually (Google Forms has no
    native scoring for research scales; quiz mode supports single-answer grading only)
  - visible_when / skip logic not supported (Google Forms branching is section-level only)
  - question_head (shared preamble) is prepended to GridItem title
  - VAS is approximated as a 1–N scale widget; slider appearance differs from OSD VAS
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from osd_loader import load_scale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _t(translations, lang, key, fallback=''):
    val = translations.get(lang, {}).get(key)
    if val is not None:
        return val
    val = translations.get('en', {}).get(key)
    if val is not None:
        return val
    return fallback or key


def _js_str(s):
    """Escape a string for embedding in a JS double-quoted literal."""
    s = str(s)
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '')
    # Strip HTML tags — Google Forms doesn't render HTML in question text
    s = re.sub(r'<[^>]+>', '', s)
    return s


def _get_effective_scale(item, defn):
    """Resolve the effective likert scale for an item."""
    rs_id = item.get('response_scale')
    rs = defn.get('response_scales', {})
    if rs_id and rs_id in rs:
        return rs[rs_id]
    if 'default' in rs:
        return rs['default']
    # Item-level overrides merged onto scale-level
    base = defn.get('likert_options', {})
    item_lo = item.get('likert_options', {})
    if item_lo:
        return {**base, **item_lo}
    return base


def _resolve_options(item, defn):
    """Resolve multi/multicheck options list."""
    if item.get('options') is not None:
        return item['options']
    option_sets = defn.get('option_sets', {})
    os_id = item.get('option_set')
    if os_id and os_id in option_sets:
        return option_sets[os_id]
    if 'default' in option_sets:
        return option_sets['default']
    return []


def _option_text(opt, translations, lang):
    if isinstance(opt, dict):
        key = opt.get('text_key') or opt.get('value', '')
        return _t(translations, lang, key, str(opt.get('value', key)))
    return _t(translations, lang, str(opt), str(opt))


# ---------------------------------------------------------------------------
# Likert grouping (same logic as other converters)
# ---------------------------------------------------------------------------

def _scale_sig(item, defn):
    """Signature string identifying a likert scale — items with the same sig share a GridItem."""
    rs_id = item.get('response_scale')
    if rs_id:
        return f'rs:{rs_id}'
    eff = _get_effective_scale(item, defn)
    pts = item.get('likert_points') or eff.get('points', 5)
    mn  = item.get('likert_min')    or eff.get('min', 1)
    qh  = item.get('question_head') or eff.get('question_head', '')
    return f'lo:{pts}:{mn}:{qh}'


def _group_items(items, defn):
    """
    Yield (group_type, payload) tuples preserving item order.
    group_type is one of: 'likert_block', 'item'
    payload for 'likert_block' is a list of likert items sharing a scale.
    payload for 'item' is a single item dict.
    """
    buf = []
    buf_sig = None

    for item in items:
        if item.get('type') == 'likert':
            sig = _scale_sig(item, defn)
            if sig != buf_sig:
                if buf:
                    yield ('likert_block', buf)
                buf = [item]
                buf_sig = sig
            else:
                buf.append(item)
        else:
            if buf:
                yield ('likert_block', buf)
                buf = []
                buf_sig = None
            yield ('item', item)

    if buf:
        yield ('likert_block', buf)


# ---------------------------------------------------------------------------
# JS statement generators
# ---------------------------------------------------------------------------

def _emit_page_break(lines, title, description=''):
    lines.append('  var pb = form.addPageBreakItem();')
    if title:
        lines.append(f'  pb.setTitle("{_js_str(title)}");')
    if description:
        lines.append(f'  pb.setHelpText("{_js_str(description)}");')
    lines.append('')


def _emit_section_header(lines, text):
    lines.append('  form.addSectionHeaderItem()')
    lines.append(f'      .setTitle("{_js_str(text)}");')
    lines.append('')


def _emit_grid(lines, title, rows, col_labels, required=False):
    """Emit a GridItem (matrix). rows = list of (value, label) row dicts."""
    req = 'true' if required else 'false'
    lines.append('  var grid = form.addGridItem();')
    lines.append(f'  grid.setTitle("{_js_str(title)}");')
    row_strs = ', '.join(f'"{_js_str(r)}"' for r in rows)
    col_strs = ', '.join(f'"{_js_str(c)}"' for c in col_labels)
    lines.append(f'  grid.setRows([{row_strs}]);')
    lines.append(f'  grid.setColumns([{col_strs}]);')
    lines.append(f'  grid.setRequired({req});')
    lines.append('')


def _emit_multiple_choice(lines, title, choices, required=False):
    req = 'true' if required else 'false'
    lines.append('  var mc = form.addMultipleChoiceItem();')
    lines.append(f'  mc.setTitle("{_js_str(title)}");')
    choice_strs = ', '.join(f'mc.createChoice("{_js_str(c)}")' for c in choices)
    lines.append(f'  mc.setChoices([{choice_strs}]);')
    lines.append(f'  mc.setRequired({req});')
    lines.append('')


def _emit_checkbox(lines, title, choices, required=False):
    req = 'true' if required else 'false'
    lines.append('  var cb = form.addCheckboxItem();')
    lines.append(f'  cb.setTitle("{_js_str(title)}");')
    choice_strs = ', '.join(f'cb.createChoice("{_js_str(c)}")' for c in choices)
    lines.append(f'  cb.setChoices([{choice_strs}]);')
    lines.append(f'  cb.setRequired({req});')
    lines.append('')


def _emit_text(lines, title, paragraph=False, required=False):
    req = 'true' if required else 'false'
    kind = 'ParagraphText' if paragraph else 'Text'
    lines.append(f'  form.add{kind}Item()')
    lines.append(f'      .setTitle("{_js_str(title)}")')
    lines.append(f'      .setRequired({req});')
    lines.append('')


def _emit_scale(lines, title, mn, mx, min_label='', max_label='', required=False):
    req = 'true' if required else 'false'
    lines.append('  var sc = form.addScaleItem();')
    lines.append(f'  sc.setTitle("{_js_str(title)}");')
    lines.append(f'  sc.setBounds({mn}, {mx});')
    if min_label:
        lines.append(f'  sc.setLabels("{_js_str(min_label)}", "{_js_str(max_label)}");')
    lines.append(f'  sc.setRequired({req});')
    lines.append('')


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert(scale_dir, lang='en'):
    defn, translations, code = load_scale(scale_dir, lang)
    items = defn.get('items', [])
    scale_info = defn.get('scale_info', {})
    name = scale_info.get('name', code)

    lines = []
    lines.append(f'// Google Apps Script — {name}')
    lines.append(f'// Generated from {code}.osd by convert_to_googleforms.py')
    lines.append(f'//')
    lines.append(f'// Instructions:')
    lines.append(f'//   1. Open forms.google.com and create a blank form')
    lines.append(f'//   2. Click the three-dot menu → Script editor')
    lines.append(f'//   3. Paste this entire file, replacing any existing code')
    lines.append(f'//   4. Click Save, then Run → createForm')
    lines.append(f'//   5. Grant permissions when prompted')
    lines.append(f'//   6. Find the new form in Google Drive')
    lines.append('')

    # Scoring note as a JS comment
    scoring = defn.get('scoring', {})
    dims = scoring.get('dimensions', {})
    if dims:
        lines.append('// Scoring (configure manually in Google Forms quiz settings):')
        for dim_name, dim in dims.items():
            method = dim.get('method', 'sum_coded')
            item_ids = list(dim.get('items', {}).keys()) if isinstance(dim.get('items'), dict) else dim.get('items', [])
            lines.append(f'//   {dim_name}: {method} of [{", ".join(str(i) for i in item_ids)}]')
        lines.append('')

    lines.append('function createForm() {')
    lines.append(f'  var form = FormApp.create("{_js_str(name)}");')
    lines.append(f'  form.setDescription("{_js_str(scale_info.get("description", ""))}");')
    lines.append('')

    for group_type, payload in _group_items(items, defn):

        if group_type == 'likert_block':
            block = payload
            first = block[0]
            eff = _get_effective_scale(first, defn)

            pts = first.get('likert_points') or eff.get('points', 5)
            mn  = first.get('likert_min')    or eff.get('min', 1)
            mx  = mn + pts - 1
            label_keys = first.get('likert_labels') or eff.get('labels', [])

            col_labels = []
            for i in range(pts):
                val = mn + i
                key = label_keys[i] if i < len(label_keys) else None
                if key:
                    text = _t(translations, lang, key, str(val))
                else:
                    text = str(val)
                col_labels.append(text)

            # Title: question_head if shared, else blank (rows carry the text)
            qh_key = first.get('question_head') or eff.get('question_head', '')
            title = _t(translations, lang, qh_key, '') if qh_key else ''

            if len(block) == 1:
                # Single likert — use MultipleChoiceItem unless question_head present
                item_text = _t(translations, lang, first.get('text_key', first['id']), first['id'])
                full_title = f'{title}\n\n{item_text}'.strip() if title else item_text
                _emit_multiple_choice(lines, full_title, col_labels,
                                      required=first.get('required', False))
            else:
                # Multiple items — use GridItem
                row_labels = []
                required = False
                for it in block:
                    row_text = _t(translations, lang, it.get('text_key', it['id']), it['id'])
                    row_labels.append(row_text)
                    if it.get('required'):
                        required = True
                _emit_grid(lines, title, row_labels, col_labels, required=required)

        else:
            item = payload
            itype = item.get('type', 'short')
            text_key = item.get('text_key', item.get('id', ''))
            text = _t(translations, lang, text_key, item.get('id', ''))
            req = item.get('required', False)

            if itype == 'section':
                _emit_page_break(lines, text)

            elif itype == 'inst':
                _emit_section_header(lines, text)

            elif itype == 'multi':
                opts = _resolve_options(item, defn)
                choices = [_option_text(o, translations, lang) for o in opts]
                _emit_multiple_choice(lines, text, choices, required=req)

            elif itype == 'multicheck':
                opts = _resolve_options(item, defn)
                choices = [_option_text(o, translations, lang) for o in opts]
                _emit_checkbox(lines, text, choices, required=req)

            elif itype == 'short':
                _emit_text(lines, text, paragraph=False, required=req)

            elif itype == 'long':
                _emit_text(lines, text, paragraph=True, required=req)

            elif itype == 'vas':
                mn = item.get('min', 0)
                mx = item.get('max', 100)
                # Google ScaleItem supports 2–10 points; clamp to a 10-point scale
                # and note the approximation
                scale_points = min(mx - mn, 10)
                if scale_points < 2:
                    scale_points = 2
                min_label = _t(translations, lang, item.get('min_label', ''), '')
                max_label = _t(translations, lang, item.get('max_label', ''), '')
                lines.append(f'  // VAS approximated as {scale_points}-point scale (original: {mn}–{mx})')
                _emit_scale(lines, text, 1, scale_points, min_label, max_label, required=req)

            elif itype == 'grid':
                rows_raw = item.get('rows', [])
                cols_raw = item.get('columns', [])
                row_labels = []
                for r in rows_raw:
                    if isinstance(r, dict):
                        row_labels.append(_t(translations, lang, r.get('text_key', r.get('id', '')), r.get('id', '')))
                    else:
                        row_labels.append(_t(translations, lang, str(r), str(r)))
                col_labels = []
                for c in cols_raw:
                    if isinstance(c, dict):
                        col_labels.append(_t(translations, lang, c.get('text_key', str(c.get('value', ''))), str(c.get('value', ''))))
                    else:
                        col_labels.append(_t(translations, lang, str(c), str(c)))
                _emit_grid(lines, text, row_labels, col_labels, required=req)

            else:
                lines.append(f'  // SKIPPED: {item.get("id", "?")} (unsupported type: {itype})')
                lines.append('')

    lines.append('  Logger.log("Form created: " + form.getEditUrl());')
    lines.append('}')
    lines.append('')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Convert OSD scale to Google Apps Script (.gs)')
    parser.add_argument('scale_dir', help='Scale directory containing .osd file')
    parser.add_argument('--output', '-o', help='Output .gs file (default: stdout)')
    parser.add_argument('--lang', default='en', help='Language code (default: en)')
    args = parser.parse_args()

    script = convert(args.scale_dir, lang=args.lang)

    if args.output:
        Path(args.output).write_text(script, encoding='utf-8')
        print(f'Written to: {args.output}', file=sys.stderr)
    else:
        print(script)


if __name__ == '__main__':
    main()
