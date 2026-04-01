#!/usr/bin/env python3
"""
osd2surveydown.py — Convert an OpenScales .osd file to surveydown format.

Generates:
  - questions.yml  — All questions in surveydown YAML format
  - survey.qmd     — Quarto document referencing the questions
  - app.R          — Minimal Shiny app with database config stub

Usage:
  python3 osd2surveydown.py path/to/SCALE.osd [--lang en] [--outdir output/]
"""

import json
import sys
import os
import argparse
import textwrap


def load_osd(filepath):
    """Load and parse an .osd file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def resolve_text(key, translations):
    """Look up a text_key in the translations dict."""
    return translations.get(key, key)


def yaml_escape(text):
    """Escape text for YAML value. Use quoted scalar if needed."""
    if not text:
        return '""'
    # If text contains special chars, quote it
    if any(c in text for c in [':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`', '"', "'"]):
        # Use double quotes with escaped internal quotes
        escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'
    if '\n' in text:
        escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'
    return text


def convert_likert(item, defn, translations):
    """Convert a likert item to surveydown mc_buttons question."""
    likert_opts = defn.get('likert_options', {})

    # Get item-level overrides
    points = item.get('likert_points', likert_opts.get('points', 5))
    min_val = item.get('likert_min', likert_opts.get('min', 1))
    max_val = item.get('likert_max', likert_opts.get('max', points))
    labels = item.get('likert_labels', likert_opts.get('labels', []))

    # Build question text
    text = resolve_text(item.get('text_key', item['id']), translations)

    # Add question_head if present
    qhead_key = item.get('question_head', likert_opts.get('question_head', ''))
    if qhead_key:
        qhead = resolve_text(qhead_key, translations)
        if qhead:
            text = qhead + "\n\n" + text

    # Build options: label text -> numeric value
    options = {}
    for i, val in enumerate(range(min_val, max_val + 1)):
        if i < len(labels):
            label_text = resolve_text(labels[i], translations)
        else:
            label_text = str(val)
        options[label_text] = str(val)

    return {
        'type': 'mc',
        'label': text,
        'options': options,
    }


def convert_vas(item, defn, translations):
    """Convert a VAS item to surveydown slider_numeric."""
    text = resolve_text(item.get('text_key', item['id']), translations)

    min_val = item.get('min', 0)
    max_val = item.get('max', 100)
    min_label = resolve_text(item.get('min_label', ''), translations)
    max_label = resolve_text(item.get('max_label', ''), translations)

    label = text
    if min_label and max_label:
        label += f"\n\n({min_label} — {max_label})"

    # Use categorical slider with all values as options
    # This gives a continuous-feeling slider with labeled endpoints
    step = item.get('step', 1)
    options = {}
    for v in range(min_val, max_val + 1, step):
        if v == min_val and min_label:
            options[min_label] = str(v)
        elif v == max_val and max_label:
            options[max_label] = str(v)
        else:
            options[str(v)] = str(v)

    result = {
        'type': 'slider',
        'label': text,
        'options': options,
    }
    return result


def convert_multi(item, defn, translations):
    """Convert a multi (single-select) item to surveydown mc."""
    text = resolve_text(item.get('text_key', item['id']), translations)

    options = {}
    for opt in item.get('options', []):
        if isinstance(opt, dict):
            opt_text = resolve_text(opt.get('text_key', opt.get('value', '')), translations)
            opt_val = str(opt.get('value', ''))
        else:
            opt_text = resolve_text(str(opt), translations)
            opt_val = str(opt)
        options[opt_text] = opt_val

    return {
        'type': 'mc',
        'label': text,
        'options': options,
    }


def convert_multicheck(item, defn, translations):
    """Convert a multicheck item to surveydown mc_multiple."""
    result = convert_multi(item, defn, translations)
    result['type'] = 'mc_multiple'
    return result


def convert_short(item, defn, translations):
    """Convert a short text item to surveydown text."""
    text = resolve_text(item.get('text_key', item['id']), translations)
    result = {
        'type': 'text',
        'label': text,
    }
    if item.get('maxlength'):
        result['placeholder'] = f"Max {item['maxlength']} characters"
    return result


def convert_long(item, defn, translations):
    """Convert a long text item to surveydown textarea."""
    text = resolve_text(item.get('text_key', item['id']), translations)
    return {
        'type': 'textarea',
        'label': text,
    }


def convert_grid(item, defn, translations):
    """Convert a grid item to surveydown matrix."""
    text = resolve_text(item.get('text_key', item['id']), translations)

    # Grid rows are sub-items (can be dicts or strings)
    rows = {}
    for row in item.get('rows', []):
        if isinstance(row, dict):
            row_text = resolve_text(row.get('text_key', row.get('id', '')), translations)
            row_id = row.get('id', '')
        else:
            row_text = resolve_text(str(row), translations)
            row_id = str(row)
        rows[row_text] = row_id

    # Grid columns are options (can be dicts or strings)
    options = {}
    for col in item.get('columns', []):
        if isinstance(col, dict):
            col_text = resolve_text(col.get('text_key', col.get('label', '')), translations)
            col_val = str(col.get('value', ''))
        else:
            col_text = resolve_text(str(col), translations)
            col_val = str(col)
        options[col_text] = col_val

    return {
        'type': 'matrix',
        'label': text,
        'row': rows,
        'options': options,
    }


CONVERTERS = {
    'likert': convert_likert,
    'vas': convert_vas,
    'multi': convert_multi,
    'multicheck': convert_multicheck,
    'short': convert_short,
    'long': convert_long,
    'grid': convert_grid,
}


def write_yaml_value(f, key, value, indent=2):
    """Write a YAML key-value pair with proper formatting."""
    prefix = ' ' * indent
    if isinstance(value, dict):
        f.write(f"{prefix}{key}:\n")
        for k, v in value.items():
            f.write(f"{prefix}  {yaml_escape(k)}: {yaml_escape(str(v))}\n")
    elif isinstance(value, bool):
        f.write(f"{prefix}{key}: {'true' if value else 'false'}\n")
    elif isinstance(value, (int, float)):
        f.write(f"{prefix}{key}: {value}\n")
    else:
        f.write(f"{prefix}{key}: {yaml_escape(str(value))}\n")


def generate_questions_yml(osd_data, lang='en'):
    """Generate questions.yml content from OSD data."""
    defn = osd_data['definition']
    translations = osd_data.get('translations', {}).get(lang, {})
    items = defn.get('items', [])

    lines = []
    lines.append(f"# Auto-generated from {defn.get('scale_info', {}).get('code', 'unknown')}.osd")
    lines.append(f"# Language: {lang}")
    lines.append("")

    for item in items:
        item_type = item.get('type', '')
        item_id = item.get('id', '')

        # Skip sections and instructions — handled in survey.qmd
        if item_type in ('section', 'inst'):
            continue

        converter = CONVERTERS.get(item_type)
        if not converter:
            lines.append(f"# SKIPPED: {item_id} (unsupported type: {item_type})")
            lines.append("")
            continue

        sd_question = converter(item, defn, translations)

        lines.append(f"{item_id}:")
        for key, value in sd_question.items():
            if isinstance(value, dict):
                lines.append(f"  {key}:")
                for k, v in value.items():
                    lines.append(f"    {yaml_escape(k)}: {yaml_escape(str(v))}")
            elif isinstance(value, bool):
                lines.append(f"  {key}: {'true' if value else 'false'}")
            elif isinstance(value, (int, float)):
                lines.append(f"  {key}: {value}")
            else:
                lines.append(f"  {key}: {yaml_escape(str(value))}")

        if item.get('required'):
            lines.append("  required: true")

        lines.append("")

    return '\n'.join(lines)


def generate_survey_qmd(osd_data, lang='en'):
    """Generate survey.qmd content from OSD data."""
    defn = osd_data['definition']
    translations = osd_data.get('translations', {}).get(lang, {})
    scale_info = defn.get('scale_info', {})
    items = defn.get('items', [])

    lines = []
    # YAML header
    lines.append("---")
    lines.append("format: html")
    lines.append("echo: false")
    lines.append("warning: false")
    lines.append("---")
    lines.append("")
    lines.append("```{r}")
    lines.append("library(surveydown)")
    lines.append("```")
    lines.append("")

    # Track current page
    page_num = 1
    in_page = False

    for item in items:
        item_type = item.get('type', '')
        item_id = item.get('id', '')

        if item_type == 'section':
            # Close previous page if open
            if in_page:
                lines.append(":::")
                lines.append("")
            # New page
            section_title = resolve_text(item.get('text_key', ''), translations)
            lines.append(f"::: {{#page{page_num} .sd-page}}")
            lines.append("")
            if section_title:
                lines.append(f"## {section_title}")
                lines.append("")
            in_page = True
            page_num += 1

        elif item_type == 'inst':
            # Instruction text — render as markdown
            if not in_page:
                lines.append(f"::: {{#page{page_num} .sd-page}}")
                lines.append("")
                in_page = True
                page_num += 1
            inst_text = resolve_text(item.get('text_key', ''), translations)
            if inst_text:
                lines.append(inst_text)
                lines.append("")

        else:
            # Question — reference from YAML
            if not in_page:
                lines.append(f"::: {{#page{page_num} .sd-page}}")
                lines.append("")
                in_page = True
                page_num += 1

            lines.append("```{r}")
            lines.append(f'sd_question("{item_id}")')
            lines.append("```")
            lines.append("")

    # Close last page if open
    if in_page:
        lines.append(":::")
        lines.append("")

    # Add closing page
    lines.append(f"::: {{#end .sd-page}}")
    lines.append("")
    lines.append(f"## {scale_info.get('name', 'Survey')} Complete")
    lines.append("")
    lines.append("Thank you for completing this survey.")
    lines.append("")
    lines.append("```{r}")
    lines.append("sd_close()")
    lines.append("```")
    lines.append(":::")
    lines.append("")

    return '\n'.join(lines)


def generate_app_r(osd_data):
    """Generate app.R content."""
    scale_info = osd_data['definition'].get('scale_info', {})
    code = scale_info.get('code', 'survey')

    return textwrap.dedent(f"""\
    # app.R — {scale_info.get('name', 'Survey')}
    # Auto-generated from {code}.osd by osd2surveydown.py

    library(surveydown)

    # Database connection
    # For local testing, use ignore = TRUE (saves to local CSV)
    # For production, fill in your database credentials
    db <- sd_db_connect(ignore = TRUE)

    # Server configuration
    server <- function(input, output, session) {{

      # Define conditional display / skip logic here if needed
      # sd_show_if(condition, "question_id")
      # sd_skip_if(condition, "page_id")

      sd_server(db = db)
    }}

    # Run the app
    shiny::shinyApp(ui = sd_ui(), server = server)
    """)


def main():
    parser = argparse.ArgumentParser(
        description='Convert OpenScales .osd to surveydown format')
    parser.add_argument('osd_file', help='Path to .osd file')
    parser.add_argument('--lang', default='en', help='Language code (default: en)')
    parser.add_argument('--outdir', default=None,
                        help='Output directory (default: same name as scale code)')
    args = parser.parse_args()

    # Load OSD
    osd_data = load_osd(args.osd_file)
    defn = osd_data['definition']
    scale_info = defn.get('scale_info', {})
    code = scale_info.get('code', 'survey')

    # Check translations exist
    translations = osd_data.get('translations', {})
    if args.lang not in translations:
        available = list(translations.keys())
        print(f"Warning: language '{args.lang}' not found. Available: {available}")
        if available:
            args.lang = available[0]
            print(f"Using '{args.lang}' instead.")
        else:
            print("Error: no translations found in .osd file.")
            sys.exit(1)

    # Determine output directory
    outdir = args.outdir or f"surveydown-{code}"
    os.makedirs(outdir, exist_ok=True)

    # Generate files
    questions_yml = generate_questions_yml(osd_data, args.lang)
    survey_qmd = generate_survey_qmd(osd_data, args.lang)
    app_r = generate_app_r(osd_data)

    # Write files
    with open(os.path.join(outdir, 'questions.yml'), 'w', encoding='utf-8') as f:
        f.write(questions_yml)
    print(f"  Written: {outdir}/questions.yml")

    with open(os.path.join(outdir, 'survey.qmd'), 'w', encoding='utf-8') as f:
        f.write(survey_qmd)
    print(f"  Written: {outdir}/survey.qmd")

    with open(os.path.join(outdir, 'app.R'), 'w', encoding='utf-8') as f:
        f.write(app_r)
    print(f"  Written: {outdir}/app.R")

    # Summary
    items = defn.get('items', [])
    n_questions = sum(1 for i in items if i.get('type') not in ('section', 'inst'))
    n_sections = sum(1 for i in items if i.get('type') == 'section')
    types_used = set(i.get('type') for i in items)

    print(f"\nConverted {code}: {n_questions} questions, {n_sections} sections")
    print(f"  Item types: {', '.join(sorted(types_used))}")
    print(f"  Scale: {scale_info.get('name', '?')}")
    print(f"  Language: {args.lang}")


if __name__ == '__main__':
    main()
