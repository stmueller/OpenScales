#!/usr/bin/env python3
"""
convert_to_surveydown.py — Convert an OpenScales .osd to surveydown (R/Quarto) format.

CLI interface compatible with OpenScales_web/convert.php:
  python3 convert_to_surveydown.py scales/SCALECODE/ --output /tmp/out.zip --lang en

Produces a ZIP file containing questions.yml, survey.qmd, and app.R.
"""

import json
import sys
import os
import argparse
import zipfile
import glob

# Import the converter functions from sibling module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from osd2surveydown import load_osd, generate_questions_yml, generate_survey_qmd, generate_app_r


def find_osd_file(scale_dir):
    """Find the .osd file in a scale directory."""
    osds = glob.glob(os.path.join(scale_dir, '*.osd'))
    if not osds:
        return None
    return osds[0]


def main():
    parser = argparse.ArgumentParser(
        description='Convert OpenScales .osd to surveydown format (ZIP)')
    parser.add_argument('scale_dir', help='Path to scale directory containing .osd file')
    parser.add_argument('--output', '-o', required=True, help='Output ZIP file path')
    parser.add_argument('--lang', default='en', help='Language code (default: en)')
    args = parser.parse_args()

    # Find .osd file
    scale_dir = args.scale_dir.rstrip('/')
    osd_path = find_osd_file(scale_dir)
    if not osd_path:
        print(f"Error: no .osd file found in {scale_dir}", file=sys.stderr)
        sys.exit(1)

    # Load OSD
    osd_data = load_osd(osd_path)

    # Check language availability
    translations = osd_data.get('translations', {})
    if args.lang not in translations:
        available = list(translations.keys())
        if available:
            args.lang = available[0]
            print(f"Warning: language '{args.lang}' not found, using '{args.lang}'", file=sys.stderr)
        else:
            print("Error: no translations found in .osd file", file=sys.stderr)
            sys.exit(1)

    # Convert
    questions_yml = generate_questions_yml(osd_data, args.lang)
    survey_qmd = generate_survey_qmd(osd_data, args.lang)
    app_r = generate_app_r(osd_data)

    files = {
        'questions.yml': questions_yml,
        'survey.qmd': survey_qmd,
        'app.R': app_r,
    }

    # Write ZIP
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)

    code = osd_data.get('definition', {}).get('scale_info', {}).get('code', '?')
    print(f"Converted {code} to surveydown format ({len(files)} files)")


if __name__ == '__main__':
    main()
