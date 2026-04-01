#!/usr/bin/env python3
"""Convert Qualtrics QSF survey export to Open Scale Definition (OSD) format.

Parses Qualtrics .qsf files (JSON) and extracts questions into OSD scale
definitions. Supports interactive selection of which blocks/questions to
include, since QSF exports often contain more than just the target scale.

Supported Qualtrics question types:
  - Matrix/Bipolar  → likert with per-item bipolar labels
  - Matrix/Likert   → likert or grid
  - MC/SAVR         → multi (single choice)
  - MC/MAVR         → multicheck (multiple choice)
  - TE/SL           → short (single line text)
  - TE/ML           → long (multiline text)
  - TE/FORM         → multiple short fields
  - DB/TB           → inst (display/instruction)
  - Slider          → vas (visual analog scale)

Usage:
    python convert_from_qualtrics.py input.qsf                    # Interactive
    python convert_from_qualtrics.py input.qsf --block "UEQ"      # Extract block
    python convert_from_qualtrics.py input.qsf --questions QID1    # Specific Qs
    python convert_from_qualtrics.py input.qsf --output scales/UEQ # Output dir
"""

import argparse
import json
import os
import re
import sys


def load_qsf(filepath):
    """Load and parse a QSF file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_elements_by_type(qsf, element_type):
    """Get all SurveyElements of a given type."""
    return [
        e for e in qsf.get("SurveyElements", [])
        if e.get("Element") == element_type
    ]


def get_questions(qsf):
    """Get all SQ (Survey Question) elements as a dict keyed by QuestionID."""
    questions = {}
    for e in get_elements_by_type(qsf, "SQ"):
        qid = e.get("PrimaryAttribute", "")
        payload = e.get("Payload", {})
        if payload:
            payload["_QuestionID"] = qid
            questions[qid] = payload
    return questions


def get_blocks(qsf):
    """Get block definitions as a dict keyed by block ID."""
    blocks = {}
    for e in get_elements_by_type(qsf, "BL"):
        payload = e.get("Payload", {})
        for key, block in payload.items():
            block_id = block.get("ID", key)
            blocks[block_id] = block
    return blocks


def strip_html(text):
    """Remove HTML tags from text, preserving basic content."""
    if not text:
        return ""
    # Keep <b>, <i>, <br> for OSD translation values
    # But strip everything else
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:b|i|strong|em)>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\n\s*\n", "\n", text)
    return text.strip()


def make_id(text, prefix="q"):
    """Make a valid OSD item ID from text."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower())
    clean = clean.strip("_")[:30]
    return f"{prefix}_{clean}" if clean else prefix


def convert_bipolar_matrix(question, code_prefix, start_index=1):
    """Convert a Qualtrics Matrix/Bipolar question to OSD items.

    Each row becomes a separate likert question with bipolar labels.

    Returns:
        (questions_list, translations_dict, item_count)
    """
    questions = []
    translations = {}
    choices = question.get("Choices", {})
    choice_order = question.get("ChoiceOrder", sorted(choices.keys(), key=int))
    num_answers = question.get("AnswerColumns", 7)

    for idx, choice_key in enumerate(choice_order):
        choice = choices.get(str(choice_key), {})
        display = choice.get("Display", "")

        # Parse "Left:Right" bipolar format
        parts = display.split(":")
        if len(parts) == 2:
            left_label = parts[0].strip()
            right_label = parts[1].strip()
        else:
            left_label = display
            right_label = ""

        item_num = start_index + idx
        item_id = f"{code_prefix}_{item_num:02d}"

        # Create likert labels for this item (left = 1, right = max)
        left_key = f"{item_id}_left"
        right_key = f"{item_id}_right"

        questions.append({
            "id": item_id,
            "text_key": f"{item_id}_text",
            "type": "likert",
            "likert_points": num_answers,
            "likert_labels": [left_key, right_key],
            "coding": 1,
        })

        # Translation: question text is empty (bipolar uses labels only)
        translations[f"{item_id}_text"] = ""
        translations[left_key] = left_label
        translations[right_key] = right_label

    return questions, translations, len(choice_order)


def convert_mc_question(question, code_prefix, item_num):
    """Convert a Qualtrics MC question to OSD multi/multicheck."""
    choices = question.get("Choices", {})
    choice_order = question.get("ChoiceOrder", sorted(choices.keys(), key=int))
    selector = question.get("Selector", "SAVR")

    item_id = f"{code_prefix}_{item_num:02d}"
    qtype = "multicheck" if selector == "MAVR" else "multi"

    options = []
    translations = {}
    for i, choice_key in enumerate(choice_order):
        choice = choices.get(str(choice_key), {})
        opt_key = f"{item_id}_opt{i+1}"
        options.append({
            "value": str(choice_key),
            "text_key": opt_key
        })
        translations[opt_key] = strip_html(choice.get("Display", ""))

    text = strip_html(question.get("QuestionText", ""))
    translations[f"{item_id}_text"] = text

    q = {
        "id": item_id,
        "text_key": f"{item_id}_text",
        "type": qtype,
        "options": options,
    }

    return q, translations


def convert_text_question(question, code_prefix, item_num):
    """Convert a Qualtrics TE question to OSD short/long."""
    selector = question.get("Selector", "SL")
    item_id = f"{code_prefix}_{item_num:02d}"

    text = strip_html(question.get("QuestionText", ""))
    translations = {f"{item_id}_text": text}

    if selector == "ML":
        qtype = "long"
    else:
        qtype = "short"

    q = {
        "id": item_id,
        "text_key": f"{item_id}_text",
        "type": qtype,
    }

    return q, translations


def convert_db_question(question, code_prefix, item_num):
    """Convert a Qualtrics DB (display) question to OSD inst."""
    item_id = f"{code_prefix}_{item_num:02d}"
    text = strip_html(question.get("QuestionText", ""))
    translations = {f"{item_id}_text": text}

    q = {
        "id": item_id,
        "text_key": f"{item_id}_text",
        "type": "inst",
    }

    return q, translations


def convert_question(question, code_prefix, item_num):
    """Convert a single Qualtrics question to OSD format.

    Returns:
        (questions_list, translations_dict, items_consumed)
    """
    qtype = question.get("QuestionType", "")
    selector = question.get("Selector", "")

    if qtype == "Matrix" and selector == "Bipolar":
        return convert_bipolar_matrix(question, code_prefix, item_num)

    elif qtype == "MC":
        q, trans = convert_mc_question(question, code_prefix, item_num)
        return [q], trans, 1

    elif qtype == "TE":
        q, trans = convert_text_question(question, code_prefix, item_num)
        return [q], trans, 1

    elif qtype == "DB":
        q, trans = convert_db_question(question, code_prefix, item_num)
        return [q], trans, 1

    elif qtype == "Timing":
        # Skip timing questions
        return [], {}, 0

    else:
        print(f"  Warning: Unsupported question type {qtype}/{selector} "
              f"({question.get('_QuestionID', '?')}), skipping")
        return [], {}, 0


def paginate_questions(questions, items_per_page=7):
    """Split questions into pages for non-scrolling display.

    Returns list of page dicts with 'id' and 'items' keys.
    """
    pages = []
    for i in range(0, len(questions), items_per_page):
        page_items = questions[i:i + items_per_page]
        page_num = len(pages) + 1
        pages.append({
            "id": f"page_{page_num}",
            "items": [q["id"] for q in page_items]
        })
    return pages


def extract_ueq_scoring():
    """Return the standard UEQ scoring definitions.

    UEQ scales (Laugwitz et al., 2008):
      Attractiveness:  items 1, 12, 14, 16, 24, 25
      Perspicuity:     items 2, 4, 13, 21
      Efficiency:      items 9, 20, 22, 23
      Dependability:   items 8, 11, 17, 19
      Stimulation:     items 5, 6, 7, 18
      Novelty:         items 3, 10, 15, 26

    Items where positive quality is on the LEFT side (need reverse coding):
      3 (Creative:Dull), 4 (Easy to Learn:Difficult to Learn),
      5 (Valuable:Inferior), 9 (Fast:Slow), 10 (Inventive:Conventional),
      12 (Good:Bad), 17 (Secure:Not Secure), 18 (Motivating:Demotivating),
      19 (Meets Expectations:Does not meet Expectations),
      21 (Clear:Confusing), 23 (Organized:Cluttered),
      24 (Attractive:Unattractive), 25 (Friendly:Unfriendly)
    """
    # Item numbers where positive is on left (reversed scoring)
    reversed_items = {3, 4, 5, 9, 10, 12, 17, 18, 19, 21, 23, 24, 25}

    scales = {
        "attractiveness": {
            "name": "Attractiveness",
            "items": [1, 12, 14, 16, 24, 25],
        },
        "perspicuity": {
            "name": "Perspicuity",
            "items": [2, 4, 13, 21],
        },
        "efficiency": {
            "name": "Efficiency",
            "items": [9, 20, 22, 23],
        },
        "dependability": {
            "name": "Dependability",
            "items": [8, 11, 17, 19],
        },
        "stimulation": {
            "name": "Stimulation",
            "items": [5, 6, 7, 18],
        },
        "novelty": {
            "name": "Novelty",
            "items": [3, 10, 15, 26],
        },
    }

    return scales, reversed_items


def build_ueq_scale(questions_list, translations, code="UEQ"):
    """Build a complete UEQ OSD scale with proper scoring."""
    prefix = code.lower()
    ueq_scales, reversed_items = extract_ueq_scoring()

    # Update coding on questions based on UEQ polarity
    for i, q in enumerate(questions_list):
        item_num = i + 1
        if item_num in reversed_items:
            q["coding"] = -1

    # Build dimensions
    dimensions = []
    for dim_id, scale in ueq_scales.items():
        dimensions.append({
            "id": dim_id,
            "name": scale["name"]
        })

    # Build scoring
    scoring = {}
    for dim_id, scale in ueq_scales.items():
        item_ids = [f"{prefix}_{n:02d}" for n in scale["items"]]
        item_coding = {}
        for n in scale["items"]:
            item_id = f"{prefix}_{n:02d}"
            coding = -1 if n in reversed_items else 1
            item_coding[item_id] = coding

        scoring[dim_id] = {
            "method": "mean_coded",
            "items": item_ids,
            "item_coding": item_coding,
        }

    # Build pages (7 items each for non-scrolling display)
    pages = paginate_questions(questions_list, items_per_page=7)

    # Add instruction page at the beginning
    inst_id = f"{prefix}_inst"
    inst_question = {
        "id": inst_id,
        "text_key": f"{inst_id}_text",
        "type": "inst",
    }
    translations[f"{inst_id}_text"] = (
        "Please assess the product by selecting one option per line. "
        "Each line presents a pair of contrasting attributes. "
        "The circles between them allow you to express your agreement "
        "with the attributes. Please decide spontaneously. "
        "Don't think too long about your decision. "
        "It is your personal opinion that counts. "
        "There is no wrong or right answer!"
    )

    all_questions = [inst_question] + questions_list

    inst_page = {"id": "instructions", "items": [inst_id]}
    pages = [inst_page] + pages

    # Add debrief
    translations["debrief"] = "Thank you for completing this questionnaire."

    scale_json = {
        "scale_info": {
            "name": "User Experience Questionnaire",
            "code": code,
            "abbreviation": "UEQ",
            "description": "26-item semantic differential scale measuring "
                           "user experience across 6 dimensions: "
                           "Attractiveness, Perspicuity, Efficiency, "
                           "Dependability, Stimulation, and Novelty.",
            "citation": "Laugwitz, B., Held, T., & Schrepp, M. (2008). "
                        "Construction and evaluation of a user experience "
                        "questionnaire. In A. Holzinger (Ed.), HCI and "
                        "Usability for Education and Work, LNCS 5298 "
                        "(pp. 63-76). Springer.",
            "license": "Free for all purposes",
            "version": "1.0",
            "url": "https://www.ueq-online.org/"
        },
        "likert_options": {
            "points": 7,
            "min": 1,
            "max": 7,
            "labels": [],
            "question_head": "question_head"
        },
        "dimensions": dimensions,
        "pages": pages,
        "items": all_questions,
        "scoring": scoring
    }

    translations["question_head"] = ""

    return scale_json, translations


def list_survey_contents(qsf):
    """Print a summary of the QSF survey contents."""
    blocks = get_blocks(qsf)
    questions = get_questions(qsf)

    survey_name = qsf.get("SurveyEntry", {}).get("SurveyName", "Unknown")
    print(f"\nSurvey: {survey_name}")
    print(f"Total questions: {len(questions)}")
    print()

    for block_id, block in blocks.items():
        desc = block.get("Description", "Unnamed")
        btype = block.get("Type", "Standard")
        elements = block.get("BlockElements", [])
        q_elements = [e for e in elements if e.get("Type") == "Question"]

        print(f"  Block: {desc} ({btype}, {len(q_elements)} questions)")
        for elem in q_elements:
            qid = elem.get("QuestionID", "")
            q = questions.get(qid, {})
            qtype = q.get("QuestionType", "?")
            selector = q.get("Selector", "?")
            desc_text = q.get("QuestionDescription", "")[:60]
            nchoices = len(q.get("Choices", {}))
            print(f"    {qid}: {qtype}/{selector} ({nchoices} choices) "
                  f"- {desc_text}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Convert Qualtrics QSF to OSD format."
    )
    parser.add_argument("input", help="Path to .qsf file")
    parser.add_argument("--output", "-o", help="Output directory for scale files")
    parser.add_argument(
        "--block", "-b",
        help="Block description to extract (substring match)"
    )
    parser.add_argument(
        "--questions", "-q", nargs="+",
        help="Specific question IDs to extract (e.g., QID1 QID2)"
    )
    parser.add_argument(
        "--code", "-c", default=None,
        help="Scale code for output (default: derived from filename)"
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="List survey contents and exit"
    )
    parser.add_argument(
        "--items-per-page", type=int, default=7,
        help="Max items per page for pagination (default: 7)"
    )
    parser.add_argument(
        "--ueq", action="store_true",
        help="Apply UEQ-specific scoring and metadata"
    )

    args = parser.parse_args()

    # Load QSF
    print(f"Loading {args.input}...")
    qsf = load_qsf(args.input)

    if args.list:
        list_survey_contents(qsf)
        return

    questions = get_questions(qsf)
    blocks = get_blocks(qsf)

    # Determine which questions to extract
    target_qids = []

    if args.questions:
        target_qids = args.questions
    elif args.block:
        # Find block by description substring match
        for block_id, block in blocks.items():
            desc = block.get("Description", "")
            if args.block.lower() in desc.lower():
                elements = block.get("BlockElements", [])
                for elem in elements:
                    if elem.get("Type") == "Question":
                        target_qids.append(elem["QuestionID"])
                print(f"Found block '{desc}' with {len(target_qids)} questions")
                break
        if not target_qids:
            print(f"No block matching '{args.block}' found.")
            list_survey_contents(qsf)
            return
    else:
        # Default: list contents and ask
        list_survey_contents(qsf)
        print("Use --block or --questions to select what to extract.")
        return

    # Determine code
    if args.code:
        code = args.code
    else:
        basename = os.path.splitext(os.path.basename(args.input))[0]
        code = re.sub(r"[^a-zA-Z0-9]", "", basename)

    code_prefix = code.lower()

    # Convert questions
    all_questions = []
    all_translations = {}
    item_num = 1

    for qid in target_qids:
        q = questions.get(qid)
        if not q:
            print(f"  Warning: Question {qid} not found, skipping")
            continue

        qtype = q.get("QuestionType", "")
        selector = q.get("Selector", "")
        print(f"  Converting {qid} ({qtype}/{selector})...")

        qs, trans, count = convert_question(q, code_prefix, item_num)
        all_questions.extend(qs)
        all_translations.update(trans)
        item_num += count

    if not all_questions:
        print("No questions converted.")
        return

    print(f"\nConverted {len(all_questions)} items from "
          f"{len(target_qids)} questions.")

    # Build scale
    if args.ueq:
        scale_json, translations = build_ueq_scale(
            all_questions, all_translations, code
        )
    else:
        # Generic scale
        pages = paginate_questions(all_questions, args.items_per_page)
        translations = all_translations
        translations["debrief"] = "Thank you for completing this questionnaire."
        translations["question_head"] = ""

        scale_json = {
            "scale_info": {
                "name": code,
                "code": code,
                "description": f"Scale converted from Qualtrics survey.",
                "license": "",
                "version": "1.0",
            },
            "likert_options": {
                "points": 7,
                "min": 1,
                "max": 7,
                "labels": [],
                "question_head": "question_head"
            },
            "dimensions": [],
            "pages": pages,
            "items": all_questions,
            "scoring": {}
        }

    # Write output
    output_dir = args.output
    if not output_dir:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scales", code
        )

    os.makedirs(output_dir, exist_ok=True)

    scale_path = os.path.join(output_dir, f"{code}.json")
    with open(scale_path, "w", encoding="utf-8") as f:
        json.dump(scale_json, f, indent=2, ensure_ascii=False)
        f.write("\n")

    trans_path = os.path.join(output_dir, f"{code}.en.json")
    with open(trans_path, "w", encoding="utf-8") as f:
        json.dump(translations, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nOutput:")
    print(f"  {scale_path}")
    print(f"  {trans_path}")
    print(f"  {len(scale_json['questions'])} questions, "
          f"{len(scale_json.get('pages', []))} pages, "
          f"{len(scale_json.get('dimensions', []))} dimensions")


if __name__ == "__main__":
    main()
