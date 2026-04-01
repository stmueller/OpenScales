# Contributing to OpenScales

Thank you for contributing! This guide explains how to submit new scales or improve existing ones.

## Adding a New Scale

### 1. Create the scale directory

```
scales/{code}/
  {code}.json          — Scale definition (required)
  {code}.en.json       — English translation (required)
  {code}.{lang}.json   — Additional translations (optional)
  screenshot.png       — Preview image (optional, auto-generated if PEBL is available)
```

The `{code}` should be a short, unique identifier (e.g., `PHQ9`, `GAD7`, `BFI`).

### 2. Write the scale definition

Your `{code}.json` must include at minimum:

```json
{
  "scale_info": {
    "name": "Full Scale Name",
    "code": "CODE",
    "description": "Brief description of what the scale measures",
    "citation": "Full APA citation with DOI",
    "version": "1.0"
  },
  "questions": [
    {
      "id": "q1",
      "text_key": "q1",
      "type": "likert",
      "likert_points": 5
    }
  ]
}
```

See [SPECIFICATION.md](SPECIFICATION.md) for all available fields and features.

### 3. Write the translation file

Your `{code}.en.json` should contain all text strings referenced by the definition:

```json
{
  "question_head": "Instructions shown above each question",
  "q1": "The actual question text",
  "debrief": "Thank you message shown at the end."
}
```

### 4. Add a screenshot (optional)

If you have [PEBL](https://pebl.sf.net) installed, screenshots can be auto-generated:

```bash
pebl2 tools/generate_screenshots.py scales/{code}/
```

Otherwise, you can manually create a `screenshot.png` showing a representative question from your scale (recommended size: 1024x768).

### 5. Validate your scale definition files

```bash
python3 tools/validate_scale.py scales/{code}/
```

Fix any errors before submitting.

### 6. Submit a pull request

- One scale per pull request
- Include the scale's citation and licensing information
- Describe the scale in your PR description
- or -
- Publish your files on openScience.org and message us.


## Quality Checklist

Before submitting, verify:

- [ ] `scale_info.name` and `scale_info.code` are set
- [ ] `scale_info.citation` includes the original publication reference
- [ ] `scale_info.license` specifies usage terms
- [ ] All `text_key` references in questions have corresponding entries in the translation file
- [ ] Likert label keys referenced in `likert_options.labels` exist in the translation file
- [ ] Option `text_key`s for multi/multicheck questions exist in the translation file
- [ ] Scoring `items` arrays reference valid question IDs
- [ ] `item_coding` values are `1` (normal) or `-1` (reverse coded)
- [ ] The scale passes `validate_scale.py` without errors
- [ ] Question text matches the published version of the scale

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

- Translation keys should be descriptive (e.g., `q1`, `likert_strongly_agree`)
- Values may contain basic HTML: `<b>`, `<i>`, `<u>`, `<br>`, 
- Use `\n` for line breaks in plain text contexts
- Keep a `debrief` key for the end-of-scale message

## Improving Existing Scales

- Fix typos or formatting issues
- Add translations (new `{code}.{lang}.json` files)
- Add missing scoring definitions or dimensions
- Improve metadata (citations, descriptions, URLs)

