# Contributing to OpenScales

Thank you for contributing! This guide explains how to submit new scales or improve existing ones.

## Adding a New Scale

### 1. Create the scale directory

```
scales/openscales/{CODE}/
  {CODE}.osd           — Scale definition with embedded translations (required)
  screenshot.png       — Preview image (optional)
  README.md            — Scale description (optional, auto-generated)
  LICENSE.txt          — License evidence (recommended)
```

The `{CODE}` should be a short, unique identifier (e.g., `PHQ9`, `GAD7`, `BFI`).

### 2. Write the .osd file

Your `{CODE}.osd` is a single JSON file containing the definition and all translations:

```json
{
  "osd_version": "1.0",
  "definition": {
    "scale_info": {
      "name": "Full Scale Name",
      "code": "CODE",
      "description": "Brief description of what the scale measures",
      "citation": "Full APA citation with DOI",
      "license": "Public Domain",
      "license_explanation": "How/why this scale is available for use",
      "version": "1.0"
    },
    "implementation": {
      "author": "Your Name",
      "organization": "OpenScales Project",
      "date": "2026-04-01",
      "license": "CC BY 4.0",
      "license_url": "https://creativecommons.org/licenses/by/4.0/"
    },
    "likert_options": {
      "points": 5,
      "min": 1,
      "max": 5,
      "labels": ["likert_1", "likert_2", "likert_3", "likert_4", "likert_5"],
      "question_head": "question_head"
    },
    "items": [
      {
        "id": "q1",
        "text_key": "q1",
        "type": "likert"
      }
    ],
    "scoring": [
      {
        "id": "total",
        "name": "Total Score",
        "method": "sum",
        "items": ["q1"]
      }
    ]
  },
  "translations": {
    "en": {
      "question_head": "Instructions shown above each question",
      "q1": "The actual question text",
      "likert_1": "Strongly disagree",
      "likert_2": "Disagree",
      "likert_3": "Neutral",
      "likert_4": "Agree",
      "likert_5": "Strongly agree",
      "debrief": "Thank you for completing this scale."
    }
  }
}
```

See [SPECIFICATION.md](SPECIFICATION.md) for all available fields, item types, scoring methods, and features.

### 3. Add a screenshot (optional)

If you have [PEBL](https://pebl.org) installed, screenshots can be auto-generated. Otherwise, you can manually create a `screenshot.png` showing a representative question (recommended size: 1024x768).

### 4. Validate your scale

```bash
python3 tools/validate_scale.py scales/openscales/{CODE}/
```

Fix any errors before submitting.

### 5. Submit a pull request

- One scale per pull request
- Include the scale's citation and licensing information
- Describe the scale in your PR description

Or publish your `.osd` file and contact us via [GitHub Issues](https://github.com/stmueller/OpenScales/issues).


## Quality Checklist

Before submitting, verify:

- [ ] `scale_info.name` and `scale_info.code` are set
- [ ] `scale_info.citation` includes the original publication reference
- [ ] `scale_info.license` specifies usage terms (see recommended values in SPECIFICATION.md)
- [ ] `scale_info.license_explanation` documents the basis for the license claim
- [ ] `implementation` block is present with author and CC BY 4.0 license
- [ ] All `text_key` references in items have corresponding entries in `translations.en`
- [ ] Likert label keys in `likert_options.labels` exist in translations
- [ ] Option `text_key`s for multi/multicheck items exist in translations
- [ ] Scoring `items` arrays reference valid item IDs
- [ ] `item_coding` values are `1` (normal) or `-1` (reverse coded)
- [ ] The scale passes `validate_scale.py` without errors
- [ ] Item text matches the published version of the scale

## Licensing Guidelines

- Only submit scales that are legally available for sharing
- Published scales in the public domain or under open licenses are preferred
- If a scale requires permission, note this in `scale_info.license`
- Never submit copyrighted scale text without proper licensing
- Use the standardized `license` values defined in [SPECIFICATION.md](SPECIFICATION.md) (e.g., `"Public Domain"`, `"free to use"`, `"CC BY 4.0"`)
- **Document evidence**: Include `license_explanation` with the substance of the license grant (who said what, when). Include `license_url` pointing to the source page or press release
- **Include a LICENSE.txt file** in the scale directory when possible, containing:
  - The license terms or permissions grant text
  - Source URL where the terms were found
  - Date accessed
- Don't label a scale "Public Domain" unless the rights holder explicitly used that term or the work is a U.S. government product. Use `"free to use"` for scales released without copyright restriction but without a formal PD dedication

## Translation Guidelines

- All translations are embedded in the `.osd` file under the `translations` key
- Each language is a separate object keyed by language code (e.g., `"en"`, `"de"`, `"es"`)
- Translation keys should be descriptive (e.g., `q1`, `likert_strongly_agree`)
- Values may contain basic HTML: `<b>`, `<i>`, `<u>`, `<br>`
- Use `\n` for line breaks in plain text contexts
- Keep a `debrief` key for the end-of-scale message

## Improving Existing Scales

- Fix typos or formatting issues
- Add translations (new language entries in the `translations` object)
- Add missing scoring definitions or dimensions
- Improve metadata (citations, descriptions, URLs)
- Add `implementation` blocks if missing
