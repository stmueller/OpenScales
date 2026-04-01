# OpenScales

**[openscales.net](https://openscales.net)**

A community repository of psychological scales and questionnaires in the **Open Scale Definition (OSD)** format — a runner-agnostic JSON specification for defining self-report measures, knowledge tests, and survey instruments.

## What is Open Scale Definition?

Open Scale Definition (OSD) is a JSON-based specification for defining psychological scales, questionnaires, and surveys. Each `.osd` file is a self-contained JSON document containing the scale structure, scoring rules, and multilingual translations. The format enables:

- Multi-language support with embedded translations
- Sharing scales across different survey platforms
- Automated scoring with reverse coding, transforms, and computed variables
- Rich question types (Likert, VAS, multiple choice, grids, short/long answer, and more)
- Conversion to REDCap, Qualtrics, LimeSurvey, PsyToolkit, QTI 3.0, and Surveydown

See [SPECIFICATION.md](documentation/SPECIFICATION.md) for the full format specification (v1.0.12).

## Repository Structure

```
OpenScales/
  documentation/
    SPECIFICATION.md          — Full OSD format specification
    OSC_SPECIFICATION.md      — Open Scale Chain format (multi-scale sessions)
    CONTRIBUTING.md           — Guidelines for contributing scales
    REGISTRY.md               — Scale registry documentation
  scales/
    openscales/               — 171 fully open scales (public domain, CC, free to use)
      PHQ9/PHQ9.osd           — Patient Health Questionnaire-9
      SWLS/SWLS.osd           — Satisfaction With Life Scale
      GAD7/GAD7.osd           — Generalized Anxiety Disorder-7
      ...
    phenx/                    — 410 PhenX Toolkit scales (auto-converted)
    restricted/               — 6 scales with research-use restrictions
  tools/
    convert_to_redcap.py      — Export to REDCap Data Dictionary CSV
    convert_to_qualtrics.py   — Export to Qualtrics Advanced TXT format
    convert_to_limesurvey.py  — Export to LimeSurvey TSV format
    convert_to_psytoolkit.py  — Export to PsyToolkit survey format
    convert_to_qti.py         — Export to QTI 3.0 content package (ZIP)
    convert_to_surveydown.py  — Export to Surveydown R/Quarto (ZIP)
    osd2surveydown.py         — Surveydown converter core library
    osd_loader.py             — Shared OSD/JSON loading helper
    validate_scale.py         — Validate a scale against the spec
    generate_index.py         — Generate index.json catalog
    generate_readmes.py       — Generate README for each scale
  runner/
    scale-runner.html         — Browser-based OSD scale runner
    scale-runner.js           — JavaScript runtime for OSD scales
    scale-runner.css           — Scale runner styles
    chain-runner.html         — Multi-scale chain runner
    chain-runner.js           — Chain runner runtime
  templates/                  — OSD file templates for new scales
  index.json                  — Auto-generated catalog of all scales
  LICENSE                     — Repository license
```

## Quick Start

### Using a scale

Each scale is a self-contained `.osd` file:

```json
{
  "osd_version": "1.0",
  "definition": {
    "scale_info": { "name": "...", "code": "...", "license": "..." },
    "implementation": { "author": "...", "license": "CC BY 4.0" },
    "likert_options": { ... },
    "items": [ ... ],
    "scoring": [ ... ]
  },
  "translations": {
    "en": { "item1": "I feel satisfied with my life.", ... },
    "de": { "item1": "Ich bin zufrieden mit meinem Leben.", ... }
  }
}
```

### Running a scale in the browser

Visit [openscales.net](https://openscales.net) to browse and run any scale directly in your browser. No installation required.

### Exporting to other platforms

Convert any scale to a format your survey platform can import:

```bash
# REDCap (Data Dictionary CSV)
python3 tools/convert_to_redcap.py scales/openscales/PHQ9/ --output PHQ9_redcap.csv

# Qualtrics (Advanced TXT)
python3 tools/convert_to_qualtrics.py scales/openscales/PHQ9/ --output PHQ9_qualtrics.txt

# LimeSurvey (TSV)
python3 tools/convert_to_limesurvey.py scales/openscales/PHQ9/ --output PHQ9_limesurvey.txt

# QTI 3.0 (ZIP — Canvas, Blackboard, Moodle, Sakai)
python3 tools/convert_to_qti.py scales/openscales/PHQ9/ --output PHQ9_qti.zip

# PsyToolkit
python3 tools/convert_to_psytoolkit.py scales/openscales/PHQ9/ --output PHQ9_psytoolkit.txt

# Surveydown (R/Quarto ZIP)
python3 tools/convert_to_surveydown.py scales/openscales/PHQ9/ --output PHQ9_surveydown.zip
```

Or use the web converter at [openscales.net/convert.php](https://openscales.net/convert.php).

### Validating a scale

```bash
python3 tools/validate_scale.py scales/openscales/PHQ9/
```

## Scale Collections

| Collection | Count | Description |
|------------|-------|-------------|
| **Open Scales** | 171 | Fully open scales — public domain, Creative Commons, or explicitly free to use |
| **PhenX Toolkit** | 410 | Scales from the [PhenX Toolkit](https://www.phenxtoolkit.org/), auto-converted to OSD |
| **Restricted** | 6 | Scales with research-use restrictions (free for research, commercial use may require permission) |

## Compatible Runners

The OSD format is designed to be implemented by any survey or experiment platform:

- **[OpenScales Web Runner](https://openscales.net)** — Browser-based runner (JavaScript)
- **[PEBL](https://pebl.org)** — Psychology Experiment Building Language (native desktop + WebAssembly)
- **[Surveydown](https://surveydown.org)** — R/Quarto/Shiny (via converter)

## Export Targets

| Platform | Format | Tool |
|----------|--------|------|
| REDCap | Data Dictionary CSV | `convert_to_redcap.py` |
| Qualtrics | Advanced TXT | `convert_to_qualtrics.py` |
| LimeSurvey | Tab-separated TXT | `convert_to_limesurvey.py` |
| PsyToolkit | Survey DSL | `convert_to_psytoolkit.py` |
| Canvas / Blackboard / Moodle | QTI 3.0 ZIP | `convert_to_qti.py` |
| Surveydown (R/Quarto) | ZIP (questions.yml + survey.qmd + app.R) | `convert_to_surveydown.py` |

## Contributing

See [CONTRIBUTING.md](documentation/CONTRIBUTING.md) for guidelines on submitting new scales or improving existing ones.

## License

Repository structure, tooling, and OSD implementations: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

Individual scales may have their own licensing terms — check each scale's `scale_info.license` field. The `implementation` block in each `.osd` file documents who created the digital encoding and under what license.

## Citation

If you use OpenScales in your research, please cite:

> Mueller, S. T. (2026). OpenScales: An open repository of psychological scales in Open Scale Definition format. https://openscales.net
