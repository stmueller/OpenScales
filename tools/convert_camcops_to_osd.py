#!/usr/bin/env python3
"""Convert CamCOPS scale definitions (.py + .xml + .rst) to OSD format.

Parses CamCOPS Python server task files for scoring logic,
XML string files for item text, and RST docs for metadata/IP.
Produces a .osd JSON bundle for each scale.

Usage:
    python3 tools/convert_camcops_to_osd.py scales/camcops/gad7/
    python3 tools/convert_camcops_to_osd.py scales/camcops/   # all subdirs
"""

import ast
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_xml(xml_path):
    """Parse CamCOPS XML string file. Returns dict of name->text.
    Preserves inline HTML tags like <b>, <i>, <u> within string values."""
    strings = {}
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for task_el in root.findall('.//task'):
            for s in task_el.findall('string'):
                name = s.get('name', '')
                # Reconstruct inner content including inline HTML tags
                # ET.tostring gives the outer <string> tag too, so we strip it
                raw = ET.tostring(s, encoding='unicode', method='html')
                # Remove the outer <string ...> and </string> tags
                inner = re.sub(r'^<string[^>]*?>', '', raw)
                inner = re.sub(r'</string>\s*$', '', inner)
                text = inner.strip()
                if name:
                    strings[name] = text
    except Exception as e:
        print(f"  WARNING: XML parse error: {e}")
    return strings


def parse_rst(rst_path):
    """Parse CamCOPS RST doc for title, citation, IP rights, and scoring info."""
    info = {'title': '', 'ip_rights': '', 'citations': [], 'description_text': '',
            'subscale_info': ''}
    try:
        content = rst_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        # Title: line before --- or === underline
        for i, line in enumerate(lines):
            if i > 0 and re.match(r'^[-=]{3,}$', line.strip()):
                candidate = lines[i - 1].strip()
                if candidate and not candidate.startswith('..'):
                    info['title'] = candidate
                    break

        # Extract sections by header
        sections = {}
        current_section = None
        current_lines = []
        for i, line in enumerate(lines):
            if re.match(r'^~+$', line.strip()) and i > 0:
                header = lines[i - 1].strip()
                if current_section:
                    sections[current_section] = '\n'.join(current_lines).strip()
                current_section = header.lower()
                current_lines = []
            elif current_section:
                if re.match(r'^[-=]{3,}$', line.strip()) and i > 0:
                    # Hit a higher-level section, stop
                    sections[current_section] = '\n'.join(current_lines[:-1]).strip()
                    current_section = None
                    current_lines = []
                else:
                    current_lines.append(line)
        if current_section:
            sections[current_section] = '\n'.join(current_lines).strip()

        # IP rights section
        for key in ['intellectual property rights', 'intellectual property']:
            if key in sections:
                ip = sections[key]
                ip = re.sub(r'\.\. include::.*\n?', '', ip)
                ip = re.sub(r'\n\s*\n', ' | ', ip)
                ip = re.sub(r'\n', ' ', ip)
                ip = re.sub(r'\s+', ' ', ip).strip()
                info['ip_rights'] = ip
                break

        # Extract citations from History section
        # Look for author-year patterns like "Author et al. (YYYY)" or "Author (YYYY)"
        for key in ['history and guide', 'history', 'source']:
            if key not in sections:
                continue
            section_text = sections[key]
            # Match full citation lines: Author(s) (Year). Title. Journal...
            cite_matches = re.findall(
                r'[-*]?\s*([A-Z][a-zA-Z\s,&]+(?:et al\.?)?\s*\(\d{4}[a-z]?\)\.?\s*[^.]+\..+?)(?=\n\s*[-*]|\n\n|\Z)',
                section_text, re.DOTALL
            )
            for cite in cite_matches:
                cite_clean = re.sub(r'\s+', ' ', cite).strip()
                # Filter out non-citation lines
                if len(cite_clean) > 40 and re.search(r'\(\d{4}\)', cite_clean):
                    # Skip lines that are just URLs or notes
                    if not cite_clean.startswith('http') and 'First question' not in cite_clean:
                        info['citations'].append(cite_clean[:500])
            if info['citations']:
                break

        # Extract description text (between title and first section)
        desc_lines = []
        past_title = False
        for i, line in enumerate(lines):
            if re.match(r'^[-=]{3,}$', line.strip()) and i > 0:
                if not past_title:
                    past_title = True
                    continue
            if past_title:
                if re.match(r'^~+$', line.strip()):
                    break  # hit first subsection
                if not line.strip().startswith('..'):
                    desc_lines.append(line)
        desc_text = '\n'.join(desc_lines).strip()
        # Extract subscale info if present
        subscale_match = re.search(
            r'(?:areas|subscales|factors|dimensions):\s*\n((?:\s*[-*].*\n)+)',
            desc_text, re.IGNORECASE
        )
        if subscale_match:
            info['subscale_info'] = subscale_match.group(1).strip()
        info['description_text'] = re.sub(r'\s+', ' ', desc_text).strip()[:500]

    except Exception as e:
        print(f"  WARNING: RST parse error: {e}")
    return info


def parse_python(py_path):
    """Parse CamCOPS Python task file for scoring structure."""
    info = {
        'n_questions': None,
        'min_value': None,
        'max_value': None,
        'max_score': None,
        'reverse_scored': [],
        'agree_scored': [],
        'thresholds': [],
        'subscales': {},
        'comment_strings': [],
        'field_prefix': 'q',
        'shortname': '',
        'tablename': '',
    }

    try:
        content = py_path.read_text(encoding='utf-8')

        # N_QUESTIONS / NQUESTIONS
        m = re.search(r'N_?QUESTIONS\s*=\s*(\d+)', content)
        if m:
            info['n_questions'] = int(m.group(1))

        # Field prefix
        m = re.search(r'strseq\(\s*["\'](\w+)["\']', content)
        if m:
            info['field_prefix'] = m.group(1)

        # Response range from extend_columns
        m = re.search(r'minimum\s*=\s*(\d+)', content)
        if m:
            info['min_value'] = int(m.group(1))
        m = re.search(r'maximum\s*=\s*(\d+)', content)
        if m:
            info['max_value'] = int(m.group(1))

        # MAX_SCORE
        m = re.search(r'MAX_SCORE\s*=\s*(\d+)', content)
        if m:
            info['max_score'] = int(m.group(1))

        # Reverse scoring — multiple naming conventions
        # REVERSE_SCORED_QUESTIONS, REVERSE_SCORE, REVERSED_Q, Q_REVERSE_SCORED
        for pattern in [
            r'REVERSE_SCORED_QUESTIONS?\s*=\s*\[([^\]]*)\]',
            r'REVERSE_SCORE\s*=\s*\[([^\]]*)\]',
            r'REVERSED_Q\s*=\s*\[([^\]]*)\]',
            r'Q_REVERSE_SCORED\s*=\s*\[([^\]]*)\]',
        ]:
            m = re.search(pattern, content)
            if m:
                nums = re.findall(r'\d+', m.group(1))
                info['reverse_scored'] = [int(n) for n in nums]
                break

        # Agree scoring (items where "agree" scores the trait — e.g., AQ)
        m = re.search(r'AGREE_SCORING_QUESTIONS?\s*=\s*\[([^\]]*)\]', content, re.DOTALL)
        if m:
            nums = re.findall(r'\d+', m.group(1))
            info['agree_scored'] = [int(n) for n in nums]

        # Severity thresholds from severity() method or get_trackers
        threshold_patterns = [
            re.compile(r'score\s*>=\s*(\d+).*?(?:SS\.(\w+)|["\'](\w+)["\'])', re.DOTALL),
        ]
        for pat in threshold_patterns:
            for m in pat.finditer(content):
                val = int(m.group(1))
                label = m.group(2) or m.group(3)
                if label:
                    label = label.replace('_', ' ').title()
                    info['thresholds'].append((val, label))

        # comment_strings from extend_columns
        m = re.search(r'comment_strings\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if m:
            strings_text = m.group(1)
            info['comment_strings'] = re.findall(r'"([^"]*)"', strings_text)

        # shortname
        m = re.search(r'shortname\s*=\s*"([^"]*)"', content)
        if m:
            info['shortname'] = m.group(1)

        # tablename
        m = re.search(r'__tablename__\s*=\s*"([^"]*)"', content)
        if m:
            info['tablename'] = m.group(1)

        # ── Subscale extraction ──────────────────────────────────
        # 1. Named item lists: NAME_QUESTIONS = [1, 2, 3, ...]
        skip_names = {'TASK_FIELDS', 'SCORED_FIELDS', 'REQUIRED_FIELDS',
                       'AGREE_SCORING_QUESTIONS', 'REVERSE_SCORED_QUESTIONS',
                       'REVERSE_SCORE', 'REVERSED_Q', 'Q_REVERSE_SCORED',
                       'NA_QUESTIONS', 'SPECIAL_NA_TEXT_QUESTIONS',
                       'NO_SOMETIMES_QUESTIONS', 'SPECIAL_SEVERITY_QUESTIONS',
                       'SPECIAL_FREQUENCY_QUESTIONS', 'FREQUENCY_AS_PERCENT_QUESTIONS',
                       'ONE_TO_THREE'}
        for m in re.finditer(
            r'(\w+_(?:QUESTIONS|ITEMS|QS))\s*=\s*\[([^\]]+)\]',
            content
        ):
            name = m.group(1)
            if name in skip_names:
                continue
            nums = re.findall(r'\d+', m.group(2))
            if not nums or len(nums) < 2:
                continue
            prefix = info['field_prefix']
            items = [f"{prefix}{n}" for n in nums]
            # Clean up subscale name: SOCIAL_SKILL_QUESTIONS -> social_skill
            dim_id = name.lower()
            for suffix in ['_questions', '_items', '_qs']:
                dim_id = dim_id.replace(suffix, '')
            info['subscales'][dim_id] = {
                'name': dim_id.replace('_', ' ').title(),
                'items': items,
                'item_numbers': [int(n) for n in nums],
            }

        # 2. strseq subscale fields: NAME = strseq("q", start, end)
        for m in re.finditer(
            r'(\w+)\s*=\s*strseq\(\s*["\'](\w+)["\'],\s*(\d+),\s*(\d+)\)',
            content
        ):
            name = m.group(1)
            if name.upper() in skip_names or 'TASK' in name.upper():
                continue
            prefix = m.group(2)
            start = int(m.group(3))
            end = int(m.group(4))
            items = [f"{prefix}{i}" for i in range(start, end + 1)]
            dim_id = name.lower()
            for suffix in ['_fields', '_field_names']:
                dim_id = dim_id.replace(suffix, '')
            if dim_id and dim_id not in info['subscales']:
                info['subscales'][dim_id] = {
                    'name': dim_id.replace('_', ' ').title(),
                    'items': items,
                    'item_numbers': list(range(start, end + 1)),
                }

    except Exception as e:
        print(f"  WARNING: Python parse error: {e}")
    return info


def build_osd(code, xml_strings, py_info, rst_info):
    """Build an OSD JSON structure from parsed components."""

    n_questions = py_info['n_questions']
    if not n_questions:
        # Try to infer from XML
        q_keys = [k for k in xml_strings if re.match(r'^q\d+$', k)]
        n_questions = len(q_keys) if q_keys else 0

    if n_questions == 0:
        return None

    prefix = py_info['field_prefix']
    min_val = py_info['min_value'] if py_info['min_value'] is not None else 0
    max_val = py_info['max_value'] if py_info['max_value'] is not None else 3
    n_points = max_val - min_val + 1

    # Build translation strings
    translations = {}

    # Instruction/stem
    if 'instruction' in xml_strings:
        translations['inst'] = xml_strings['instruction']
    if 'stem' in xml_strings:
        translations['question_head'] = xml_strings['stem']
    elif 'title' in xml_strings:
        translations['question_head'] = xml_strings['title']

    # Response labels — try multiple CamCOPS naming conventions
    for i in range(min_val, max_val + 1):
        label_text = None
        for pattern in [f"a{i}", f"a{i - min_val}", f"option_{i}", f"option{i}",
                        f"answer{i}", f"opt{i}", f"response{i}"]:
            if pattern in xml_strings:
                label_text = xml_strings[pattern]
                break
        if label_text:
            translations[f"r{i}"] = label_text

    # Item text — try multiple CamCOPS naming conventions
    has_per_item_options = False
    for i in range(1, n_questions + 1):
        src_key = f"{prefix}{i}"
        text = None
        # Try: q1, q1_q, q1_question, q1_stem
        for candidate in [src_key, f"{src_key}_q", f"{src_key}_question", f"{src_key}_stem"]:
            if candidate in xml_strings:
                text = xml_strings[candidate]
                break
        if text:
            text = re.sub(r'^\d+[\.\)]\s*', '', text)
            translations[src_key] = text
        else:
            translations[src_key] = f"(Item {i} text not available)"

        # Check if this item has per-item response options (q1_a1, q1_a2, etc.)
        per_item_opts = {k: v for k, v in xml_strings.items()
                         if re.match(rf'^{re.escape(src_key)}_a\d+$', k)}
        if per_item_opts:
            has_per_item_options = True
            # Store per-item options in translations for reference
            for opt_key, opt_text in sorted(per_item_opts.items()):
                translations[opt_key] = opt_text

    translations['debrief'] = 'Thank you for completing this questionnaire.'

    # Build likert labels list
    likert_labels = []
    for i in range(n_points):
        likert_labels.append(f"r{min_val + i}")

    # Build items
    items = []
    if 'inst' in translations:
        items.append({
            "id": f"{code}_inst",
            "text_key": "inst",
            "type": "inst"
        })

    for i in range(1, n_questions + 1):
        item_id = f"{prefix}{i}"
        # Check if this item has per-item response options
        per_item_opts = sorted([k for k in translations if re.match(rf'^{re.escape(item_id)}_a\d+$', k)])
        if per_item_opts:
            # Build multi-choice item with per-item options
            options = []
            for opt_key in per_item_opts:
                # Extract value from key like q1_a3 -> 3
                val = int(re.search(r'_a(\d+)$', opt_key).group(1))
                options.append({"text_key": opt_key, "value": val})
            items.append({
                "id": item_id,
                "text_key": item_id,
                "type": "multi",
                "options": options,
            })
        else:
            items.append({
                "id": item_id,
                "text_key": item_id,
                "type": "likert"
            })

    # Build scoring
    reverse = set(py_info['reverse_scored'])
    agree = set(py_info.get('agree_scored', []))
    all_items = [f"{prefix}{i}" for i in range(1, n_questions + 1)]

    # Determine item coding
    # Three cases:
    # 1. reverse_scored defined: those items get -1, rest get 1
    # 2. agree_scored defined: items NOT in agree get -1 (disagree = forward for those)
    # 3. Neither: all items get 1
    item_coding = {}
    if agree:
        # agree_scored means "agree" scores the trait for those items
        # Items NOT in agree need reverse coding (disagree = trait)
        for i in range(1, n_questions + 1):
            item_id = f"{prefix}{i}"
            item_coding[item_id] = 1 if i in agree else -1
    elif reverse:
        for i in range(1, n_questions + 1):
            item_id = f"{prefix}{i}"
            item_coding[item_id] = -1 if i in reverse else 1
    else:
        for i in range(1, n_questions + 1):
            item_id = f"{prefix}{i}"
            item_coding[item_id] = 1

    scoring = {
        "total": {
            "method": "sum_coded",
            "items": all_items,
            "description": f"Sum of all {n_questions} items.",
            "item_coding": item_coding,
        }
    }

    # Add notes about scoring direction
    if agree:
        disagree_items = sorted(set(range(1, n_questions + 1)) - agree)
        scoring["total"]["description"] += (
            f" 'Agree' scores trait for items {sorted(agree)}; "
            f"'disagree' scores trait for items {disagree_items} (reverse-coded)."
        )

    # Add norms from thresholds
    if py_info['thresholds']:
        max_possible = py_info['max_score'] or (max_val * n_questions)
        boundaries = sorted(py_info['thresholds'], key=lambda x: x[0])
        if boundaries:
            norms = []
            norms.append({
                "min": 0,
                "max": boundaries[0][0] - 1,
                "label": "Below threshold"
            })
            for idx, (val, label) in enumerate(boundaries):
                next_val = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else max_possible + 1
                norms.append({
                    "min": val,
                    "max": next_val - 1,
                    "label": label
                })
            scoring["total"]["norms"] = {"thresholds": norms}

    # Add subscale scoring from Python-extracted subscales
    if py_info['subscales']:
        for dim_id, sub_info in py_info['subscales'].items():
            sub_items = sub_info['items']
            sub_item_nums = sub_info.get('item_numbers', [])
            sub_name = sub_info.get('name', dim_id.replace('_', ' ').title())

            # Try to find a better name from the XML (e.g., "social_skill_score" key)
            xml_name_key = f"{dim_id}_score"
            xml_alt_key = f"{dim_id.replace('_', '')}_score"
            if xml_name_key in xml_strings:
                sub_name = xml_strings[xml_name_key]
            elif xml_alt_key in xml_strings:
                sub_name = xml_strings[xml_alt_key]

            # Build item coding for subscale — same logic as total
            sub_coding = {}
            for item in sub_items:
                item_num = int(re.search(r'\d+', item).group())
                if agree:
                    sub_coding[item] = 1 if item_num in agree else -1
                elif reverse:
                    sub_coding[item] = -1 if item_num in reverse else 1
                else:
                    sub_coding[item] = 1

            scoring[dim_id] = {
                "method": "sum_coded",
                "items": sub_items,
                "item_coding": sub_coding,
                "description": f"{sub_name} ({len(sub_items)} items: {', '.join(str(n) for n in sub_item_nums)})"
            }

    # Build dimensions
    dimensions = []
    for dim_id, score_def in scoring.items():
        if dim_id == 'total':
            dim_name = 'Total'
        elif dim_id in py_info.get('subscales', {}):
            sub_info = py_info['subscales'][dim_id]
            dim_name = sub_info.get('name', dim_id.replace('_', ' ').title())
            # Check XML for a nicer name
            for xml_key in [f"{dim_id}_score", f"{dim_id.replace('_', '')}_score"]:
                if xml_key in xml_strings:
                    dim_name = xml_strings[xml_key]
                    break
        else:
            dim_name = dim_id.replace('_', ' ').title()
        dimensions.append({
            "id": dim_id,
            "name": dim_name,
            "description": score_def.get('description', ''),
        })

    # Determine license from RST
    ip = rst_info.get('ip_rights', '').lower()
    if 'public domain' in ip:
        license_val = 'Public Domain'
    elif 'creative commons' in ip or 'cc by' in ip:
        license_val = 'CC BY'
    elif 'free to use' in ip or 'free to reproduce' in ip:
        license_val = 'free for research use'
    elif 'permission' in ip:
        license_val = 'seek author permission'
    else:
        license_val = 'unknown'

    # Citation
    citation = ''
    if rst_info.get('citations'):
        citation = rst_info['citations'][0]

    title = rst_info.get('title', '') or py_info.get('shortname', '') or code.upper()

    # Build description from RST or fallback
    description = rst_info.get('description_text', '')
    if not description or len(description) < 20:
        description = f"{n_questions}-item scale."
    description += " Auto-converted from CamCOPS; requires manual review."

    # Assemble OSD
    osd = {
        "osd_version": "1.0",
        "definition": {
            "scale_info": {
                "name": title,
                "code": code.upper(),
                "abbreviation": py_info.get('shortname', '') or code.upper(),
                "description": description[:500],
                "citation": citation,
                "license": license_val,
                "license_explanation": f"CamCOPS IP notes: {rst_info.get('ip_rights', 'Not documented')[:300]}",
                "version": "1.0",
                "url": ""
            },
            "likert_options": {
                "points": n_points,
                "min": min_val,
                "max": max_val,
                "labels": likert_labels,
            },
            "dimensions": dimensions,
            "items": items,
            "scoring": scoring,
        },
        "translations": {
            "en": translations
        },
        "_camcops_conversion": {
            "source": "CamCOPS (https://github.com/ucam-department-of-psychiatry/camcops)",
            "status": "auto-converted — requires manual review",
            "reverse_scored_items": list(reverse),
            "n_questions": n_questions,
            "response_range": [min_val, max_val],
        }
    }

    # Add question_head to likert_options if available
    if 'question_head' in translations:
        osd['definition']['likert_options']['question_head'] = 'question_head'

    return osd


def convert_scale(scale_dir):
    """Convert a single CamCOPS scale directory to OSD."""
    scale_dir = Path(scale_dir)
    code = scale_dir.name

    print(f"\nConverting: {code}")

    # Find files — try exact case first, then lowercase
    code_lower = code.lower()
    xml_path = scale_dir / f"{code}.xml"
    if not xml_path.exists():
        xml_path = scale_dir / f"{code_lower}.xml"
    rst_path = scale_dir / f"{code}.rst"
    if not rst_path.exists():
        rst_path = scale_dir / f"{code_lower}.rst"
    py_path = scale_dir / f"{code}.py"
    if not py_path.exists():
        py_path = scale_dir / f"{code_lower}.py"

    # Parse XML
    xml_strings = {}
    if xml_path.exists():
        xml_strings = parse_xml(xml_path)
        print(f"  XML: {len(xml_strings)} strings")
    else:
        print(f"  XML: not found")

    # Parse RST
    rst_info = {'title': '', 'ip_rights': '', 'citations': []}
    if rst_path.exists():
        rst_info = parse_rst(rst_path)
        print(f"  RST: title='{rst_info['title'][:50]}', IP={'yes' if rst_info['ip_rights'] else 'no'}")

    # Parse Python
    py_info = {
        'n_questions': None, 'min_value': None, 'max_value': None,
        'max_score': None, 'reverse_scored': [], 'thresholds': [],
        'subscales': {}, 'comment_strings': [], 'field_prefix': 'q',
        'shortname': '', 'tablename': '',
    }
    if py_path.exists():
        py_info = parse_python(py_path)
        print(f"  PY:  n_q={py_info['n_questions']}, range={py_info['min_value']}-{py_info['max_value']}, "
              f"reverse={py_info['reverse_scored']}, thresholds={len(py_info['thresholds'])}")
    else:
        print(f"  PY:  not found")

    if not xml_strings and not py_info['n_questions']:
        print(f"  SKIP: insufficient data")
        return False

    # Build OSD
    osd = build_osd(code, xml_strings, py_info, rst_info)
    if not osd:
        print(f"  SKIP: could not determine item count")
        return False

    # Write OSD
    out_path = scale_dir / f"{code}.osd"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(osd, f, indent=2, ensure_ascii=False)

    n_items = len([i for i in osd['definition']['items'] if i['type'] != 'inst'])
    n_trans = len(osd['translations']['en'])
    print(f"  WROTE: {out_path.name} ({n_items} items, {n_trans} translations, license={osd['definition']['scale_info']['license']})")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 convert_camcops_to_osd.py <scale_dir_or_parent>")
        sys.exit(1)

    target = Path(sys.argv[1])

    if (target / f"{target.name}.py").exists() or (target / f"{target.name}.xml").exists():
        # Single scale directory
        convert_scale(target)
    else:
        # Parent directory — convert all subdirectories
        converted = 0
        skipped = 0
        for subdir in sorted(target.iterdir()):
            if not subdir.is_dir():
                continue
            if subdir.name.startswith('.') or subdir.name.startswith('_'):
                continue
            # Check it has at least one source file
            has_source = any(
                (subdir / f"{subdir.name}{ext}").exists()
                for ext in ['.py', '.xml', '.rst']
            )
            if has_source:
                if convert_scale(subdir):
                    converted += 1
                else:
                    skipped += 1

        print(f"\n{'=' * 60}")
        print(f"Converted: {converted}")
        print(f"Skipped:   {skipped}")
        print(f"Total:     {converted + skipped}")


if __name__ == '__main__':
    main()
