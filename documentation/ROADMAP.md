# OpenScales — Mission, Design, and Roadmap

## Naming

The format and project need a name that:
- Communicates openness and interoperability
- Is distinct from **OSF** (Open Science Framework) — a well-known platform in academic research
- Works as both a project name and a format identifier

**Chosen name:** OpenScales / Open Scale Definition (OSD)

The project is called **OpenScales**. The format is **Open Scale Definition (OSD)**. The abbreviation "OSD" avoids collision with **OSF** (Open Science Framework), a well-known platform in academic research where users may host their scale definitions.

In technical contexts, the format is "a `.json` scale definition file conforming to the OSD specification." The file extension is `.json`, not a custom extension — it's JSON, and tools should treat it as JSON.

If a short handle is needed (e.g., for `--format` flags in converters), use `osd`.

---

## Mission

OpenScales provides:

1. **A specification** (OSD) for defining psychological scales, questionnaires, and survey instruments in a runner-agnostic JSON format
2. **A community repository** of freely-licensed scales in this format
3. **Conversion tools** that export scales to formats used by major survey platforms and LMS systems
4. **Runners** that administer these scales directly — including the [PEBL](https://pebl.sf.net) desktop platform and web-based platform [PEBLHUB](https://peblhub.online), and a javascript OpenScales runner and upload script for self-hosting.

### Who is this for?

- **Researchers** who need validated scales and want to use them in their preferred platform (Qualtrics, REDCap, Canvas, etc.)
- **Scale developers** who want their instruments to be widely accessible across platforms
- **Clinicians** who need standardized assessments available in multiple languages
- **Students and educators** who need scales for coursework or teaching demonstrations

### Core Principles

1. **Separation of structure and content.** The definition file (structure, scoring, logic) is distinct from translation files (all user-facing text). This makes multi-language support natural rather than bolted on.

2. **Export-first interoperability.** The primary use case is: "I have a scale in OSD format and need to use it in Platform X." Converters are one-directional exports. The reference implementations are intended to fully express the scale developers complete testing instructions (from wording, translations,  responses, branching, dependence, randomization, subscales, scoring, and interpretation) using a small set of common question/item types.  Not all of the specification will be available on all platforms, but exporting should at least provide a set of translated questions with appropriate responses into supported platforms.

3. **Permissive but principled licensing.** The repository collects public domain and CC-licensed scales. Author-approved contribtions not CC-licensed are also supported. Commercial or copyright-encumbered scales may be offered through partnerships, where the definition file is freely available but use requires a license from the rights holder.

4. **Progressive complexity.** The specification has three tiers (Core, Standard, Advanced). A simple scale with 10 Likert items needs only Core features. Complex adaptive instruments can use Advanced features. Runners declare what they support and degrade gracefully.

5. **Platform adoption welcome.** We provide Python conversion tools, but the specification is designed so that platforms (SurveyMonkey, LimeSurvey, etc.) could write native importers if the format gains traction.

6. **Repository and Registry.** APA PsychTests and MAPI research trust each track up to 80,000 tests, many of which are owned by individual researchers, clinicians, hospitals, businesses, etc. We aim to both provide scale specifications for tests we can host, and a registry for users who wish to host their own scales, either for free (via github, osf.io, etc.) or for commercial purposes.
---

## Question Types

### Currently Specified

| Type | Category | Description |
|------|----------|-------------|
| `likert` | Rating | Likert-type scale (e.g., 1-5 agreement) |
| `vas` | Rating | Visual analog scale / slider |
| `grid` | Rating | Matrix of sub-items with shared response options |
| `multi` | Choice | Multiple choice, single selection (radio buttons) |
| `multicheck` | Choice | Multiple choice, multiple selection (checkboxes) |
| `rank` | Choice | Rank/order items by preference (Advanced tier) |
| `short` | Text | Short text entry |
| `long` | Text | Multi-line text entry |
| `inst` | Display | Instruction or information display |

### Proposed Additions

Based on analysis of Qualtrics, REDCap, LimeSurvey, PsyToolkit, and other platforms:

#### High Priority — Common in scale/survey research

| Type | Description | Rationale | Target Platforms |
|------|-------------|-----------|-----------------|
| `constant_sum` | Allocate N points across options | Common in preference/importance research; native in Qualtrics (CS), QuestionPro | Qualtrics, QTI |
| `semantic_differential` | Bipolar scale with opposing anchor labels | Foundational in psychology (Osgood, 1957); Qualtrics Matrix-Bipolar | Qualtrics, QTI |
| `dropdown` | Single selection from a dropdown menu | Essential for long option lists (countries, occupations); distinct UX from `multi` | All platforms |
| `number` | Validated numeric entry | Age, counts, measurements; distinct from `short` with number validation | REDCap, Qualtrics, QTI |
| `date` | Date picker | Demographics, event timing, longitudinal studies | REDCap, Qualtrics, LimeSurvey |

#### Medium Priority — Useful but less common in scales

| Type | Description | Rationale |
|------|-------------|-----------|
| `nps` | Net Promoter Score (0-10) | Standardized format with known scoring; could be a `likert` variant |
| `file_upload` | Upload documents or images | Consent forms, work samples; support varies by platform |
| `time` | Time or duration entry | Time-use studies, EMA |

#### Deferred — Too specialized or platform-specific

These types exist on some platforms but are not common enough in psychometric scale research to warrant specification:

- MaxDiff / best-worst scaling — complex experimental design, not a question type
- Heat map / click map — requires image + coordinate capture
- Conjoint analysis — experimental methodology, not a scale format
- Signature capture — legal/consent utility
- CAPTCHA — anti-fraud utility
- Geolocation — metadata capture
- Star rating — rendering variant of `likert`, not a distinct data type

### Implementation Notes

**`constant_sum`**: New question type with `total` field specifying the required sum, and `options` listing the items to allocate across. Response is a mapping of option IDs to allocated values.

```json
{
  "id": "importance",
  "type": "constant_sum",
  "text_key": "importance_question",
  "total": 100,
  "options": [
    {"value": "quality", "text_key": "opt_quality"},
    {"value": "speed", "text_key": "opt_speed"},
    {"value": "cost", "text_key": "opt_cost"}
  ]
}
```

**`semantic_differential`**: Similar to `grid` but with `left_label` and `right_label` per row instead of shared column headers. Each row is a bipolar pair.

```json
{
  "id": "sd1",
  "type": "semantic_differential",
  "text_key": "sd_instructions",
  "points": 7,
  "items": [
    {"left_key": "sd_good", "right_key": "sd_bad"},
    {"left_key": "sd_strong", "right_key": "sd_weak"},
    {"left_key": "sd_active", "right_key": "sd_passive"}
  ]
}
```

**`dropdown`**: Identical data model to `multi`, with a `display_as` hint or simply a separate type to signal dropdown rendering.

**`number`**: Like `short` but with `min`, `max`, `step`, and `decimal_places` fields. Runners display a numeric input with validation.

**`date`**: With optional `min_date`, `max_date`, `format` (e.g., `"YYYY-MM-DD"`). Runners display a date picker widget.

---

## Converter Roadmap

### Guiding Principle

The converters are **export-only** — they convert FROM OSD format TO platform-specific formats. Import converters (from other formats into OSD) are lower priority and only built when there's a clear source of scales to ingest.

### Completed

All export converters are implemented. Import converters exist where there is a meaningful pool of existing scales to ingest.

| Converter | Direction | Format | Status |
|-----------|-----------|--------|--------|
| `convert_to_psytoolkit.py` | Export | PsyToolkit survey DSL | ✅ |
| `convert_from_psytoolkit.py` | Import | PsyToolkit survey DSL | ✅ |
| `convert_to_qualtrics.py` | Export | Qualtrics Advanced TXT | ✅ |
| `convert_from_qualtrics.py` | Import | Qualtrics QSF | ✅ |
| `convert_to_qti.py` | Export | QTI 3.0 content package | ✅ |
| `convert_to_redcap.py` | Export | REDCap Data Dictionary CSV | ✅ |
| `convert_to_limesurvey.py` | Export | LimeSurvey LSS XML | ✅ |

### Phase 1: Qualtrics Advanced TXT Export

**File:** `convert_to_qualtrics.py`

**Priority:** High — Qualtrics is the dominant academic survey platform.

**Format:** `[[AdvancedFormat]]` TXT. This is the simplest reliable import path. Qualtrics supports it well and it covers the question types we need.

| OSD Type | Qualtrics Output |
|-----------------|-----------------|
| `likert` (multi-item, shared scale) | `[[Question:Matrix]]` with `[[Choices]]` (rows) + `[[Answers]]` (scale points) |
| `likert` (single item) | `[[Question:MC]]` with choices |
| `vas` | `[[Question:Slider]]` (limited — min/max need manual config post-import) |
| `multi` | `[[Question:MC]]` |
| `multicheck` | `[[Question:MC]]` + `[[MultipleAnswer]]` |
| `dropdown` | `[[Question:MC:Dropdown]]` |
| `short` | `[[Question:TE:SingleLine]]` |
| `long` | `[[Question:TE:Essay]]` |
| `number` | `[[Question:TE:SingleLine]]` (with note about validation) |
| `grid` | `[[Question:Matrix]]` |
| `semantic_differential` | `[[Question:Matrix:Bipolar]]` |
| `constant_sum` | `[[Question:CS]]` |
| `inst` | `[[Question:DB]]` |
| `rank` | `[[Question:RO]]` |
| Pages/sections | `[[Block:Name]]` + `[[PageBreak]]` |
| Question IDs | `[[ID:tag]]` |

**Limitations:**
- Slider min/max/gridlines cannot be set via TXT import — user must adjust in Qualtrics editor
- Reverse coding (RecodeValues) cannot be set via TXT — user must configure manually or we add a note
- No scoring/computed variables in TXT format
- VAS endpoint labels require manual configuration

**Testing:** Direct import into Qualtrics account for verification.

### Phase 2: QTI 3.0 Export

**File:** `convert_to_qti.py`

**Priority:** High — covers every LMS (Canvas, Blackboard, Moodle, Sakai, Brightspace).

**Output:** ZIP content package containing:
```
{code}_qti/
  imsmanifest.xml          — Content package manifest
  assessment.xml           — Assessment test structure
  items/
    {id}.xml               — One file per question (qti-assessment-item)
  scoring_info.json        — Supplementary: subscale definitions (not part of QTI)
```

| OSD Type | QTI 3.0 Element |
|-----------------|----------------|
| `likert` | `qti-choice-interaction` + `class="likert"` + `qti-mapping` for numeric coding |
| `vas` | `qti-slider-interaction` (lowerBound/upperBound/step) |
| `multi` | `qti-choice-interaction` (max-choices="1") |
| `multicheck` | `qti-choice-interaction` (max-choices="0") |
| `short` | `qti-text-entry-interaction` |
| `long` | `qti-extended-text-interaction` |
| `grid` | `qti-match-interaction` (two simpleMatchSets) |
| `rank` | `qti-order-interaction` |
| `inst` | `qti-item-body` with no interaction |
| `dropdown` | `qti-inline-choice-interaction` |
| `number` | `qti-text-entry-interaction` with pattern-mask |
| `constant_sum` | No direct equivalent — use PCI or multiple `qti-text-entry-interaction` |
| `semantic_differential` | `qti-choice-interaction` per row, or PCI |
| Reverse coding | Reversed values in `qti-mapping` |
| Subscale scoring | Not representable in QTI — included in `scoring_info.json` |

**Key decisions:**
- Use Python `xml.etree.ElementTree` for XML generation (no external dependencies)
- Include `scoring_info.json` as a supplementary file for subscale definitions, since QTI has no way to express "sum items 1-9 for the depression score"
- Survey items omit `qti-response-processing` (no correct answer)
- Consider a `--qti-version 2.1` flag for backward compatibility (mechanical element renaming)

**Limitations:**
- QTI is fundamentally item-level — no aggregated scoring
- Matrix rendering varies wildly across LMS platforms
- VAS text anchor labels not natively supported (workaround: put labels in item body HTML)
- Constant sum has no direct QTI equivalent

### Phase 3: REDCap Data Dictionary CSV Export

**File:** `convert_to_redcap.py`

**Priority:** Medium-high — REDCap is ubiquitous in clinical and health research.

**Output:** CSV file conforming to REDCap's Data Dictionary import format.

REDCap columns:

| Column | Mapping |
|--------|---------|
| `Variable / Field Name` | Question ID |
| `Form Name` | Scale code |
| `Section Header` | Page/section title |
| `Field Type` | `radio`, `dropdown`, `text`, `slider`, `descriptive`, `checkbox`, `notes`, `calc` |
| `Field Label` | Question text (from translation) |
| `Choices, Calculations, OR Slider Labels` | `1, Strongly Disagree \| 2, Disagree \| ...` |
| `Field Note` | Reverse coding notes, source information |
| `Text Validation Type OR Show Slider Number` | `number`, `date_ymd`, `email`, etc. |
| `Text Validation Min` / `Max` | From validation rules |
| `Required Field?` | `y` / blank |
| `Branching Logic` | From `visible_when` conditions |

| OSD Type | REDCap Field Type |
|-----------------|------------------|
| `likert` | `radio` with numeric-coded choices |
| `vas` | `slider` |
| `multi` | `radio` |
| `multicheck` | `checkbox` |
| `dropdown` | `dropdown` |
| `short` | `text` |
| `long` | `notes` |
| `number` | `text` with number validation |
| `date` | `text` with date_ymd validation |
| `inst` | `descriptive` |
| `grid` | Multiple `radio` fields (one per row, shared choices) |
| `constant_sum` | Multiple `text` fields with number validation |
| Subscale scoring | `calc` field type with expression |

**Advantages:** REDCap can represent scoring as `calc` fields — `@SUM([phq1],[phq2],...,[phq9])`. This is the only target platform (besides PsyToolkit) that can natively compute subscale scores.

### Phase 4: LimeSurvey Export

**File:** `convert_to_limesurvey.py`

**Priority:** Medium — covers the open-source self-hosted survey crowd.

**Format:** LSS (LimeSurvey Survey Structure) XML or TSV import.

This is lower priority than the others but straightforward once the other converters exist.
Given Limesurvey is open source software, a .osd import module may be a feasible alternative.

### Potential Future Exports

| Platform | Feasibility | Notes |
|----------|-------------|-------|
| SurveyMonkey | Low | No documented import format; could potentially import via Google Forms |
| Google Forms | Low | No file import; would need Google Apps Script or Forms API |
| Microsoft Forms | Low | No file import |
| Typeform | Low | API-only creation |
| SurveyJS | Medium | JSON-based; could generate SurveyJS JSON definitions |
| Formstack | Low | No bulk import |

If any of these platforms gain native import support for the OSD format, that would be ideal — and more likely to happen if the project gains traction and the specification is clean and well-documented.

---

## Hosting and Distribution

### Current: Repository + Python Tools

Users clone the repository (or download individual scale directories) and run Python scripts locally:

```bash
python3 tools/convert_to_qualtrics.py scales/PHQ9/ --output PHQ9_qualtrics.txt
python3 tools/convert_to_qti.py scales/PHQ9/ --output PHQ9_qti.zip
python3 tools/convert_to_redcap.py scales/PHQ9/ --output PHQ9_redcap.csv
```

### Planned: Web-Based Conversion Service (Completed)

Host a web interface (on OpenScales.net) where users:

1. Browse the scale catalog
2. Select a scale
3. Choose a target format (Qualtrics, QTI, REDCap, PsyToolkit, LimeSurvey)
4. Download the converted file

### Web-Based Scale Runner (Complete for 90% of specification)

A self-contained HTML/JS runner (`runner/scale-runner.js`) that administers any OSD scale definition directly in the browser. Published as part of OpenScales so anyone can self-host.

**Design goals:**
- Mobile-first responsive design — works on phones and tablets
- Embeddable in any hosting environment (peblhub, institutional servers, Prolific, MTurk)
- Configurable data submission endpoint — works against the included `server/collect.php` or any compatible backend
- Fires a `peblTestComplete` event on completion, making it a drop-in participant in the peblhub chain system alongside PEBL behavioral tests
- Versioned releases; peblhub archives the exact runner version used in each study for reproducibility

**Self-hosting stack:**
```
runner/scale-runner.js     — the runner (versioned releases)
runner/scale-runner.css    — mobile-first styles
runner/scale-runner.html   — standalone shell
runner/server/collect.php  — minimal data collection endpoint
```

A researcher with shared hosting can drop these four files on their server and administer any openly-licensed OSD scale with no accounts or subscriptions.

**Peblhub integration:** peblhub pins a specific OpenScales runner release and wraps it with chain sequencing, study management, token authentication, and server-side data archival. From the chain's perspective, a scale item is interchangeable with a PEBL behavioral test item.

### Scale Library Model

The hub's scale library uses a three-tier model that accommodates the full range of licensing realities in psychometrics:

**Tier 1 — Hosted (openly licensed)**
Public domain and CC-licensed scales. The hub hosts the JSON and anyone can add these to a study. The OpenScales GitHub repository contains only Tier 1 scales.

**Tier 1 -- Restricted (private)**
We keep a set of implemented scales that are not yet distributable. Once launched, we will contact authors and provide the .osd files for them to use, and request author-approval for integrating into repository.

**Tier 2 —  Registry (hub knows, doesn't host)**
Copyrighted scales (e.g., MEQ, MOCI, commercial assessments). The library entry shows name, description, license requirements, and how to contact the rights holder. The OSD-format file may be available from the author to licensed users. Once obtained, researchers upload it to their private workspace (Tier 3).

The hub/OpenScales project offers scale authors a service: we create a validated OSD implementation of their instrument that they can distribute to licensed researchers. Authors who participate give researchers a ready-to-run file; authors who don't are ghost-listed with a link to their own distribution channel.

**Tier 3 — Private workspace**
Scales uploaded by a researcher to their own hub workspace. Not visible in the public library. Runs with full chain integration and data archival. The researcher is responsible for licensing compliance. This covers: licensed proprietary scales, custom institutional scales, and scales researchers have created themselves.

### Business Model (Open-Core)

OpenScales is fully open source — the spec, tools, openly-licensed scales, and the runner are all public. Peblhub adds a commercial layer:

| Layer | License | Availability |
|---|---|---|
| OSD spec, converters, runner, open scales | Open source (MIT/CC) | Everyone, including self-hosters |
| Peblhub managed hosting (chains, studies, user accounts, data storage) | Commercial SaaS | Peblhub subscribers |
| Proprietary scale library | Licensed content, peblhub-only | Fee per scale or per administration |

**Proprietary scale licensing:** Rights holders grant peblhub a distribution license. Researchers pay a per-administration fee or subscription. Peblhub handles payment, usage metering, and royalty reporting. Rights holders receive a new distribution channel with verified licensing — something no other survey platform currently offers in a research context.

Content protection is legal (terms of service, license agreement at checkout) rather than technical — the same approach used by every major online survey platform. Determined users can always extract question text from the browser; the legal framework is what matters.

The open-source runner is intentionally made available so rights holders can inspect exactly what will be shown to participants, verify the scoring logic, and approve the implementation before it goes live.

---

## Scale Collection Strategy

### Phase 1: Seed with Existing Scales ✅

- ~~Migrate existing PEBL built-in scales~~ (done) ✅
- ~~Manually implement well-known public domain scales~~ (PHQ-9, GAD-7, PCL-5, AUDIT, CAGE, CESD, DASS-21/42, IPIP variants, RAND health surveys, and many more — 136 scales total) ✅
- Import confirmed public-domain/CC scales from PsyToolkit (partial — license review ongoing)

### Phase 2: Community Contributions

- Accept contributions via GitHub PR with validation CI
- Accept contributions via openScience.org with manual review
- Provide templates and the Scale Builder tool in PEBL for creating new definitions

### Phase 3: Publisher Partnerships

- Partner with scale publishers/rights holders for copyright-encumbered instruments
- Scale definition files are open; administration requires license verification
- Rights holder controls distribution terms; we provide the technical infrastructure

### Target: 200+ Scales

Including:
- Depression/anxiety: PHQ-9, GAD-7, BDI-II, HADS, DASS-21, CES-D, STAI
- Personality: Big Five (BFI, NEO-FFI, TIPI), HEXACO, Dark Triad
- Well-being: SWLS, WHO-5, WEMWBS, PWB, SF-36
- Cognitive: MoCA, MMSE, ACE-III (licensed), CRT
- Usability: SUS, UMUX, AttrakDiff, UEQ, NASA-TLX
- Clinical: PCL-5, AUDIT, CAGE, PSQI, ISI, ESS
- Education: Grit, Mindset, Academic Motivation, SRL
- Organizational: Job Satisfaction, Burnout (MBI), Work Engagement (UWES)
- Phenx scales which inlude 488 'freely distrubutable' questionnaires.
---

## Implementation Priorities

### Completed

- ~~All export converters (Qualtrics, QTI, REDCap, LimeSurvey, PsyToolkit)~~ ✅
- ~~Import converters (PsyToolkit, Qualtrics)~~ ✅
- ~~Resolve format naming~~ (done — OpenScales / OSD) ✅
- ~~Scale Builder UI in PEBL launcher (C1–C9, S1, S2, S4, A1)~~ ✅
- ~~ScaleRunner.pbl runtime (all question types, section randomization, branching, parameter-driven visibility and branching, progress indicator, type hints)~~ ✅
- ~~`runner/scale-runner.js`~~ — all question types, visible_when, S2/S3/S4/A1, scoring, data upload, peblTestComplete event, progress indicator ✅
- ~~`runner/server/collect.php`~~ — minimal self-hosting data collection endpoint ✅
- ~~Parameters (C8)~~ — text substitution, visibility conditions, branch routing; Scale Builder has add/edit/delete with type and options ✅
- ~~Scale library~~ — 136 scales across mood, anxiety, personality, cognition, substance use, clinical, technology, and more ✅
- ~~Peblhub chain integration~~ — `item_type: "scale"` in chain config; OSD content served from frozen snapshot; PEBL runner uses `FS.writeFile()` injection; JS runner loaded directly; both fire `peblTestComplete` on completion ✅

### Immediate

1. **Peblhub scale library UI** — browse/search OSD catalog, add scale to chain, private workspace upload for researcher-owned OSD files
2. Audit existing 136 scales for licensing tier (confirm Tier 1 vs. should-be-ghost-listed)

### Short-term (weeks)

3. **Within-section randomization UI** — S4 `randomize` on section markers survives round-trip but is not editable in builder; add to Sections tab
7. Add remaining priority scales: SWLS, WHO-5, WEMWBS, BDI-II, STAI, NASA-TLX, UWES, MBI (where openly licensed)
8. Verify PsyToolkit scale licenses and import eligible ones

### Medium-term (months)

9. **Scoring script generation** — new tool (`tools/generate_scoring_scripts.py`) that reads a scale's embedded scoring definition (from `definition.scoring` in the OSD, or a sidecar `.scoring.json` where present) and emits ready-to-use analysis syntax in R (`mutate`/`rowSums`/`rowMeans`), SPSS (`COMPUTE`), and Python/pandas. Reverse coding expressed as `(max + min) - x`; composite scores built from subscale results. Most scales embed scoring directly in the OSD rather than a sidecar file, so the generator must handle both sources.

10. Web-based conversion service on peblhub.online
11. Ghost-listing system for Tier 2 scales in hub UI
12. Proprietary scale licensing infrastructure (access control, usage metering, royalty reporting)
13. QTI 2.1 backward-compatibility flag
14. Runner Phase 3 — accessibility (ARIA), RTL language support, custom themes
15. Response option randomization (S5) — `randomize_options` on multi/multicheck items

### Long-term

15. Rights holder partnership program (MEQ, commercial assessments)
16. DOI-based scale import (resolve via CrossRef/DataCite, archive locally)
17. Balanced branch assignment (A1 balanced method — requires server-side participant counter)
18. Computed variables (S7) — runtime expression evaluation for derived scores *completed
19. Community growth and governance

---

## Scale Builder / ScaleRunner Implementation Status

Tracks which spec features are implemented in the PEBL launcher Scale Builder UI, the ScaleRunner.pbl desktop runtime, and the scale-runner.js web runtime.

| Feature | Spec ref | Scale Builder UI | ScaleRunner.pbl | scale-runner.js | Notes |
|---------|----------|-----------------|-----------------|-----------------|-------|
| Scale metadata (`scale_info`) | C1 | ✅ | ✅ | ✅ | |
| Question types: likert, vas, grid, short, long, multi, multicheck, inst | C2 | ✅ | ✅ | ✅ | |
| Per-question `random_group` | C2 | ✅ | ✅ | ✅ | |
| Reverse coding (`item_coding: -1`) | C3 | ✅ | ✅ | ✅ | |
| Dimensions and subscale scoring | C3 | ✅ | ✅ | ✅ | mean_coded, sum_coded |
| Translations (i18n) | C4 | ✅ | ✅ | ✅ | Multi-language, OSD bundle format |
| Section markers (`type: section`) | C5 | ✅ | ✅ | ✅ | Add/edit/move/delete in UI |
| Required vs. optional items | C6 | ✅ | ✅ | ✅ | Per-item and scale-level default |
| Dimension selection (`enabled_param`, `visible_when`) | C7 | ✅ | ✅ | ✅ | |
| Parameters (C8) — text substitution `{param_name}` | C8/S2 | ✅ | ✅ | ✅ | **Completed 2026-02-24.** Scale Builder: add/edit/delete params with type (string, integer, float, boolean, choice) and options. Runner: BuildParamReplist → PreprocessStrings; key lowercased to match `{param_name}` tokens in translation strings. |
| Parameters (C8) — drive `visible_when` conditions | C8/S1 | ✅ | ✅ | ✅ | `"parameter": "age_group"` source in EvaluateCondition; works for both item-level and section-level visibility. |
| Parameters (C8) — drive branch selection | C8/A1 | ✅ | ✅ | ✅ | `method: "parameter"` in branch group selects arm whose `id` matches parameter value. Fallback to random if no match. |
| Input validation constraints | C9 | ✅ | ✅ | ✅ | min/max length, word count, numeric range, pattern, min/max selected |
| Question-level `visible_when` skip logic | S1 | ✅ | ✅ | ✅ | |
| Section-level `visible_when` skip logic | S1 | ✅ | ✅ | ✅ | Condition cascades to all questions until next section marker. |
| Dimension-level `visible_when` | S1 | ✅ | ✅ | ✅ | |
| Pattern substitution `{param_name}` in strings | S2 | ✅ | ✅ | ✅ | See C8 row above. |
| Answer piping `{answer.id}` / `{answer.alias}` | S3 | ✅ | ✅ | ✅ | Question editor: answer alias field. Runtime: PipeAnswers() resolves via gAliasMap. |
| Within-section randomization (`randomize` on section marker) | S4 | ❌ | ✅ | ✅ | Survives round-trip in builder via raw JSON; not editable in UI. |
| Top-level `randomize_sections` | S4 | ✅ | ✅ | ✅ | Sections tab: toggle + per-section Fixed checkbox. ShuffleSectionOrder() respects fixed list. |
| Response option randomization (`randomize_options`) | S5 | ❌ | ❌ | ❌ | Deferred |
| Immediate feedback (correct/explanation keys) | S6 | ❌ | ❌ | ❌ | Deferred |
| Computed variables (`computed` block) | S7 | ❌ | ❌ | ❌ | Deferred |
| Consent/screening gates | S8 | ✅ | ✅ | ✅ | Question editor: gate checkbox, operator, value, termination message. Runtime: gate triggers termination with configurable message. |
| Section timing (`time_limit_seconds`) | S9 | ❌ | ❌ | ❌ | Explicitly deferred — not planned |
| Norms / interpretation thresholds | S10 | ❌ | ❌ | ❌ | Deferred |
| Random branching / A/B assignment (random method) | A1 | ✅ | ✅ | ✅ | Sections tab: branch group editor. Runtime: uniform random arm selection; chosen arms logged in pooled CSV as `{group_id}_arm` columns. |
| Branch selection by parameter (parameter method) | A1 | ✅ | ✅ | ✅ | **Completed 2026-02-24.** Arm id matched against parameter value; fallback to random. |
| Branch selection balanced across participants | A1 | ❌ | ❌ | ❌ | Deferred — requires persistent server-side counter; not appropriate as a runner-only spec feature |
| Item sampling from pool | A2 | ❌ | ❌ | ❌ | Deferred |
| Looping / iteration (`loop_over` on section) | A3 | ❌ | ❌ | ❌ | Deferred |
| Scale composition / batteries | A4 | ❌ | ❌ | ❌ | Deferred |
| Rank/order response type | A5 | ❌ | ❌ | ❌ | Deferred |
| Audio / video media | A6 | ❌ | ❌ | ❌ | Deferred |
| Pre-population / defaults from external data | A7 | ❌ | ❌ | ❌ | Deferred |

---

## Technical Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| QTI version | 3.0 (with potential 2.1 flag) | Current standard; HTML5-native; 2.1 downgrade is mechanical |
| Qualtrics format | Advanced TXT (not QSF) | Simpler, documented, sufficient for export |
| REDCap format | Data Dictionary CSV | Native import format; supports calc fields for scoring |
| XML generation | `xml.etree.ElementTree` | No external dependencies; sufficient for QTI |
| Import converters | PsyToolkit only (for now) | Only platform with a meaningful pool of existing scales |
| File extension | `.json` (no custom extension) | It's JSON; custom extensions create tooling friction |
| Naming | "OpenScales" project, "OSD" format | Avoids collision with Open Science Framework |
