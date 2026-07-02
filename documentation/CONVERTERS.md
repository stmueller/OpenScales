# OpenScales Conversion Ecosystem

This document describes the landscape of survey/data-collection platforms, OpenScales' converter coverage, and priorities for future development.

---

## Overview

OpenScales uses the **Open Scale Definition (OSD)** format as its canonical representation. Converters translate between OSD and other platforms, enabling scales to be deployed in diverse research environments and imported from existing scale libraries.

Converters live in `tools/`. The naming convention is:
- `convert_from_<platform>.py` — external format → OSD (import)
- `convert_to_<platform>.py` — OSD → external format (export)

---

## Current Converter Coverage

| Platform | Direction | Script | Notes |
|----------|-----------|--------|-------|
| **Qualtrics** | Import (→ OSD) | `convert_from_qualtrics.py` | Reads QSF export |
| **Qualtrics** | Export (OSD →) | `convert_to_qualtrics.py` | Produces Advanced TXT |
| **PsyToolkit** | Import (→ OSD) | `convert_from_psytoolkit.py` | |
| **PsyToolkit** | Export (OSD →) | `convert_to_psytoolkit.py` | |
| **REDCap** | Export (OSD →) | `convert_to_redcap.py` | Data Dictionary CSV; no import yet |
| **LimeSurvey** | Export (OSD →) | `convert_to_limesurvey.py` | Tab-separated value format |
| **Google Forms** | Export (OSD →) | `convert_to_googleforms.py` | Google Apps Script; paste into Script Editor and run once |
| **SurveyDown** | Export (OSD →) | `convert_to_surveydown.py`, `osd2surveydown.py`, `osd2surveydown.js` | Markdown/R/Shiny/PostgreSQL |
| **QTI 3.0** | Export (OSD →) | `convert_to_qti.py` | IMS QTI content package; e-assessment |
| **CamCOPS** | Import (→ OSD) | `convert_camcops_to_osd.py` | Cambridge cognitive/psychiatric kit |
| **PhenX** | Import (→ OSD) | `convert_phenx_to_osd.py` | NIH PhenX Toolkit split-file format |
| **ARC/TBS** | Import (→ OSD) | `convert_tbs_to_osd.py` | ARC Wisconsin .tbs survey files |

---

## Platform Landscape

### Platforms in ReproNim Evaluation (Chen et al. 2025, JMIR 10.2196/63343)

The following 13 platforms were compared in Chen et al. (2025) on FAIR principles (14 criteria) and functionality (8 features). OpenScales was not included in that comparison but would score well on FAIR and functionality given its schema-driven approach, open licensing, and built-in runner.

| Platform | Type | Format | OSD Coverage | Priority | Notes |
|----------|------|--------|-------------|----------|-------|
| **Qualtrics** | Commercial survey | QSF (JSON) | ✅ Both | — | Done |
| **REDCap** | Academic EDC | Data Dictionary CSV | ✅ Export | Medium | Import would be high value |
| **PsyToolkit** | Academic survey/experiment | Custom text | ✅ Both | — | Done |
| **LimeSurvey** | Open-source survey | TSV | ✅ Export | Low | Import possible |
| **SurveyDown** | R/Markdown survey | Quarto/R/Shiny | ✅ Export | — | Done |
| **ReproSchema** | Schema-driven research | JSON-LD (per-item files) | ❌ Neither | High | See below |
| **MindLogger / Curious** | Mobile/web mental health | ReproSchema internally | ❌ | Medium | Covered by ReproSchema converter |
| **KoboToolbox** | Mobile/offline fieldwork | XLSForm (Excel) | ❌ | High | One converter covers KoboToolbox + SurveyCTO + ODK |
| **SurveyCTO** | Mobile/offline research | XLSForm (Excel) | ❌ | High | Same XLSForm converter |
| **formr** | Longitudinal R surveys | Spreadsheet/CSV | ❌ | Low | R-ecosystem, niche; unrelated to SurveyDown |
| **CEDAR** | Biomedical metadata | JSON-LD (schema.org) | ❌ | Very Low | Metadata annotation tool, not survey delivery |
| **LORIS** | Neuroimaging DB | Custom PHP/JSON | ❌ | Low | Neuroimaging-specific, highly specialized |
| **OpenClinica** | Clinical trials EDC | XLSForm / ODM XML | ❌ | Low | Clinical trials focus; XLSForm converter would partially cover |
| **Pavlovia** | Online experiments | PsychoPy JSON | ❌ | Medium | Popular in academic psychology; see below |
| **SurveyMonkey** | Commercial survey | Proprietary | ❌ | Low | No open API/format; low research use |

### Other Relevant Platforms (not in Chen et al.)

| Platform | Type | Format | OSD Coverage | Priority | Notes |
|----------|------|--------|-------------|----------|-------|
| **CamCOPS** | Clinical assessment kit | Python + XML + RST | ✅ Import | — | Done; 140+ tasks, careful licensing |
| **PhenX Toolkit** | NIH standardized measures | Split-file JSON | ✅ Import | — | Done |
| **ARC Wisconsin** | Research measures repo | .tbs files | ✅ Import | — | Done; CC BY-SA 4.0 scoring code |
| **QTI 3.0** | E-assessment / LMS | XML content package | ✅ Export | — | Done; Canvas, Moodle, Blackboard |
| **XLSForm / ODK** | Mobile offline fieldwork | Excel (.xlsx) | ❌ | High | One format covering many platforms; see below |
| **LimeSurvey** | Open-source survey | TSV / QEX | ✅ Export | Low | Import possible |
| **REDCap** | Academic EDC | Data Dictionary CSV | ✅ Export | Medium | Import would be high value |

---

## Platform Deep Dives

### XLSForm / ODK

**XLSForm** is the survey-authoring standard developed by the **Open Data Kit (ODK)** project (originally University of Washington, ~2008; now community-governed). It defines surveys as Excel files with three sheets:
- `survey` — one row per item: `type`, `name`, `label`, `relevant` (skip logic), `constraint`
- `choices` — response option lists (`list_name`, `value`, `label`)
- `settings` — form metadata (title, version, language)

**ODK** is a full ecosystem: ODK Collect (Android app, works offline), ODK Central (server), and XLSForm as the authoring layer. Designed for global health and humanitarian fieldwork where internet is unreliable. Adopted by WHO, UNICEF, Gates Foundation, and thousands of NGOs.

Platforms using XLSForm:
- **KoboToolbox** — 14,000+ organizations in humanitarian/NGO sector
- **SurveyCTO** — research in low-resource settings, offline-first
- **ODK Collect** — Android field data collection
- **OpenClinica** — clinical trial EDC (also supports CDISC ODM)
- **DHIS2** — global health information systems (WHO)
- **Enketo** — web-based ODK form renderer

One `convert_to_xlsform.py` would cover all of these. Skip logic (`${item} = value`) maps well to OSD `visible_when`. Scoring is out of scope (XLSForm is data-collection only).

**Python tooling:** `pyxform` library converts XLSForm → ODK-compatible XML.

**TODO:** `convert_to_xlsform.py` and `convert_from_xlsform.py` — see TODO.md.

---

### ReproSchema

**ReproSchema** (ReproNim project, MIT/McGill/Child Mind Institute) is a JSON-LD schema-driven system for standardizing research survey protocols. Paper: Chen et al. (2025), JMIR, doi:10.2196/63343.

Library of ~90 scales at https://github.com/ReproNim/reproschema-library/ downloaded to `misc/reproschema-library-main/`. Apache 2.0 repo license; individual scale copyrights unaddressed.

Format: Decentralized JSON files — one directory per scale containing:
- `{scale}_schema` — activity metadata, item order, JS-expression scoring (`compute` array)
- `items/{item_id}` — per-item JSON with multilingual `question.{lang}` dicts
- `valueConstraints` — response option definitions

**MindLogger / Curious** uses ReproSchema as its internal format, so a ReproSchema converter would cover both.

Key mapping challenges OSD → ReproSchema:
- OSD declarative scoring → ReproSchema JS `compute` expressions (straightforward)
- OSD `visible_when` → ReproSchema `isVis` JS expressions (straightforward)
- OSD separate translation files → ReproSchema nested `{lang}` dicts (mechanical)

Key mapping challenges ReproSchema → OSD:
- JS `compute` → OSD declarative scoring (60% automatic; 40% needs manual review)
- JS `isVis` → OSD `visible_when` (requires JS boolean parser)
- Implicit subscales → explicit OSD `dimensions` (manual for complex scales)
- Nested `{lang}` dicts → separate OSD translation files (mechanical)

**TODO:** OSD→ReproSchema converter (contribute back to their repo); ReproSchema→OSD pending license audit. See TODO.md.

---

### Pavlovia / PsychoPy

**Pavlovia** (https://pavlovia.org) is a platform for hosting and running online experiments built with **PsychoPy** (Python-based experiment builder). Widely used in academic cognitive/experimental psychology. Surveys in PsychoPy use a JSON format (introduced ~2023) that supports branching, response types, and multilingual content.

The OSD and PsychoPy survey formats overlap substantially for questionnaire use cases. A converter would be valuable given Pavlovia's popularity in the OpenScales target audience (academic psychology researchers).

**TODO:** Investigate PsychoPy survey JSON format; implement `convert_to_psychopy.py`. See TODO.md.

---

### CDISC

**CDISC (Clinical Data Interchange Standards Consortium)** is a regulatory standards body for pharmaceutical clinical trials. Its standards (CDASH for data collection, SDTM for submission structure, ADaM for analysis, ODM for CRF exchange) are required by FDA and EMA for drug approval submissions.

**Not relevant to OpenScales.** CDISC is oriented toward pharmaceutical regulatory compliance, not research psychology. The overlap would only arise for formal clinical trials using OpenScales scales, which would require CDISC-compliant output regardless — a specialized use case beyond our scope.

---

### formr

**formr** (University of Göttingen) is an R-ecosystem survey framework for longitudinal/diary studies. Survey structure is defined in spreadsheets; study runs are stored as JSON. Actively maintained but niche — primarily used by researchers already in the R ecosystem.

Distinct from **SurveyDown** (different team, different format — Quarto/Markdown/Shiny). The two share only the R-ecosystem context.

Low priority for a converter given niche audience and lack of a well-documented interchange format.

---

### CEDAR

**CEDAR (Center for Expanded Data Annotation and Retrieval)** is a biomedical metadata management tool from Stanford, focused on annotating datasets with ontology-driven metadata to improve FAIR compliance. It is not a survey delivery platform — it annotates existing data with structured metadata.

**Not relevant to OpenScales** as a converter target.

---

## OSD Feature Coverage by Platform

This table summarizes which OSD features each export converter currently handles.

| OSD Feature | Qualtrics | REDCap | PsyToolkit | LimeSurvey | SurveyDown | QTI | XLSForm (planned) | ReproSchema (planned) |
|-------------|-----------|--------|------------|------------|------------|-----|-------------------|-----------------------|
| Likert items | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| VAS items | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | ⚠️ | ✅ |
| Multi/multicheck | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Text (short/long) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Grid items | ⚠️ | ⚠️ | ❌ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ❌ |
| Instructions (inst) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| visible_when / skip logic | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ | ✅ |
| Scoring / dimensions | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Translations | ✅ | ⚠️ | ⚠️ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| Variants | ⚠️ | ❌ | ❌ | ❌ | ⚠️ | ❌ | ❌ | ⚠️ |
| Parameters | ⚠️ | ❌ | ❌ | ❌ | ⚠️ | ❌ | ❌ | ⚠️ |

✅ = supported  ⚠️ = partial/workaround  ❌ = not supported / out of scope for platform

---

## Priority Roadmap

| Priority | Converter | Rationale |
|----------|-----------|-----------|
| **High** | OSD → XLSForm | Covers KoboToolbox, SurveyCTO, ODK, OpenClinica, DHIS2 in one shot; huge global health user base |
| **High** | OSD → ReproSchema | Contribute to ReproNim library; covers MindLogger/Curious too; natural collaboration |
| **Medium** | ReproSchema → OSD | Import ~75 net-new scales pending license audit |
| **Medium** | OSD → PsychoPy/Pavlovia | Popular in academic psychology; overlapping target audience |
| **Medium** | REDCap → OSD (import) | REDCap is dominant in clinical/academic research; would unlock many existing scale libraries |
| **Low** | XLSForm → OSD | Import scales from humanitarian sector |
| **Low** | formr | Niche R-ecosystem audience |
| **Not planned** | CDISC/ODM | Pharmaceutical regulatory focus; out of scope |
| **Not planned** | CEDAR | Metadata annotation, not survey delivery |
| **Not planned** | LORIS | Neuroimaging-specific, highly specialized |
| **Not planned** | SurveyMonkey | Proprietary, no open format |

---

*Last updated: 2026-06-18*
