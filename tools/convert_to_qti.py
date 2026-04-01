#!/usr/bin/env python3
"""Convert Open Scale Definition (OSD) format to QTI 3.0 content package.

Usage:
    python3 convert_to_qti.py <scale_directory> [--output FILE] [--lang LANG]
    python3 convert_to_qti.py scales/grit/ --output grit_qti.zip

Reads {code}.json and {code}.{lang}.json from a scale directory and generates
a QTI 3.0 content package (ZIP) suitable for import into LMS platforms:
    Canvas, Blackboard, Moodle, Sakai, Brightspace, etc.

Output structure:
    {code}_qti.zip/
        imsmanifest.xml          -- Content package manifest
        assessment.xml           -- Assessment test structure
        items/
            {id}.xml             -- One QTI assessment item per question
        scoring_info.json        -- Supplementary scoring definitions

Supported conversions:
  - likert           -> qti-choice-interaction (one item per question)
  - multi            -> qti-choice-interaction (max-choices="1")
  - multicheck       -> qti-choice-interaction (max-choices="0")
  - dropdown         -> qti-inline-choice-interaction
  - short            -> qti-text-entry-interaction
  - long             -> qti-extended-text-interaction
  - vas              -> qti-slider-interaction
  - grid             -> qti-match-interaction
  - rank             -> qti-order-interaction
  - inst             -> qti-item-body only (no interaction)
  - image            -> qti-item-body with <img>
  - constant_sum     -> multiple qti-text-entry-interaction
  - semantic_diff.   -> multiple qti-choice-interaction

Notes:
  - QTI has no concept of aggregated subscale scoring. Scoring definitions
    are included in scoring_info.json for reference.
  - Survey items omit response processing (no correct answers).
  - Items with correct answers (sum_correct method) include response
    processing and scoring.
"""

import json
import re
import sys
import zipfile
import io
from pathlib import Path
from xml.etree import ElementTree as ET


QTI_NS = "http://www.imsglobal.org/xsd/imsqtiasi_v3p0"
CP_NS = "http://www.imsglobal.org/xsd/imscp_v1p1"
XHTML_NS = "http://www.w3.org/1999/xhtml"


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


def escape_xml(text):
    """Escape text for XML content (not attributes)."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def text_to_xhtml(text):
    """Convert scale text (may contain HTML) to XHTML for QTI item body.

    Returns a string of XHTML paragraph(s) suitable for embedding in
    qti-item-body. Basic HTML tags are preserved; plain text gets wrapped
    in <p> tags.
    """
    # Replace \n with <br/>
    text = text.replace("\n", "<br/>")
    # If text already contains block-level HTML, wrap minimally
    if "<p>" in text.lower() or "<div>" in text.lower() or "<ul>" in text.lower():
        return text
    return f"<p>{text}</p>"


def make_identifier(prefix, raw_id):
    """Create a valid XML identifier from a prefix and raw ID."""
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw_id))
    return f"{prefix}_{clean}"


# --- QTI Item Builders ---

def build_item_xml(question, definition, translations, scoring):
    """Build a complete QTI 3.0 assessment item XML string."""
    qtype = question.get("type", "")
    qid = question["id"]
    text = get_text(translations, question.get("text_key", qid))

    builder = ITEM_BUILDERS.get(qtype, _build_info_item)
    return builder(qid, text, question, definition, translations, scoring)


def _xml_header(identifier, title):
    """Return the XML declaration and opening qti-assessment-item tag."""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<qti-assessment-item\n'
        f'    xmlns="{QTI_NS}"\n'
        f'    identifier="{escape_xml(identifier)}"\n'
        f'    title="{escape_xml(title)}"\n'
        f'    adaptive="false"\n'
        f'    time-dependent="false">\n'
    )


def _xml_footer():
    return '</qti-assessment-item>\n'


def _build_likert_item(qid, text, question, definition, translations, scoring):
    """Build a likert item as qti-choice-interaction."""
    likert_opts = definition.get("likert_options", {})
    labels = []
    if "likert_labels" in question:
        labels = [get_text(translations, lbl) for lbl in question["likert_labels"]]
    elif likert_opts.get("labels"):
        labels = [get_text(translations, lbl) for lbl in likert_opts["labels"]]
    else:
        points = question.get("likert_points", likert_opts.get("points", 5))
        min_val = likert_opts.get("min", 1)
        labels = [str(min_val + i) for i in range(points)]

    min_val = likert_opts.get("min", 1)

    xml = _xml_header(qid, strip_html(text)[:80])
    xml += (
        f'  <qti-response-declaration identifier="RESPONSE" '
        f'cardinality="single" base-type="identifier"/>\n'
    )
    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'
    xml += (
        f'    <qti-choice-interaction response-identifier="RESPONSE" '
        f'shuffle="false" max-choices="1">\n'
    )
    for i, label in enumerate(labels):
        val = min_val + i
        choice_id = f"choice_{val}"
        xml += (
            f'      <qti-simple-choice identifier="{choice_id}">'
            f'{escape_xml(label)}</qti-simple-choice>\n'
        )
    xml += '    </qti-choice-interaction>\n'
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_multi_item(qid, text, question, definition, translations, scoring):
    """Build a multiple-choice (single select) item."""
    options = question.get("options", [])
    max_choices = "1"

    xml = _xml_header(qid, strip_html(text)[:80])
    xml += (
        f'  <qti-response-declaration identifier="RESPONSE" '
        f'cardinality="single" base-type="identifier"/>\n'
    )

    # Add correct response if available from scoring
    correct = _get_correct_answers(qid, scoring)
    if correct:
        xml += '  <qti-response-processing/>\n'

    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'
    xml += (
        f'    <qti-choice-interaction response-identifier="RESPONSE" '
        f'shuffle="false" max-choices="{max_choices}">\n'
    )
    for opt in options:
        if isinstance(opt, dict):
            opt_val = opt.get("value", "")
            opt_text = get_text(translations,
                                opt.get("text_key", opt.get("value", "")))
        else:
            opt_val = opt
            opt_text = get_text(translations, opt)
        choice_id = make_identifier("opt", opt_val)
        xml += (
            f'      <qti-simple-choice identifier="{choice_id}">'
            f'{escape_xml(opt_text)}</qti-simple-choice>\n'
        )
    xml += '    </qti-choice-interaction>\n'
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_multicheck_item(qid, text, question, definition, translations, scoring):
    """Build a multiple-choice (multi select) item."""
    options = question.get("options", [])

    xml = _xml_header(qid, strip_html(text)[:80])
    xml += (
        f'  <qti-response-declaration identifier="RESPONSE" '
        f'cardinality="multiple" base-type="identifier"/>\n'
    )
    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'
    xml += (
        f'    <qti-choice-interaction response-identifier="RESPONSE" '
        f'shuffle="false" max-choices="0">\n'
    )
    for opt in options:
        if isinstance(opt, dict):
            opt_val = opt.get("value", "")
            opt_text = get_text(translations,
                                opt.get("text_key", opt.get("value", "")))
        else:
            opt_val = opt
            opt_text = get_text(translations, opt)
        choice_id = make_identifier("opt", opt_val)
        xml += (
            f'      <qti-simple-choice identifier="{choice_id}">'
            f'{escape_xml(opt_text)}</qti-simple-choice>\n'
        )
    xml += '    </qti-choice-interaction>\n'
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_short_item(qid, text, question, definition, translations, scoring):
    """Build a short text entry item."""
    xml = _xml_header(qid, strip_html(text)[:80])
    xml += (
        f'  <qti-response-declaration identifier="RESPONSE" '
        f'cardinality="single" base-type="string"/>\n'
    )

    # Check for correct answers (e.g., CRT)
    correct = _get_correct_answers(qid, scoring)
    if correct:
        xml += '  <qti-response-processing>\n'
        xml += '    <qti-response-condition>\n'
        xml += '      <qti-response-if>\n'
        xml += (
            '        <qti-match>\n'
            '          <qti-variable identifier="RESPONSE"/>\n'
            f'          <qti-correct identifier="RESPONSE"/>\n'
            '        </qti-match>\n'
        )
        xml += '        <qti-set-outcome-value identifier="SCORE">\n'
        xml += '          <qti-base-value base-type="float">1</qti-base-value>\n'
        xml += '        </qti-set-outcome-value>\n'
        xml += '      </qti-response-if>\n'
        xml += '    </qti-response-condition>\n'
        xml += '  </qti-response-processing>\n'

    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'

    maxlength = question.get("maxlength", "")
    attrs = 'response-identifier="RESPONSE"'
    if maxlength:
        attrs += f' expected-length="{maxlength}"'

    xml += f'    <qti-text-entry-interaction {attrs}/>\n'
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_long_item(qid, text, question, definition, translations, scoring):
    """Build a long text entry item."""
    rows = question.get("rows", 5)

    xml = _xml_header(qid, strip_html(text)[:80])
    xml += (
        f'  <qti-response-declaration identifier="RESPONSE" '
        f'cardinality="single" base-type="string"/>\n'
    )
    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'
    xml += (
        f'    <qti-extended-text-interaction '
        f'response-identifier="RESPONSE" expected-lines="{rows}"/>\n'
    )
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_vas_item(qid, text, question, definition, translations, scoring):
    """Build a VAS/slider item."""
    min_val = question.get("min", 0)
    max_val = question.get("max", 100)
    step = question.get("step", 1)

    xml = _xml_header(qid, strip_html(text)[:80])
    xml += (
        f'  <qti-response-declaration identifier="RESPONSE" '
        f'cardinality="single" base-type="float"/>\n'
    )
    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'

    # Add endpoint labels as text if available
    if "min_label" in question or "max_label" in question:
        min_label = get_text(translations, question.get("min_label", "")) \
            if "min_label" in question else str(min_val)
        max_label = get_text(translations, question.get("max_label", "")) \
            if "max_label" in question else str(max_val)
        xml += f'    <p><em>{escape_xml(min_label)}</em> — '
        xml += f'<em>{escape_xml(max_label)}</em></p>\n'

    xml += (
        f'    <qti-slider-interaction response-identifier="RESPONSE" '
        f'lower-bound="{min_val}" upper-bound="{max_val}" step="{step}"/>\n'
    )
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_grid_item(qid, text, question, definition, translations, scoring):
    """Build a grid/matrix item as qti-match-interaction."""
    columns = question.get("columns", [])
    rows = question.get("rows", [])

    xml = _xml_header(qid, strip_html(text)[:80])
    xml += (
        f'  <qti-response-declaration identifier="RESPONSE" '
        f'cardinality="multiple" base-type="directedPair"/>\n'
    )
    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'
    xml += (
        f'    <qti-match-interaction response-identifier="RESPONSE" '
        f'shuffle="false" max-associations="0">\n'
    )

    # First match set: rows (items)
    xml += '      <qti-simple-match-set>\n'
    for i, row in enumerate(rows):
        row_text = get_text(translations, row) if isinstance(row, str) else str(row)
        row_id = make_identifier("row", i)
        xml += (
            f'        <qti-simple-associable-choice '
            f'identifier="{row_id}" match-max="1">'
            f'{escape_xml(strip_html(row_text))}'
            f'</qti-simple-associable-choice>\n'
        )
    xml += '      </qti-simple-match-set>\n'

    # Second match set: columns (response options)
    xml += '      <qti-simple-match-set>\n'
    for i, col in enumerate(columns):
        col_text = get_text(translations, col) if isinstance(col, str) else str(col)
        col_id = make_identifier("col", i)
        xml += (
            f'        <qti-simple-associable-choice '
            f'identifier="{col_id}" match-max="0">'
            f'{escape_xml(strip_html(col_text))}'
            f'</qti-simple-associable-choice>\n'
        )
    xml += '      </qti-simple-match-set>\n'

    xml += '    </qti-match-interaction>\n'
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_rank_item(qid, text, question, definition, translations, scoring):
    """Build a ranking/ordering item."""
    options = question.get("options", [])

    xml = _xml_header(qid, strip_html(text)[:80])
    xml += (
        f'  <qti-response-declaration identifier="RESPONSE" '
        f'cardinality="ordered" base-type="identifier"/>\n'
    )
    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'
    xml += (
        f'    <qti-order-interaction response-identifier="RESPONSE" '
        f'shuffle="false">\n'
    )
    for opt in options:
        if isinstance(opt, dict):
            opt_val = opt.get("value", "")
            opt_text = get_text(translations,
                                opt.get("text_key", opt.get("value", "")))
        else:
            opt_val = opt
            opt_text = get_text(translations, opt)
        choice_id = make_identifier("opt", opt_val)
        xml += (
            f'      <qti-simple-choice identifier="{choice_id}">'
            f'{escape_xml(opt_text)}</qti-simple-choice>\n'
        )
    xml += '    </qti-order-interaction>\n'
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_dropdown_item(qid, text, question, definition, translations, scoring):
    """Build a dropdown item using qti-inline-choice-interaction."""
    options = question.get("options", [])

    xml = _xml_header(qid, strip_html(text)[:80])
    xml += (
        f'  <qti-response-declaration identifier="RESPONSE" '
        f'cardinality="single" base-type="identifier"/>\n'
    )
    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'
    xml += '    <p>Select: <qti-inline-choice-interaction response-identifier="RESPONSE">\n'
    for opt in options:
        if isinstance(opt, dict):
            opt_val = opt.get("value", "")
            opt_text = get_text(translations,
                                opt.get("text_key", opt.get("value", "")))
        else:
            opt_val = opt
            opt_text = get_text(translations, opt)
        choice_id = make_identifier("opt", opt_val)
        xml += (
            f'      <qti-inline-choice identifier="{choice_id}">'
            f'{escape_xml(opt_text)}</qti-inline-choice>\n'
        )
    xml += '    </qti-inline-choice-interaction></p>\n'
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_constant_sum_item(qid, text, question, definition, translations, scoring):
    """Build a constant-sum item using multiple text entries."""
    options = question.get("options", [])
    total = question.get("total", 100)

    xml = _xml_header(qid, strip_html(text)[:80])

    # One response declaration per option
    for i, opt in enumerate(options):
        resp_id = f"RESPONSE_{i}"
        xml += (
            f'  <qti-response-declaration identifier="{resp_id}" '
            f'cardinality="single" base-type="integer"/>\n'
        )

    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'
    xml += f'    <p><em>Allocate {total} points across the following:</em></p>\n'

    for i, opt in enumerate(options):
        if isinstance(opt, dict):
            opt_text = get_text(translations,
                                opt.get("text_key", opt.get("value", "")))
        else:
            opt_text = get_text(translations, opt)
        resp_id = f"RESPONSE_{i}"
        xml += (
            f'    <p>{escape_xml(opt_text)}: '
            f'<qti-text-entry-interaction response-identifier="{resp_id}" '
            f'expected-length="5"/></p>\n'
        )

    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_semantic_diff_item(qid, text, question, definition, translations, scoring):
    """Build a semantic differential as multiple choice interactions."""
    items = question.get("items", [])
    points = question.get("points", 7)

    xml = _xml_header(qid, strip_html(text)[:80])

    for i, item in enumerate(items):
        resp_id = f"RESPONSE_{i}"
        xml += (
            f'  <qti-response-declaration identifier="{resp_id}" '
            f'cardinality="single" base-type="identifier"/>\n'
        )

    xml += '  <qti-item-body>\n'
    xml += f'    {text_to_xhtml(text)}\n'

    for i, item in enumerate(items):
        left = get_text(translations, item.get("left_key", ""))
        right = get_text(translations, item.get("right_key", ""))
        resp_id = f"RESPONSE_{i}"

        xml += (
            f'    <p><em>{escape_xml(left)}</em> vs. '
            f'<em>{escape_xml(right)}</em></p>\n'
        )
        xml += (
            f'    <qti-choice-interaction response-identifier="{resp_id}" '
            f'shuffle="false" max-choices="1">\n'
        )
        for j in range(points):
            xml += (
                f'      <qti-simple-choice identifier="pt_{j+1}">'
                f'{j+1}</qti-simple-choice>\n'
            )
        xml += '    </qti-choice-interaction>\n'

    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_info_item(qid, text, question, definition, translations, scoring):
    """Build an information/instruction display item (no interaction)."""
    xml = _xml_header(qid, strip_html(text)[:40])
    xml += '  <qti-item-body>\n'
    xml += f'    <div class="instruction">\n'
    xml += f'      {text_to_xhtml(text)}\n'
    xml += f'    </div>\n'
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _build_image_item(qid, text, question, definition, translations, scoring):
    """Build an image display item."""
    img_file = question.get("image_file", "")

    xml = _xml_header(qid, strip_html(text)[:40])
    xml += '  <qti-item-body>\n'
    if img_file:
        xml += f'    <p><img src="{escape_xml(img_file)}" alt=""/></p>\n'
    xml += f'    {text_to_xhtml(text)}\n'
    xml += '  </qti-item-body>\n'
    xml += _xml_footer()
    return xml


def _get_correct_answers(qid, scoring):
    """Get correct answers for an item from scoring definitions."""
    for score_def in scoring.values():
        if not isinstance(score_def, dict):
            continue
        if score_def.get("method") == "sum_correct":
            correct = score_def.get("correct_answers", {})
            if qid in correct:
                return correct[qid]
    return None


# Map of question type to builder function
ITEM_BUILDERS = {
    "likert": _build_likert_item,
    "multi": _build_multi_item,
    "multicheck": _build_multicheck_item,
    "short": _build_short_item,
    "long": _build_long_item,
    "number": _build_short_item,
    "date": _build_short_item,
    "vas": _build_vas_item,
    "grid": _build_grid_item,
    "rank": _build_rank_item,
    "dropdown": _build_dropdown_item,
    "constant_sum": _build_constant_sum_item,
    "semantic_differential": _build_semantic_diff_item,
    "inst": _build_info_item,
    "image": _build_image_item,
    "imageresponse": _build_image_item,
}


# --- Package Builders ---

def build_manifest_xml(code, name, item_ids):
    """Build imsmanifest.xml for the content package."""
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += (
        f'<manifest xmlns="{CP_NS}"\n'
        f'    identifier="MANIFEST_{escape_xml(code)}">\n'
    )
    xml += '  <metadata>\n'
    xml += '    <schema>QTI Package</schema>\n'
    xml += '    <schemaversion>3.0</schemaversion>\n'
    xml += '  </metadata>\n'
    xml += '  <organizations/>\n'
    xml += '  <resources>\n'

    # Assessment test resource
    xml += (
        f'    <resource identifier="RES_test" '
        f'type="imsqti_test_xmlv3p0" href="assessment.xml">\n'
        f'      <file href="assessment.xml"/>\n'
    )
    for item_id in item_ids:
        xml += f'      <dependency identifierref="RES_{item_id}"/>\n'
    xml += '    </resource>\n'

    # Individual item resources
    for item_id in item_ids:
        xml += (
            f'    <resource identifier="RES_{item_id}" '
            f'type="imsqti_item_xmlv3p0" href="items/{item_id}.xml">\n'
            f'      <file href="items/{item_id}.xml"/>\n'
            f'    </resource>\n'
        )

    xml += '  </resources>\n'
    xml += '</manifest>\n'
    return xml


def build_assessment_xml(code, name, questions, pages=None):
    """Build assessment.xml test structure."""
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += (
        f'<qti-assessment-test xmlns="{QTI_NS}"\n'
        f'    identifier="TEST_{escape_xml(code)}"\n'
        f'    title="{escape_xml(name)}">\n'
    )
    xml += (
        f'  <qti-test-part identifier="PART_main" '
        f'navigation-mode="linear" submission-mode="simultaneous">\n'
    )

    if pages:
        for page in pages:
            page_id = page.get("id", "section")
            title = page.get("title_key", page_id)
            xml += (
                f'    <qti-assessment-section identifier="SEC_{page_id}" '
                f'title="{escape_xml(title)}" visible="true">\n'
            )
            for item_id in page.get("items", []):
                xml += (
                    f'      <qti-assessment-item-ref '
                    f'identifier="REF_{item_id}" '
                    f'href="items/{item_id}.xml"/>\n'
                )
            xml += '    </qti-assessment-section>\n'
    else:
        xml += (
            f'    <qti-assessment-section identifier="SEC_main" '
            f'title="{escape_xml(name)}" visible="true">\n'
        )
        for q in questions:
            qid = q["id"]
            xml += (
                f'      <qti-assessment-item-ref '
                f'identifier="REF_{qid}" '
                f'href="items/{qid}.xml"/>\n'
            )
        xml += '    </qti-assessment-section>\n'

    xml += '  </qti-test-part>\n'
    xml += '</qti-assessment-test>\n'
    return xml


def build_scoring_info(definition):
    """Build scoring_info.json with subscale definitions."""
    scoring = definition.get("scoring", {})
    dimensions = definition.get("dimensions", [])

    info = {
        "note": "QTI does not support aggregated scoring. "
                "This file documents the scoring rules for manual "
                "configuration in your LMS or analysis software.",
        "dimensions": dimensions,
        "scoring": scoring,
    }
    return json.dumps(info, indent=2, ensure_ascii=False)


def generate_qti_package(definition, translations):
    """Generate QTI 3.0 content package as bytes (ZIP)."""
    code = definition.get("scale_info", {}).get("code", "scale")
    name = definition.get("scale_info", {}).get("name", code)
    questions = definition.get("items") or definition.get("questions", [])
    scoring = definition.get("scoring", {})
    pages = definition.get("pages", None)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Build individual items
        item_ids = []
        for q in questions:
            qid = q["id"]
            item_ids.append(qid)
            item_xml = build_item_xml(q, definition, translations, scoring)
            zf.writestr(f"items/{qid}.xml", item_xml)

        # Manifest
        manifest_xml = build_manifest_xml(code, name, item_ids)
        zf.writestr("imsmanifest.xml", manifest_xml)

        # Assessment test
        assessment_xml = build_assessment_xml(code, name, questions, pages)
        zf.writestr("assessment.xml", assessment_xml)

        # Scoring info
        if scoring:
            scoring_json = build_scoring_info(definition)
            zf.writestr("scoring_info.json", scoring_json)

    return buf.getvalue()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert OSD format to QTI 3.0 content package"
    )
    parser.add_argument("scale_dir", help="Path to scale directory")
    parser.add_argument("--output", "-o",
                        help="Output ZIP file (default: {code}_qti.zip)")
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

    package_bytes = generate_qti_package(definition, translations)

    output_path = args.output or f"{code}_qti.zip"
    with open(output_path, "wb") as f:
        f.write(package_bytes)

    print(f"Written: {output_path}")

    # Summary
    questions = definition.get("items") or definition.get("questions", [])
    print(f"  {len(questions)} items")
    types = {}
    for q in questions:
        t = q.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    for t, count in sorted(types.items()):
        print(f"    {t}: {count}")


if __name__ == "__main__":
    main()
