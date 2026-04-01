#!/usr/bin/env python3
"""Generate Open Scale Definition (OSD) scales from IPIP item pool data.

Uses the Tedone Item Assignment Table (Excel) to automatically generate
OSD-format scale definitions from the International Personality Item Pool.

All IPIP items are public domain:
  "The items and scales are in the public domain, which means that one can
   copy, edit, translate, or use them for any purpose without asking
   permission and without paying a fee."
  — https://ipip.ori.org/

Usage:
    python generate_from_ipip.py                    # List available instruments
    python generate_from_ipip.py NEO                # Generate full NEO inventory
    python generate_from_ipip.py --all              # Generate all instruments
    python generate_from_ipip.py NEO --scoring mean # Use mean instead of sum
"""

import argparse
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import OrderedDict

# Where to find the Excel file relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
SCALES_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "scales")
DEFAULT_EXCEL = os.path.join(DATA_DIR, "TedoneItemAssignmentTable30APR21.xlsx")

# IPIP instrument metadata: code, full name, citation, description
INSTRUMENT_META = {
    "NEO": {
        "name": "IPIP-NEO Personality Inventory",
        "abbreviation": "IPIP-NEO",
        "code": "IPIP-NEO",
        "description": "IPIP representation of the NEO-PI-R measuring 5 domains "
                        "and 30 facets of the Five Factor Model of personality.",
        "citation": "Goldberg, L. R. (1999). A broad-bandwidth, public-domain, "
                     "personality inventory measuring the lower-level facets of "
                     "several five-factor models. In I. Mervielde, I. Deary, F. De "
                     "Fruyt, & F. Ostendorf (Eds.), Personality Psychology in "
                     "Europe (Vol. 7, pp. 7-28). Tilburg University Press.",
        "url": "https://ipip.ori.org/newNEOKey.htm",
        "scoring_method": "mean_coded",
    },
    "NEO5-20": {
        "name": "IPIP Big Five (20 items per domain)",
        "abbreviation": "IPIP-100",
        "code": "IPIP-Big5-100",
        "description": "100-item IPIP measure of the Big Five personality domains "
                        "(20 items per domain). Domain-level scoring only.",
        "citation": "Goldberg, L. R. (1999). A broad-bandwidth, public-domain, "
                     "personality inventory measuring the lower-level facets of "
                     "several five-factor models. In I. Mervielde, I. Deary, F. De "
                     "Fruyt, & F. Ostendorf (Eds.), Personality Psychology in "
                     "Europe (Vol. 7, pp. 7-28). Tilburg University Press.",
        "url": "https://ipip.ori.org/newBigFive5broadKey.htm",
        "scoring_method": "mean_coded",
    },
    "HEXACO_PI": {
        "name": "IPIP-HEXACO Personality Inventory",
        "abbreviation": "IPIP-HEXACO",
        "code": "IPIP-HEXACO",
        "description": "IPIP representation of the HEXACO-PI measuring 6 domains "
                        "and 24 facets, including Honesty-Humility.",
        "citation": "Lee, K., & Ashton, M. C. (2004). Psychometric properties of "
                     "the HEXACO personality inventory. Multivariate Behavioral "
                     "Research, 39(2), 329-358.",
        "url": "https://ipip.ori.org/newHEXACO_PI_key.htm",
        "scoring_method": "mean_coded",
    },
    "16PF": {
        "name": "IPIP 16 Personality Factors",
        "abbreviation": "IPIP-16PF",
        "code": "IPIP-16PF",
        "description": "IPIP representation of Cattell's 16 Personality Factors.",
        "citation": "Conn, S. R., & Rieke, M. L. (1994). The 16PF Fifth Edition "
                     "technical manual. Institute for Personality and Ability "
                     "Testing.",
        "url": "https://ipip.ori.org/new16PFKey.htm",
        "scoring_method": "mean_coded",
    },
    "VIA": {
        "name": "IPIP Character Strengths (VIA)",
        "abbreviation": "IPIP-VIA",
        "code": "IPIP-VIA",
        "description": "IPIP representation of the Values in Action character "
                        "strengths inventory measuring 24 character strengths.",
        "citation": "Peterson, C., & Seligman, M. E. P. (2004). Character "
                     "Strengths and Virtues: A Handbook and Classification. "
                     "Oxford University Press.",
        "url": "https://ipip.ori.org/newVIAKey.htm",
        "scoring_method": "mean_coded",
    },
    "BIS_BAS": {
        "name": "IPIP Behavioral Inhibition/Activation Scales",
        "abbreviation": "IPIP-BIS/BAS",
        "code": "IPIP-BISBAS",
        "description": "IPIP representation of Carver & White's BIS/BAS scales "
                        "measuring behavioral inhibition and activation systems.",
        "citation": "Carver, C. S., & White, T. L. (1994). Behavioral inhibition, "
                     "behavioral activation, and affective responses to impending "
                     "reward and punishment. Journal of Personality and Social "
                     "Psychology, 67(2), 319-333.",
        "url": "https://ipip.ori.org/newBISBASKey.htm",
        "scoring_method": "mean_coded",
    },
    "Levenson1981": {
        "name": "IPIP Locus of Control Scale",
        "abbreviation": "IPIP-LOC",
        "code": "IPIP-LOC",
        "description": "IPIP representation of Levenson's Locus of Control scales "
                        "measuring Internal, Powerful Others, and Chance orientations.",
        "citation": "Levenson, H. (1981). Differentiating among internality, "
                     "powerful others, and chance. In H. M. Lefcourt (Ed.), "
                     "Research with the Locus of Control Construct (Vol. 1, "
                     "pp. 15-63). Academic Press.",
        "url": "https://ipip.ori.org/newSingleConstructsKey.htm#Internality",
        "scoring_method": "mean_coded",
    },
    "Cacioppo1982": {
        "name": "IPIP Need for Cognition Scale",
        "abbreviation": "IPIP-NFC",
        "code": "IPIP-NFC",
        "description": "IPIP representation of the Need for Cognition scale "
                        "measuring tendency to engage in and enjoy effortful thinking.",
        "citation": "Cacioppo, J. T., & Petty, R. E. (1982). The need for "
                     "cognition. Journal of Personality and Social Psychology, "
                     "42(1), 116-131.",
        "url": "https://ipip.ori.org/newSingleConstructsKey.htm#Need-for-Cognition",
        "scoring_method": "sum_coded",
    },
    "Rosenberg1965": {
        "name": "IPIP Self-Esteem Scale",
        "abbreviation": "IPIP-SE",
        "code": "IPIP-SelfEsteem",
        "description": "IPIP items measuring self-esteem, designed to approximate "
                        "the Rosenberg Self-Esteem Scale.",
        "citation": "Rosenberg, M. (1965). Society and the Adolescent Self-Image. "
                     "Princeton University Press.",
        "url": "https://ipip.ori.org/newSingleConstructsKey.htm#Self-esteem",
        "scoring_method": "sum_coded",
    },
    "Scheier1994": {
        "name": "IPIP Optimism Scale",
        "abbreviation": "IPIP-OPT",
        "code": "IPIP-Optimism",
        "description": "IPIP items measuring dispositional optimism, designed to "
                        "approximate the LOT-R.",
        "citation": "Scheier, M. F., Carver, C. S., & Bridges, M. W. (1994). "
                     "Distinguishing optimism from neuroticism. Journal of "
                     "Personality and Social Psychology, 67(6), 1063-1078.",
        "url": "https://ipip.ori.org/newSingleConstructsKey.htm#Hope/Optimism",
        "scoring_method": "sum_coded",
    },
    "Radloff1977": {
        "name": "IPIP Depression Scale",
        "abbreviation": "IPIP-DEP",
        "code": "IPIP-Depression",
        "description": "IPIP items measuring depressive symptoms, designed to "
                        "approximate the CES-D.",
        "citation": "Radloff, L. S. (1977). The CES-D Scale: A self-report "
                     "depression scale for research in the general population. "
                     "Applied Psychological Measurement, 1(3), 385-401.",
        "url": "https://ipip.ori.org/newSingleConstructsKey.htm#Depression",
        "scoring_method": "sum_coded",
    },
    "Span2002": {
        "name": "IPIP ADHD Screening Scale",
        "abbreviation": "IPIP-ADHD",
        "code": "IPIP-ADHD",
        "description": "IPIP items measuring ADHD-related symptoms.",
        "citation": "Span, S. A., Earleywine, M., & Strybel, T. Z. (2002). "
                     "Confirming the factor structure of attention deficit "
                     "hyperactivity disorder symptoms in adult, nonclinical "
                     "samples. Journal of Clinical Psychology, 58(5), 497-507.",
        "url": "https://ipip.ori.org/newSingleConstructsKey.htm#ADHD",
        "scoring_method": "sum_coded",
    },
    "Snyder1974": {
        "name": "IPIP Self-Monitoring Scale",
        "abbreviation": "IPIP-SM",
        "code": "IPIP-SelfMonitoring",
        "description": "IPIP items measuring self-monitoring tendencies.",
        "citation": "Snyder, M. (1974). Self-monitoring of expressive behavior. "
                     "Journal of Personality and Social Psychology, 30(4), 526-537.",
        "url": "https://ipip.ori.org/newSingleConstructsKey.htm#Self-monitoring",
        "scoring_method": "sum_coded",
    },
    "BIDR": {
        "name": "IPIP Social Desirability Scales",
        "abbreviation": "IPIP-BIDR",
        "code": "IPIP-BIDR",
        "description": "IPIP representation of the BIDR measuring impression "
                        "management, self-deception, and cognitive failures.",
        "citation": "Paulhus, D. L. (1991). Measurement and control of response "
                     "bias. In J. P. Robinson, P. R. Shaver, & L. S. Wrightsman "
                     "(Eds.), Measures of Personality and Social Psychological "
                     "Attitudes (pp. 17-59). Academic Press.",
        "url": "https://ipip.ori.org/newSingleConstructsKey.htm",
        "scoring_method": "mean_coded",
    },
    "Barchard2001": {
        "name": "IPIP Emotional Intelligence Scale",
        "abbreviation": "IPIP-EI",
        "code": "IPIP-EI",
        "description": "IPIP representation of emotional intelligence components "
                        "including empathy, emotional expressivity, and "
                        "emotion-based decision making.",
        "citation": "Barchard, K. A. (2001). Emotional and social intelligence: "
                     "Examining its place in the nomological network. Unpublished "
                     "doctoral dissertation, University of British Columbia.",
        "url": "https://ipip.ori.org/newEmotionalIntelligenceKey.htm",
        "scoring_method": "mean_coded",
    },
    "CAT-PD": {
        "name": "IPIP Personality Disorder Traits (CAT-PD)",
        "abbreviation": "IPIP-CAT-PD",
        "code": "IPIP-CATPD",
        "description": "IPIP representation of the CAT-PD measuring 33 personality "
                        "disorder-relevant trait dimensions.",
        "citation": "Simms, L. J., Goldberg, L. R., Roberts, J. E., Watson, D., "
                     "Welte, J., & Rotterman, J. H. (2011). Computerized Adaptive "
                     "Assessment of Personality Disorder. Psychological Assessment, "
                     "23(1), 111-126.",
        "url": "https://ipip.ori.org/newCAT-PD-SFKey.htm",
        "scoring_method": "mean_coded",
    },
    "BFAS": {
        "name": "IPIP Big Five Aspect Scales",
        "abbreviation": "IPIP-BFAS",
        "code": "IPIP-BFAS",
        "description": "IPIP representation of the Big Five Aspect Scales measuring "
                        "10 aspects (2 per Big Five domain).",
        "citation": "DeYoung, C. G., Quilty, L. C., & Peterson, J. B. (2007). "
                     "Between facets and domains: 10 aspects of the Big Five. "
                     "Journal of Personality and Social Psychology, 93(5), 880-896.",
        "url": "https://ipip.ori.org/newBFASKeys.htm",
        "scoring_method": "mean_coded",
    },
    "IPIP-IPC": {
        "name": "IPIP Interpersonal Circumplex",
        "abbreviation": "IPIP-IPC",
        "code": "IPIP-IPC",
        "description": "IPIP Interpersonal Circumplex scales measuring 8 "
                        "interpersonal styles.",
        "citation": "Markey, P. M., & Markey, C. N. (2009). A brief assessment of "
                     "the Interpersonal Circumplex: The IPIP-IPC. Assessment, "
                     "16(4), 352-361.",
        "url": "https://ipip.ori.org/newIPIP-IPCScales.htm",
        "scoring_method": "mean_coded",
    },
    "ORVIS": {
        "name": "IPIP Oregon Vocational Interest Scales",
        "abbreviation": "IPIP-ORVIS",
        "code": "IPIP-ORVIS",
        "description": "IPIP vocational interest scales measuring 8 broad "
                        "interest domains.",
        "citation": "Pozzebon, J. A., Visser, B. A., Ashton, M. C., Lee, K., & "
                     "Goldberg, L. R. (2010). Psychometric characteristics of a "
                     "public-domain self-report measure of vocational interests. "
                     "Journal of Personality Assessment, 92(2), 168-174.",
        "url": "https://ipip.ori.org/newORVISKey.htm",
        "scoring_method": "mean_coded",
    },
    "Goldberg1999": {
        "name": "IPIP Dissociation Scale",
        "abbreviation": "IPIP-DIS",
        "code": "IPIP-Dissociation",
        "description": "IPIP items measuring dissociative experiences.",
        "citation": "Goldberg, L. R. (1999). The Curious Experiences Survey: "
                     "A revised version of the Dissociative Experiences Scale.",
        "url": "https://ipip.ori.org/newSingleConstructsKey.htm",
        "scoring_method": "sum_coded",
    },
}


def parse_xlsx(filepath):
    """Parse the Tedone IPIP Excel file without external dependencies.

    Returns list of dicts with keys: instrument, alpha, key, text, label
    """
    zf = zipfile.ZipFile(filepath)

    # Parse shared strings
    tree = ET.parse(zf.open("xl/sharedStrings.xml"))
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for si in tree.findall(".//s:si", ns):
        # Handle both simple <t> and rich text <r><t>
        parts = []
        for t in si.findall(".//s:t", ns):
            if t.text:
                parts.append(t.text)
        strings.append("".join(parts))

    # Parse worksheet
    tree2 = ET.parse(zf.open("xl/worksheets/sheet1.xml"))
    rows = tree2.findall(".//s:row", ns)

    # Column mapping: A=instrument, B=alpha, C=key, D=text, E=label
    col_map = {"A": "instrument", "B": "alpha", "C": "key", "D": "text", "E": "label"}

    data = []
    for row_idx, row in enumerate(rows):
        if row_idx == 0:  # skip header
            continue
        cells = row.findall("s:c", ns)
        record = {}
        for c in cells:
            ref = c.get("r", "")
            col_letter = re.match(r"([A-Z]+)", ref).group(1) if ref else ""
            if col_letter not in col_map:
                continue
            v = c.find("s:v", ns)
            if v is None:
                continue
            if c.get("t") == "s":
                record[col_map[col_letter]] = strings[int(v.text)]
            else:
                record[col_map[col_letter]] = v.text
        if record.get("text"):
            data.append(record)

    return data


def make_dim_id(label):
    """Convert a construct label to a valid dimension ID."""
    # Clean up the label to make a valid ID
    dim_id = label.lower()
    dim_id = re.sub(r"[/,\s]+", "_", dim_id)
    dim_id = re.sub(r"[^a-z0-9_]", "", dim_id)
    dim_id = re.sub(r"_+", "_", dim_id)
    dim_id = dim_id.strip("_")
    return dim_id


def make_item_id(code_prefix, index):
    """Generate an item ID like 'neo_001'."""
    return f"{code_prefix}_{index:03d}"


def generate_scale(instrument, items, meta, scoring_method="mean_coded"):
    """Generate OSD scale definition and translation files.

    Args:
        instrument: instrument name from Excel
        items: list of item dicts from parse_xlsx, filtered to this instrument
        meta: metadata dict from INSTRUMENT_META
        scoring_method: 'sum_coded' or 'mean_coded'

    Returns:
        (scale_json, translation_json) as dicts
    """
    code = meta["code"]
    code_lower = code.lower().replace("-", "_")

    # Filter out unscored items (key=0) — these exist only in VIA
    scored_items = [i for i in items if int(float(i.get("key", "1"))) != 0]
    skipped = len(items) - len(scored_items)
    if skipped > 0:
        print(f"  Skipping {skipped} unscored items (key=0)")

    # Group items by label (dimension)
    dim_items = OrderedDict()
    for item in scored_items:
        label = item.get("label", "general")
        if label not in dim_items:
            dim_items[label] = []
        dim_items[label].append(item)

    # Build dimensions
    dimensions = []
    for label in dim_items:
        dimensions.append({
            "id": make_dim_id(label),
            "name": label
        })

    # Build questions and translations
    questions = []
    translations = {}
    item_counter = 1

    # Standard IPIP Likert labels
    translations["likert_1"] = "Very Inaccurate"
    translations["likert_2"] = "Moderately Inaccurate"
    translations["likert_3"] = "Neither Accurate Nor Inaccurate"
    translations["likert_4"] = "Moderately Accurate"
    translations["likert_5"] = "Very Accurate"
    translations["question_head"] = "Describe yourself as you generally are now, not as you wish to be in the future. Describe yourself as you honestly see yourself, in relation to other people you know of the same sex as you are, and roughly your same age."

    for label, label_items in dim_items.items():
        for item in label_items:
            item_id = make_item_id(code_lower, item_counter)
            key = int(float(item.get("key", "1")))

            questions.append({
                "id": item_id,
                "text_key": item_id,
                "type": "likert",
                "likert_points": 5,
                "coding": key
            })

            translations[item_id] = item["text"]
            item_counter += 1

    # Build scoring
    scoring = {}
    item_counter = 1
    for label, label_items in dim_items.items():
        dim_id = make_dim_id(label)
        scored_items = []
        item_coding = {}
        alphas = []

        for item in label_items:
            item_id = make_item_id(code_lower, item_counter)
            key = int(float(item.get("key", "1")))
            scored_items.append(item_id)
            item_coding[item_id] = key
            if item.get("alpha"):
                try:
                    alphas.append(float(item["alpha"]))
                except (ValueError, TypeError):
                    pass
            item_counter += 1

        score_entry = {
            "method": scoring_method,
            "items": scored_items,
            "item_coding": item_coding,
        }

        # Add alpha if available (all items in same dimension should have same alpha)
        if alphas:
            alpha = alphas[0]  # They should all be the same
            score_entry["description"] = f"Cronbach's alpha = {alpha:.2f}"

        scoring[dim_id] = score_entry

    # Add debrief
    translations["debrief"] = "Thank you for completing this questionnaire."

    # Build the full scale definition
    scale_json = {
        "scale_info": {
            "name": meta["name"],
            "code": code,
            "abbreviation": meta.get("abbreviation", code),
            "description": meta["description"],
            "citation": meta["citation"],
            "license": "Public Domain",
            "version": "1.0",
            "url": meta.get("url", "https://ipip.ori.org/")
        },
        "likert_options": {
            "points": 5,
            "min": 1,
            "max": 5,
            "labels": [
                "likert_1",
                "likert_2",
                "likert_3",
                "likert_4",
                "likert_5"
            ],
            "question_head": "question_head"
        },
        "dimensions": dimensions,
        "questions": questions,
        "scoring": scoring
    }

    return scale_json, translations


def write_scale(code, scale_json, translation_json, output_dir):
    """Write scale files to disk."""
    scale_dir = os.path.join(output_dir, code)
    os.makedirs(scale_dir, exist_ok=True)

    # Write scale definition
    scale_path = os.path.join(scale_dir, f"{code}.json")
    with open(scale_path, "w", encoding="utf-8") as f:
        json.dump(scale_json, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Write English translation
    trans_path = os.path.join(scale_dir, f"{code}.en.json")
    with open(trans_path, "w", encoding="utf-8") as f:
        json.dump(translation_json, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return scale_dir


def list_instruments(data):
    """Print available instruments and their statistics."""
    from collections import Counter
    inst_counts = Counter()
    inst_labels = {}
    inst_items = {}

    for item in data:
        inst = item.get("instrument", "")
        label = item.get("label", "")
        text = item.get("text", "")
        inst_counts[inst] += 1
        if inst not in inst_labels:
            inst_labels[inst] = set()
            inst_items[inst] = set()
        inst_labels[inst].add(label)
        inst_items[inst].add(text)

    print(f"{'Instrument':<20} {'Items':>6} {'Unique':>6} {'Labels':>6}  "
          f"{'Has Meta':>8}  Description")
    print("-" * 100)

    for inst in sorted(inst_counts.keys()):
        has_meta = "YES" if inst in INSTRUMENT_META else ""
        meta_desc = ""
        if inst in INSTRUMENT_META:
            meta_desc = INSTRUMENT_META[inst]["name"]
        print(f"{inst:<20} {inst_counts[inst]:>6} {len(inst_items[inst]):>6} "
              f"{len(inst_labels[inst]):>6}  {has_meta:>8}  {meta_desc}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate OSD scales from IPIP item pool data."
    )
    parser.add_argument(
        "instrument",
        nargs="?",
        help="Instrument name to generate (e.g., 'NEO', 'HEXACO_PI'). "
             "Omit to list available instruments."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate all instruments with metadata defined."
    )
    parser.add_argument(
        "--excel",
        default=DEFAULT_EXCEL,
        help="Path to Tedone Item Assignment Table Excel file."
    )
    parser.add_argument(
        "--output",
        default=SCALES_DIR,
        help="Output directory for generated scales."
    )
    parser.add_argument(
        "--scoring",
        choices=["sum_coded", "mean_coded"],
        default=None,
        help="Override scoring method (default: use instrument-specific default)."
    )

    args = parser.parse_args()

    if not os.path.exists(args.excel):
        print(f"Error: Excel file not found: {args.excel}")
        print(f"Download from: https://ipip.ori.org/TedoneItemAssignmentTable30APR21.xlsx")
        print(f"Place in: {DATA_DIR}/")
        sys.exit(1)

    print(f"Parsing {args.excel}...")
    data = parse_xlsx(args.excel)
    print(f"Loaded {len(data)} item-scale assignments.")

    if not args.instrument and not args.all:
        print()
        list_instruments(data)
        print()
        print("Use: python generate_from_ipip.py <instrument> to generate a scale.")
        print("Use: python generate_from_ipip.py --all to generate all defined scales.")
        return

    # Determine which instruments to generate
    if args.all:
        instruments = list(INSTRUMENT_META.keys())
    else:
        instruments = [args.instrument]

    for instrument in instruments:
        # Filter data for this instrument
        inst_items = [d for d in data if d.get("instrument") == instrument]

        if not inst_items:
            print(f"Warning: No items found for instrument '{instrument}'")
            available = sorted(set(d.get("instrument", "") for d in data))
            print(f"Available: {', '.join(available)}")
            continue

        # Get metadata
        if instrument in INSTRUMENT_META:
            meta = INSTRUMENT_META[instrument]
        else:
            # Generate basic metadata for unknown instruments
            meta = {
                "name": f"IPIP {instrument} Scale",
                "abbreviation": f"IPIP-{instrument}",
                "code": f"IPIP-{instrument}",
                "description": f"IPIP representation of the {instrument} personality measure.",
                "citation": "Goldberg, L. R., Johnson, J. A., Eber, H. W., Hogan, R., "
                            "Ashton, M. C., Cloninger, C. R., & Gough, H. G. (2006). "
                            "The International Personality Item Pool and the future of "
                            "public-domain personality measures. Journal of Research in "
                            "Personality, 40(1), 84-96.",
                "url": "https://ipip.ori.org/",
                "scoring_method": "mean_coded",
            }

        scoring = args.scoring or meta.get("scoring_method", "mean_coded")
        code = meta["code"]

        print(f"\nGenerating {code} from {instrument}...")
        print(f"  Items: {len(inst_items)}, Unique texts: {len(set(i['text'] for i in inst_items))}")

        labels = sorted(set(i.get("label", "") for i in inst_items))
        print(f"  Dimensions: {len(labels)}")
        for label in labels:
            count = sum(1 for i in inst_items if i.get("label") == label)
            print(f"    {label}: {count} items")

        scale_json, trans_json = generate_scale(
            instrument, inst_items, meta, scoring_method=scoring
        )
        scale_dir = write_scale(code, scale_json, trans_json, args.output)

        q_count = len(scale_json["questions"])
        d_count = len(scale_json["dimensions"])
        print(f"  Generated: {scale_dir}/")
        print(f"    {code}.json ({q_count} questions, {d_count} dimensions)")
        print(f"    {code}.en.json ({len(trans_json)} translation keys)")

    print("\nDone!")


if __name__ == "__main__":
    main()
