# Open Scale Definition (OSD) Specification v1.0.11

*Part of the [OpenScales Project](README.md)*

A runner-agnostic JSON format for defining psychological scales, questionnaires, and survey instruments.

## Overview

The Open Scale Definition format uses a **two-file architecture**:

1. **Definition file** (`{code}.json`) — Structure, metadata, items, scoring logic
2. **Translation files** (`{code}.{lang}.json`) — All user-facing text, one file per language

This separation enables multi-language support without duplicating structural information.

## Conformance Levels

Features are organized into three tiers:

| Tier | Requirement | Description |
|------|------------|-------------|
| **Core** | MUST | Required for all conforming runners |
| **Standard** | SHOULD | Recommended for full-featured runners |
| **Advanced** | MAY | Optional for specialized use cases |

A runner declares its conformance level. When a scale uses features beyond the runner's level, the runner SHOULD warn the user and degrade gracefully (e.g., skip unsupported features rather than failing).

---

## File Structure

```
{code}/
  {code}.json           — Scale definition (required)
  {code}.en.json        — English translation (recommended)
  {code}.{lang}.json    — Additional translations (optional)
   -or-
   {code}.osd           — .json file containing scale definition and translations files.
  
  -optional-
  LICENSE.txt           — License evidence / permissions grant (optional)
  screenshot.png        — Preview image (optional, auto-generated)
  images/               — Referenced images (optional)
  audio/                — Referenced audio files (optional)
  video/                — Referenced video files (optional)
  
  
```

Language codes follow [BCP 47](https://www.rfc-editor.org/info/bcp47) (e.g., `en`, `de`, `es`, `zh-Hans`).

---

## CORE — Required for All Conforming Runners

### C1. Scale Metadata (`scale_info`)

Every definition MUST include a `scale_info` object.

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Full display name of the scale |
| `code` | string | Unique short identifier (used in filenames) |

**Optional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `abbreviation` | string | Common abbreviation (e.g., "SUS", "PHQ-9") |
| `description` | string | Brief description of what the scale measures |
| `citation` | string | Full academic citation with DOI |
| `license` | string | Short license label shown as a pill/badge in browse views. Keep brief — one to four words. See **Recommended license values** below. |
| `license_explanation` | string | Full license terms or usage conditions displayed on the scale detail page. Should capture the substance of the license grant (who granted it, what they said, when) so the record is self-contained even if external URLs go dead. |
| `license_url` | string | URL documenting the license terms or providing evidence for the `license` claim (e.g., rights holder's download page, press release, CC deed). Supplements `license_explanation` — do not rely on this URL as the sole record. |
| `version` | string | Scale definition version |
| `url` | string | URL for more information |

**Example:**

```json
{
  "scale_info": {
    "name": "Patient Health Questionnaire-9",
    "code": "PHQ9",
    "abbreviation": "PHQ-9",
    "description": "9-item depression screening tool",
    "citation": "Kroenke, K., Spitzer, R. L., & Williams, J. B. (2001). The PHQ-9. Journal of General Internal Medicine, 16(9), 606-613.",
    "license": "free to use",
    "license_explanation": "Pfizer released all PHQ and GAD-7 screeners without copyright restriction. The phqscreeners.com terms of use state: 'Content found at the PHQ Screeners site is expressly exempted from Pfizer's general copyright restrictions; content found on the PHQ Screeners site is free for download and use as stated within the PHQ Screeners site.'",
    "license_url": "https://www.phqscreeners.com/",
    "version": "1.0",
    "url": "https://www.phqscreeners.com/"
  }
}
```

#### Recommended `license` values

Use these standardized values where applicable:

| Value | When to use |
|-------|-------------|
| `CC BY 4.0` (or 3.0, 2.0) | Creative Commons Attribution — cite the specific version |
| `CC BY-NC` | Creative Commons Attribution-NonCommercial |
| `CC0` | Creative Commons Zero — explicit public domain dedication |
| `Public Domain` | U.S. government work, or the rights holder explicitly declared it public domain (document the declaration in `license_explanation`) |
| `free to use` | Rights holder has explicitly released for unrestricted use without a formal PD or CC dedication (e.g., Pfizer's PHQ/GAD-7 release) |
| `free for research use` | Free for research/academic/clinical use; commercial use may require permission |
| `author website distribution` | Author distributes freely via their website but no explicit license grant |
| `published measure` | Published in literature; no explicit license; restricted by default |

When using `Public Domain`, document the basis in `license_explanation` — either that it is a U.S. government work, or cite the specific statement where the author/rights holder dedicated it to the public domain.

#### Per-scale license evidence files

Each scale directory MAY contain a `LICENSE.txt` (or `LICENSE.pdf`) file with:
- The license terms or permissions grant text
- Source URL where the terms were found
- Date accessed

This provides a durable local record of the license evidence, independent of external URLs that may go offline. For scales with formal permission letters (e.g., a signed PDF), `LICENSE.pdf` is acceptable.

#### Implementation Metadata (`implementation`)

The `definition` object MAY include an `implementation` object documenting who created the `.osd` file and licensing terms for the implementation itself. This is distinct from `scale_info.license`, which covers the scale content (items, scoring, norms). The implementation license covers the specific digital encoding in OSD format.

| Field | Type | Description |
|-------|------|-------------|
| `author` | string | Name of the person or organization who created the .osd file |
| `organization` | string | Affiliated organization (e.g., "OpenScales Project") |
| `date` | string | Date the implementation was created or last updated (ISO 8601) |
| `license` | string | License for the .osd implementation (e.g., "CC BY 4.0") |
| `license_url` | string | URL for the implementation license |
| `notes` | string | Any additional notes about the implementation |

**Example:**

```json
{
  "definition": {
    "scale_info": { ... },
    "implementation": {
      "author": "Shane T. Mueller",
      "organization": "OpenScales Project",
      "date": "2026-03-15",
      "license": "CC BY 4.0",
      "license_url": "https://creativecommons.org/licenses/by/4.0/"
    },
    "items": [ ... ]
  }
}
```

> **Note:** The implementation license does not override the scale content license. A scale whose items are under `published measure` restrictions retains those restrictions regardless of the implementation license. The implementation license applies to the structural encoding: the JSON organization, computed variables, scoring logic, and any original instructional text added by the implementer.

### C2. Item Types

The format defines the following item types:

| Type | Purpose | Key fields |
|------|---------|------------|
| `inst` | Instruction/information display | — |
| `section` | Section boundary marker | `title_key` (optional) |
| `likert` | Likert rating scale | `likert_points`, optional `likert_labels` |
| `vas` | Visual analog scale | `min`, `max`, `min_label`, `max_label` |
| `grid` | Matrix/grid of sub-items | `rows`, `columns` |
| `multi` | Multiple choice (single select) | `options` |
| `multicheck` | Multiple choice (multi select) | `options` |
| `short` | Short text entry | `maxlength` |
| `long` | Long text entry | `maxlength`, `rows`, `cols` |

> **Deprecated types:** `image` and `imageresponse` are retained for backward compatibility but should not be used in new scales. Use `inst` with an embedded `<img>` (see C4 Media Embedding) to display an image, and `short` or `long` with an embedded `<img>` to collect a response to an image stimulus.

#### Common Item Fields

Every item MUST have:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier within the scale |
| `type` | string | One of the types listed above |
| `text_key` | string | Key into the translation file for item text (omit only for `section`) |

Optional common fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dimension` | string | `null` | ID of the dimension this item belongs to |
| `random_group` | integer | see note | Randomization group. `0` = fixed position; `1`+ = shuffle within that numbered group when randomization is active. Group numbers are **scoped to the item's section** — a `random_group: 1` in one section and a `random_group: 1` in another section shuffle independently and never cross section boundaries. **Defaults:** `inst` items and items with `visible_when` default to `0` (fixed); all other items default to `1` (shuffled). When a section has its own `randomize` field, `random_group: 0` still pins the item, but higher group numbers are ignored — all non-pinned items form a single shuffle pool (see S4). |
| `required` | boolean | varies | Whether the item must be answered (see C6) |
| `question_head` | string | `null` | Translation key for a question stem displayed above the item text. Intended for blocks of items that share a common introductory question (e.g. "In the past month, how often did you..."). Overrides the scale-level `likert_options.question_head` for this item. Runners currently display the head on every item; future multi-item-per-page runners MAY suppress repetition when consecutive items share the same head. |

#### `likert` Type

```json
{
  "id": "q1",
  "type": "likert",
  "text_key": "q1",
  "likert_points": 5,
  "likert_labels": ["likert_1", "likert_2", "likert_3", "likert_4", "likert_5"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `likert_points` | integer | Number of response options |
| `likert_labels` | array of strings | Translation keys for each point label (optional, overrides scale-level labels) |
| `likert_min` | integer | Minimum numeric value (default: 1) |
| `likert_max` | integer | Maximum numeric value (default: `likert_points`) |
| `likert_reverse` | boolean | When `true`, response buttons are displayed right-to-left (highest value on the left, lowest on the right). The **stored value is unchanged** — a participant clicking the leftmost button still stores `likert_max`. Labels are always shown beside their corresponding value regardless of display order. Default: `false`. |

**`likert_reverse` example** — QOLIE-89 item 2 (quality-of-life ladder, 10 at left down to 0 at right):

```json
{
  "id": "qolie89_2",
  "type": "likert",
  "text_key": "qolie89_2",
  "likert_points": 11,
  "likert_min": 0,
  "likert_reverse": true,
  "likert_labels": ["qolie89_qol0", null, null, null, null, null, null, null, null, null, "qolie89_qol10"]
}
```

`likert_labels` is indexed by value offset from `likert_min` (i.e., index 0 = value 0, index 10 = value 10), regardless of display order.

**ScaleBuilder note:** When editing a Likert item, ScaleBuilder SHOULD display a **"Reverse display order"** checkbox (off by default). When checked, the live preview of the item should update immediately to show buttons in descending order (max → min left-to-right) so the author can confirm the layout matches the paper instrument.

**Scale-level Likert defaults** can be set via `likert_options`:

```json
{
  "likert_options": {
    "points": 5,
    "min": 1,
    "max": 5,
    "labels": ["likert_1", "likert_2", "likert_3", "likert_4", "likert_5"],
    "question_head": "question_head"
  }
}
```

The `question_head` references a translation key for a question stem or instructions displayed above scored items (`likert`, `vas`, `grid`, `multi`, `multicheck`). It is particularly useful when a block of items shares a common introductory question. An item-level `question_head` field (see Common Item Fields) overrides this scale-level default for individual items. `question_head` is optional; omit it (or omit `likert_options` entirely) for scales where each item is self-contained.

#### `vas` Type

```json
{
  "id": "q1",
  "type": "vas",
  "text_key": "q1",
  "min": 0,
  "max": 100,
  "min_label": "vas_low",
  "max_label": "vas_high"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `min` | number | Minimum value |
| `max` | number | Maximum value |
| `min_label` | string | Translation key for low-end anchor |
| `max_label` | string | Translation key for high-end anchor |
| `anchors` | array of objects | Optional named anchor points along the scale (see below) |
| `orientation` | string | `"horizontal"` (default) or `"vertical"` |

**Named anchors:** In addition to (or instead of) `min_label` / `max_label`, a VAS may specify intermediate anchor points using the `anchors` array. Each anchor is an object with `value` (numeric position on the scale) and `label` (translation key for the anchor text). Anchors are displayed as text labels centered at their position along the slider.

```json
{
  "id": "q1",
  "type": "vas",
  "text_key": "q1",
  "min": 1,
  "max": 100,
  "anchors": [
    {"value": 1, "label": "strongly_disagree"},
    {"value": 25, "label": "somewhat_disagree"},
    {"value": 50, "label": "neither"},
    {"value": 75, "label": "somewhat_agree"},
    {"value": 100, "label": "strongly_agree"}
  ]
}
```

When `anchors` is present, `min_label` and `max_label` are ignored (the anchors at the endpoints replace them). Runners SHOULD render anchor labels in text boxes that wrap and are centered at the corresponding position on the slider. When `orientation` is `"vertical"`, runners SHOULD provide more space for anchor labels alongside the slider. A vertical orientation is recommended when there are many anchors or when anchor labels are long, to avoid horizontal crowding.

**Test case:** The WCHS (Words Can Harm Scale) uses a 1–100 VAS with 5 named anchors at positions 1, 25, 50, 75, and 100 (Strongly disagree → Strongly agree).

#### `grid` Type

```json
{
  "id": "grid1",
  "type": "grid",
  "text_key": "grid1",
  "rows": ["row1_key", "row2_key", "row3_key"],
  "columns": ["col1_key", "col2_key", "col3_key"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rows` | array of strings | Translation keys for row labels (sub-items) |
| `columns` | array | Column definitions — response options for the grid (see below) |

**Column formats:** Each entry in `columns` may be either:

- A **plain string** — translation key for the column label. The stored value is the 1-based column index (1, 2, 3, ...). This is the default for backward compatibility.
- An **object** with `text_key` and `value` — identical syntax to `multi` options. The stored value is the explicit `value` field.

```json
"columns": ["col1_key", "col2_key", "col3_key"]
```

is equivalent to:

```json
"columns": [
  {"text_key": "col1_key", "value": 1},
  {"text_key": "col2_key", "value": 2},
  {"text_key": "col3_key", "value": 3}
]
```

Explicit values are useful when column responses map to non-sequential or non-1-based scores. For example, a Yes/No problem checklist:

```json
"columns": [
  {"text_key": "no_label", "value": 0},
  {"text_key": "yes_label", "value": 1}
]
```

Or a 4-option grid where only one response scores a point (binary scoring):

```json
"columns": [
  {"text_key": "definitely_agree", "value": 1},
  {"text_key": "slightly_agree", "value": 1},
  {"text_key": "slightly_disagree", "value": 0},
  {"text_key": "definitely_disagree", "value": 0}
]
```

Grid sub-item responses are stored as a space-separated string of column values (e.g., `"1 0 1 0 1"`) and expanded during scoring to `{gridId}_1`, `{gridId}_2`, etc. The expanded values are the column `value` (explicit or 1-based index).

**Adaptive rendering:** Grid presentation should adapt to the available viewport. On wide screens (desktop/tablet), runners may render the full matrix layout with all rows and columns visible simultaneously, and may paginate long grids across pages. On narrow screens (mobile/phone), runners should present each row as an independent single question — showing only the column labels and the one row's response options at a time — to avoid horizontal scrolling and maintain usability.

#### `multi` and `multicheck` Types

Each option may be specified as an object with explicit `value` and `text_key`, or as a plain string (shorthand when the stored value and translation key are the same):

```json
{
  "id": "q1",
  "type": "multi",
  "text_key": "q1",
  "options": [
    {"value": "a", "text_key": "q1_option_a"},
    {"value": "b", "text_key": "q1_option_b"},
    {"value": "c", "text_key": "q1_option_c"}
  ]
}
```

Plain-string shorthand (stored value = translation key):

```json
"options": ["q1_option_a", "q1_option_b", "q1_option_c"]
```

Object options with numeric values (useful when the value is used directly in scoring):

```json
"options": [
  {"value": 5, "text_key": "health_excellent"},
  {"value": 4, "text_key": "health_very_good"},
  {"value": 3, "text_key": "health_good"},
  {"value": 2, "text_key": "health_fair"},
  {"value": 1, "text_key": "health_poor"}
]
```

| Field | Type | Description |
|-------|------|-------------|
| `options` | array | Each entry is either an object `{"value": ..., "text_key": "..."}` or a plain string. A plain string is treated as both the stored response value and the translation key. The `value` in an object may be a string or number; numeric values are useful when the stored value is also the scoring value (e.g. a 0–5 ordinal scale). |

For `multi`, exactly one option is selected. For `multicheck`, zero or more options may be selected.

#### `short` and `long` Types

```json
{
  "id": "q1",
  "type": "short",
  "text_key": "q1",
  "maxlength": 100
}
```

| Field | Type | Description |
|-------|------|-------------|
| `maxlength` | integer | Maximum character count |
| `rows` | integer | Number of visible rows (`long` type only) |
| `cols` | integer | Number of visible columns (`long` type only) |


See **C4 Media Embedding** for the preferred approach.

### C3. Dimensions and Scoring

#### Dimensions

Dimensions group items into subscales:

```json
{
  "dimensions": [
    {
      "id": "extraversion",
      "name": "Extraversion",
      "abbreviation": "E",
      "description": "Tendency toward sociability and positive emotionality"
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique identifier |
| `name` | string | yes | Display name |
| `abbreviation` | string | no | Short label |
| `description` | string | no | What the dimension measures |

Questions reference dimensions via their `dimension` field.

#### Scoring

Implementing scoring blocks is a core ability expected of all scale runners. A runner that cannot compute dimension scores cannot administer a scored scale. Scoring blocks use a small vocabulary of declarative methods — no expression evaluator is required. This keeps the Core conformance level achievable for minimal runners (e.g., embedded survey tools, offline PEBL scripts) while still supporting the full range of scoring patterns found in published psychological scales.

Additional runtime functionality — thresholding a score, deriving a risk flag, computing a BMI from height and weight — may be expressed using computed variables (S7). Computed variables require an expression evaluator and are therefore Standard conformance. The two mechanisms are complementary and flow in one direction: items → scoring blocks → computed variables. A scoring block may not reference a computed variable; a computed variable may reference `score.*`.

The `scoring` object defines how dimension scores are computed:

```json
{
  "scoring": {
    "extraversion": {
      "method": "mean_coded",
      "items": ["q1", "q2", "q3", "q4", "q5"],
      "description": "Mean extraversion score (1-5 scale)",
      "item_coding": {
        "q1": 1,
        "q2": -1,
        "q3": 1,
        "q4": -1,
        "q5": 1
      }
    }
  }
}
```

**Scoring methods:**

| Method | Description |
|--------|-------------|
| `mean_coded` | Mean of coded item values |
| `sum_coded` | Sum of coded item values |
| `sd` | Standard deviation of coded item values |
| `weighted_sum` | Weighted sum — Σ(weight × value) (requires `weights` object) |
| `weighted_mean` | Weighted mean — Σ(weight × value) ÷ Σ(weights) (requires `weights` object) |
| `sum_correct` | Count of correct answers (requires `correct_answers` object) |
| `max` | Maximum value across inputs |
| `min` | Minimum value across inputs |

**Reverse coding formula:** `reversed = (min + max) - response`

Where `min` and `max` are the response range for the item's type.

**Value mapping (`value_map`):** For non-linear recoding that cannot be expressed as simple reverse coding, use the `value_map` field. Each key is an item ID (or `"default"` for a default that applies to all items in the dimension); its value is an **array** where position `i` gives the recoded value for raw response `min + i`. `value_map` is applied *before* `item_coding`, so an item can be both remapped and then reverse-coded if needed. Per-item entries override the `"default"` default.

*RFQ example — same items, different recoding per subscale (7-point Likert, min=1):*
```json
{
  "scoring": {
    "RFQ_C": {
      "method": "mean_coded",
      "items": ["RFQ001", "RFQ002", "RFQ003", "RFQ004", "RFQ005", "RFQ006"],
      "item_coding": { "RFQ001": 1, "RFQ002": 1, "RFQ003": 1, "RFQ004": 1, "RFQ005": 1, "RFQ006": 1 },
      "value_map": {
        "default": [3, 2, 1, 0, 0, 0, 0]
      }
    },
    "RFQ_U": {
      "method": "mean_coded",
      "items": ["RFQ002", "RFQ004", "RFQ005", "RFQ006", "RFQ007", "RFQ008"],
      "item_coding": { "RFQ002": 1, "RFQ004": 1, "RFQ005": 1, "RFQ006": 1, "RFQ007": 1, "RFQ008": 1 },
      "value_map": {
        "default":      [0, 0, 0, 0, 1, 2, 3],
        "RFQ007": [3, 2, 1, 0, 0, 0, 0]
      }
    }
  }
}
```

Array index 0 corresponds to response value `min` (here 1), index 1 to `min+1` (here 2), etc. So for RFQ_C: response 1→3, 2→2, 3→1, 4–7→0. In the RFQ_U subscale, RFQ007 ("I always know what I feel") uses a per-item override with the opposite recoding pattern.

**Additional scoring fields:**

| Field | Type | Description |
|-------|------|-------------|
| `items` | array of strings | Item IDs to include. For `mean_coded`, `sum_coded`, `sd`, `max`, and `min`: only items listed in `item_coding` with a non-zero value are included in the computed score. |
| `scores` | array of strings | Dimension IDs whose already-computed scores are used as inputs. May be used instead of or alongside `items`. `item_coding` applies to score references just as it does to item references (supporting reverse-coded subscales). |
| `item_coding` | object | Per-item (or per-score) coding: `1` (forward), `-1` (reverse), `0` (exclude). Items and scores absent from `item_coding` are excluded. Using `0` explicitly is convenient when copying a full design vector. Coding is defined here in the scoring block — not on the item — so the same item can carry different codings in different dimensions. |
| `value_map` | object | Optional per-item response remapping. Keys are item IDs (or `"default"` for a default); values are **arrays** where position `i` gives the recoded value for raw response `min + i` (i.e., index 0 = the scale minimum). Applied *before* `item_coding`. When present for an item, the raw response is looked up in the array; if the index is in range, the mapped value replaces the raw value for scoring. This supports non-linear recoding schemes (e.g., collapsing upper Likert points to zero) that cannot be expressed with simple reverse coding. The same item may have different `value_map` entries in different dimensions. Per-item entries override the `"default"` default. |
| `weights` | object | Per-item (or per-score) weights for `weighted_sum` and `weighted_mean`. Keys are item or score IDs; values are numeric weights. Items absent from `weights` are excluded from the weighted calculation. |
| `correct_answers` | object | Per-item correct answers (for `sum_correct`) |
| `transform` | array of objects | Optional sequence of affine steps applied to the raw score after the scoring method is computed. See **Score Transforms** below. |
| `description` | string | Description of the score |

#### Score Transforms

The optional `transform` field applies a sequence of arithmetic operations to the raw score produced by the scoring method, yielding a transformed score. This supports the 0–100 rescaling, centering, and other linear conversions used by many published instruments (SF-36, WHOQOL-BREF, SUS, UEQ, etc.).

Each step in the array has two fields:

| Field | Type | Description |
|-------|------|-------------|
| `op` | string | Arithmetic operation: `"add"`, `"subtract"`, `"multiply"`, `"divide"` |
| `value` | number or string | Operand — either a literal number or a named statistic (see table below) |

Steps are applied in order; the output of each step feeds into the next.

**Named statistics available as `value`:**

These are computed from the scored item responses within the current scoring block (i.e., the actual coded values after reverse-coding, for the current participant). Runners MAY support these; in practice, using literal numeric constants is simpler and preferred.

| Name | Definition |
|------|-----------|
| `"mean"` | Mean of coded item values |
| `"sum"` | Sum of coded item values |
| `"sd"` | Standard deviation of coded item values (population SD, divide by *n*) |
| `"min"` | Minimum coded item value |
| `"max"` | Maximum coded item value |
| `"range"` | `max − min` of coded item values |
| `"n"` | Count of answered items included in the score |

In most cases, scale authors should use **literal numeric values** rather than named statistics. For example, to rescale a 10-item sum (range 10–50) to 0–100, use `subtract 10`, `divide 40`, `multiply 100` with literal numbers. This is clearer, portable across all runners, and does not require the runner to compute statistics at transform time.

**Examples:**

*WHOQOL-BREF physical domain — mean of 7 items (range 1–5), × 4, then rescale to 0–100:*
```json
"transform": [
  { "op": "multiply", "value": 4 },
  { "op": "subtract", "value": 4 },
  { "op": "multiply", "value": 6.25 }
]
```

*SF-36 physical functioning — sum of 10 items (range 10–30), rescale to 0–100:*
```json
"transform": [
  { "op": "subtract", "value": 10 },
  { "op": "divide",   "value": 20 },
  { "op": "multiply", "value": 100 }
]
```

*SUS — 25 × (mean − 1):*
```json
"transform": [
  { "op": "subtract", "value": 1 },
  { "op": "multiply", "value": 25 }
]
```

*UEQ — center 1–7 scale to −3…+3:*
```json
"transform": [
  { "op": "subtract", "value": 4 }
]
```

*Z-score using published population norms (literal constants):*
```json
"transform": [
  { "op": "subtract", "value": 50.2 },
  { "op": "divide",   "value": 10.3 }
]
```

**Runner implementation:** Before executing transform steps, the runner builds a variable map from the current scoring block's coded responses and item definitions. Each step resolves `value` as either the literal number or a lookup in the map, then applies the operation to the running value. No expression parser or evaluation stack is required — only sequential arithmetic on two numbers at a time.

**Interaction with `scores` inputs:** When a scoring block uses the `scores` field to take other dimensions' scores as inputs, the `transform` applies to the final aggregated value (after those inputs are combined), not to the individual input scores. The named statistics (`"mean"`, `"sd"`, etc.) refer to the item responses in the current block only; they are not defined when `items` is empty and `scores` is the sole input.

**`sd` scoring method vs. `"sd"` transform reference:** `"method": "sd"` produces the standard deviation of the coded item values as the primary score. The `"sd"` transform reference provides the same value as an operand within a transform step on a *different* scoring method (e.g., to normalize a mean score by its own item-level dispersion).

**Evaluation order:** When a scoring block uses `scores`, it depends on those dimensions being computed first. Runners MUST evaluate scoring blocks in dependency order. A circular reference (dimension A depends on B which depends on A) is a definition error; runners SHOULD report it and halt scoring.

**`max`/`min` and the `scores` field — QIDS example:**

Some scales score symptom domains as the worst (maximum) of several alternative items, then sum the domain scores. The QIDS-SR (Quick Inventory of Depressive Symptoms) is a canonical example: sleep disturbance is scored as the maximum of four sleep items; psychomotor change as the maximum of two items; and the total is the sum of nine such domain scores.

```json
{
  "scoring": {
    "sleep": {
      "method": "max",
      "items": ["item_falling_asleep", "item_sleep_night", "item_waking_up", "item_sleeping_too_much"],
      "item_coding": {
        "item_falling_asleep": 1, "item_sleep_night": 1,
        "item_waking_up": 1, "item_sleeping_too_much": 1
      }
    },
    "psychomotor": {
      "method": "max",
      "items": ["item_slowed_down", "item_restless"],
      "item_coding": {"item_slowed_down": 1, "item_restless": 1}
    },
    "QIDS_total": {
      "method": "sum_coded",
      "scores": ["sleep", "sad_mood", "appetite_weight", "concentration",
                 "self_view", "death_suicide", "interest", "energy", "psychomotor"],
      "description": "Sum of 9 symptom domain scores (0–27)",
      "norms": {
        "thresholds": [
          {"min": 0,  "max": 5,  "label_key": "norm_none"},
          {"min": 6,  "max": 10, "label_key": "norm_mild"},
          {"min": 11, "max": 15, "label_key": "norm_moderate"},
          {"min": 16, "max": 20, "label_key": "norm_severe"},
          {"min": 21, "max": 27, "label_key": "norm_very_severe"}
        ]
      }
    }
  }
}
```

**`weighted_mean` and `weighted_sum` — QOLIE-89 total example:**

Some scales produce a composite score as a weighted average of subscale scores, each of which has already been transformed to a common 0–100 range. The QOLIE-89 is a canonical example: 17 subscale scores (each 0–100) are combined using published weights, and the resulting composite is then converted to a T-score using normative population statistics.

```json
{
  "scoring": {
    "health_perceptions": {
      "method": "mean_coded",
      "items": ["hp1", "hp2", "hp3", "hp4", "hp5", "hp6"],
      "item_coding": { "hp1": -1, "hp2": 1, "hp3": -1, "hp4": 1, "hp5": -1, "hp6": 1 },
      "transform": [
        { "op": "subtract", "value": 1 },
        { "op": "divide",   "value": 4 },
        { "op": "multiply", "value": 100 }
      ]
    },
    "overall_qol": {
      "method": "mean_coded",
      "items": ["oqol1", "oqol2"],
      "item_coding": { "oqol1": 1, "oqol2": 1 },
      "transform": [
        { "op": "subtract", "value": 1 },
        { "op": "divide",   "value": 9 },
        { "op": "multiply", "value": 100 }
      ]
    },
    "total": {
      "method": "weighted_mean",
      "scores": ["health_perceptions", "overall_qol"],
      "weights": {
        "health_perceptions": 0.10,
        "overall_qol": 0.09
      },
      "description": "Weighted composite (0–100), then T-score (population mean 67.9, SD 15.55)",
      "transform": [
        { "op": "subtract", "value": 67.9 },
        { "op": "divide",   "value": 15.55 },
        { "op": "multiply", "value": 10 },
        { "op": "add",      "value": 50 }
      ]
    }
  }
}
```

When `scores` are used as inputs to `weighted_mean` or `weighted_sum`, the value used for each score is its **transformed output** (i.e., after any `transform` steps defined on that dimension). This allows subscale 0–100 scores to feed directly into a composite without additional rescaling.

**Runner implementation:** For `weighted_sum`, compute Σ(weight_i × value_i) over all inputs present in `weights`. For `weighted_mean`, compute the same sum then divide by Σ(weight_i) over the same inputs. Inputs absent from the `weights` object are excluded entirely (not treated as weight 0). If all inputs are missing, the result is `null`.

**ScaleBuilder UI:** When `weighted_sum` or `weighted_mean` is selected as the scoring method, ScaleBuilder MUST show a weights editor alongside the items/scores list — a numeric input field next to each included item or score ID. The editor SHOULD display the current weight sum (for `weighted_mean`, also display the effective denominator). Weights default to `1` for newly added items. ScaleBuilder SHOULD warn if any weight is zero or negative.

**`sum_correct` example:**

```json
{
  "scoring": {
    "reflection": {
      "method": "sum_correct",
      "items": ["q1", "q2", "q3"],
      "correct_answers": {
        "q1": ["5", "five", "0.05"],
        "q2": ["5", "five"],
        "q3": ["47", "forty-seven"]
      }
    }
  }
}
```

Each key in `correct_answers` maps to an array of acceptable answers (case-insensitive matching recommended).

**Multiple answer categories (`answer_categories`):**

A single `short`-answer item can be scored into multiple dimensions by defining named answer categories. Each category maps item IDs to arrays of acceptable answers (using the same case-insensitive matching as `correct_answers`). A scoring block references a category via the `answer_category` field instead of (or alongside) `correct_answers`.

This enables instruments where a single free-text response is evaluated against different answer sets — e.g., counting correct answers in one dimension and counting specific intuitive-incorrect answers in another.

`answer_categories` is defined at the top level of `scoring` (a sibling of the dimension objects), and individual scoring blocks reference a category by name.

| Field | Type | Req? | Description |
|-------|------|------|-------------|
| `answer_categories` | object | no | Top-level container for named answer-category sets. Each key is a category name; each value is an object mapping item IDs to arrays of acceptable answer strings. |
| `answer_category` | string | no | In a scoring block: name of the `answer_categories` entry to use for matching. When present, the scoring block uses `sum_correct` against the referenced category's answers instead of `correct_answers`. If both `answer_category` and `correct_answers` are present, `answer_category` takes precedence. |

**Use case — CRT-2 (Thomson & Oppenheimer, 2016):** The Cognitive Reflection Test presents trick questions where the intuitive (incorrect) answer is predictable. A `"correct"` category counts right answers (measuring reflective thinking), while an `"intuitive"` category counts intuitive-lure answers (measuring susceptibility to cognitive bias). Both categories score the same `short`-answer items into separate dimensions.

```json
{
  "scoring": {
    "answer_categories": {
      "correct": {
        "q1": ["second", "2nd", "2"],
        "q2": ["8", "eight"],
        "q3": ["emily"],
        "q4": ["0", "zero", "none"]
      },
      "intuitive": {
        "q1": ["first", "1st", "1"],
        "q2": ["7", "seven"],
        "q3": ["june"],
        "q4": ["27", "twenty-seven"]
      }
    },
    "reflection": {
      "method": "sum_correct",
      "items": ["q1", "q2", "q3", "q4"],
      "answer_category": "correct",
      "description": "Correct responses reflecting analytic thinking (0-4)"
    },
    "intuitive_errors": {
      "method": "sum_correct",
      "items": ["q1", "q2", "q3", "q4"],
      "answer_category": "intuitive",
      "description": "Intuitive-lure responses indicating heuristic thinking (0-4)"
    }
  }
}
```

### C4. Translations (i18n)

Translation files are JSON objects with flat key-value pairs:

```json
{
  "question_head": "Rate your agreement with each statement.",
  "likert_1": "Strongly Disagree",
  "likert_2": "Disagree",
  "likert_3": "Neutral",
  "likert_4": "Agree",
  "likert_5": "Strongly Agree",
  "q1": "I enjoy meeting new people.",
  "debrief": "Thank you for completing this questionnaire."
}
```

**File naming:** `{code}.{lang}.json` (e.g., `PHQ9.en.json`, `PHQ9.es.json`)

**Rules:**
- Keys referenced by `text_key`, `likert_labels`, option `text_key`s, etc. MUST exist in the translation file
- Values may contain **HTML-lite**: `<b>`, `<i>`, `<br>`, `<a href="...">` — a safe subset of inline HTML
- A `LANGUAGE` key is optional but recommended for self-identification
- Runners MUST load the translation file matching the requested language, falling back to English if unavailable, then to the first available translation if English is also unavailable
- Runners may load English first and then load the primary language file, so that incomplete translations fall back to English.
- An English (`en`) translation is RECOMMENDED but not required. Scales without an English translation are valid; runners MUST handle their absence gracefully.

#### C4a. Media Embedding

Any item text value may embed **one image or media source** using a standard `<img>` tag:

```json
{
  "q_face": "How familiar does this face look?<img src=\"images/face01.jpg\" width=\"320\" align=\"center\">Rate your familiarity below."
}
```

Runners MUST split the text value on the first `<img>` tag and render three regions in order:

1. **Text above** — the substring before `<img`; rendered as HTML-lite
2. **Image** — the image itself, sized and aligned per attributes
3. **Text below** — the substring after the closing `>` of the `<img>` tag; rendered as HTML-lite

The response widget for the item type (Likert buttons, text input, etc.) is placed after all three regions, unchanged.

**Supported `<img>` attributes:**

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `src` | string | required | Path relative to the scale's `images/` directory, or a remote URL when `remote="true"` is also set |
| `width` | string | `"100%"` | CSS width — pixels (e.g., `"400"`) or percentage (e.g., `"80%"`) |
| `align` | string | `"center"` | Horizontal alignment: `left`, `center`, `right` |
| `alt` | string | `""` | Accessibility description |
| `remote` | string | `"false"` | Set to `"true"` to explicitly allow a remote URL in `src` |

**Remote media sourcing policy:**

By default, runners resolve `src` relative to the scale's local `images/` directory. This preserves reproducibility: a study snapshot bundles all required assets, and images remain available regardless of third-party server availability.

- **Images (and audio, when supported):** Remote URLs (matching `https?://`) are **blocked by default**. If `src` is a remote URL and `remote="true"` is not present, the runner MUST skip the image region (rendering only text above and below) and log a console warning.
- To use a remote image, set `remote="true"` on the tag: `<img src="https://example.com/img.jpg" remote="true">`.
- A scale may also set the parameter `allow_remote_media: true` to permit all remote images in that scale without per-tag `remote` attributes (see S0 Parameters).
- **Video (when supported):** Remote URLs are allowed by default, because self-hosting large video files is impractical.

**ScaleBuilder note:** When an author enters a remote image URL, ScaleBuilder SHOULD detect this and prompt: *"Remote images may become unavailable. Cache a local copy?"* Accepting downloads the image into the scale's `images/` directory and rewrites `src` to the local path.

**Rules:**
- Only the first `<img>` tag in a text value is processed as a media embed; subsequent tags are rendered as literal text
- If `src` is absent or the file cannot be loaded, the image region is silently omitted and text above/below are concatenated
- `<img>` is the only media tag supported at this conformance level; `<audio>` and `<video>` are reserved for future standard/advanced tiers
- Runners that do not support media embedding MUST skip the image region and still render the text above and below, joined without the image


### C5. Sections

Sections are **logical groupings** of items defined by placing a section marker inline in the `items` list. A marker of `"type": "section"` begins a new section; all items that follow belong to that section until the next section marker.

Section grouping controls randomization, skip logic, timing, looping, and branching, and optionally display. How a runner presents the items within a section (simultaneously on one screen, one at a time, or anything in between) is a runner decision — the spec defines logical structure, not layout. If possible, a runner may place all items in a section on the same page.


```json
{
  "items": [
    {
      "id": "inst1",
      "type": "inst",
      "text_key": "intro_text"
    },
    {
      "id": "sec_demographics",
      "type": "section",
      "title_key": "demographics_title"
    },
    {
      "id": "q1",
      "type": "short",
      "text_key": "q1"
    },
    {
      "id": "q2",
      "type": "multi",
      "text_key": "q2",
      "options": [...]
    },
    {
      "id": "sec_main",
      "type": "section",
      "title_key": "main_section_title"
    },
    {
      "id": "q3",
      "type": "likert",
      "text_key": "q3",
      "likert_points": 5
    }
  ]
}
```

**Section marker fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique identifier for this section (used in randomization and skip logic) |
| `type` | string | yes | Must be `"section"` |
| `title_key` | string | no | Translation key for an optional section heading |
| `revisable` | boolean | no | Default `true`. When `true`, runners that present items one at a time SHOULD provide a Back button allowing participants to revise their answers within this section. When `false`, responses are final once committed and runners MUST NOT show a Back button for items in this section. Back navigation cannot cross section boundaries regardless of this setting. Runners write this field only when `false`; omitting it implies `true`. When a participant returns to a previously answered item via Back, a runner CAN and SHOULD pre-fill the response widget with the previous answer and immediately enable the Next/Confirm button; however this is not required. |
| `visible_when` | condition | no | Skip the entire section (and all its items) when the condition is false. Evaluated once when the section marker is reached. See S1. |
| `randomize` | object | no | Randomize the order of items wihin randomization groups within this section. Currently supports `method: "shuffle"` with an optional `fixed` list of item IDs to keep in their original positions. When present, takes priority over the scale-level `shuffle_questions` parameter for this section. See S4. |

Additional section-control fields (`time_limit_seconds`, `loop_over`) are reserved for future Standard/Advanced features.

**Implicit first section:** Items appearing before the first section marker are in an implicit unnamed section. This section is always presented, never included in section-level randomization, and is `revisable: true` by default. To override any property of the implicit first section, place a section marker as the very first item in the `items` list.

**Backward compatibility:** If no section markers are present, all items are administered in order, each as its own implicit single-item section, and the whole scale is revisable by default.

### C6. Required vs. Optional

Per-question property controlling whether the participant must answer before advancing:

```json
{
  "id": "q1",
  "type": "likert",
  "text_key": "q1",
  "required": true
}
```

**Scale-level default:** A top-level `default_required` field (boolean) overrides type-based defaults for all questions in the scale:

```json
{
  "scale_info": { ... },
  "default_required": false,
  "questions": [ ... ]
}
```

**Precedence (highest to lowest):**
1. Per-question `required` field (explicit boolean)
2. Scale-level `default_required` field (boolean)
3. Type-based defaults (see table below)

**Defaults by type:**
| Type | Default | Notes |
|------|---------|-------|
| `likert` | required | Scored type |
| `vas` | required | Scored type |
| `multi` | required | Scored type |
| `grid` | required | Scored type |
| `multicheck` | required | Scored type |
| `imageresponse` | required | Scored type |
| `short` | optional | Text entry |
| `long` | optional | Text entry |
| `inst` | n/a | Display-only (always has NEXT) |
| `image` | n/a | Display-only (always has NEXT) |

**Runtime behavior:**
- Optional items display a SKIP or NEXT button alongside normal response controls
- Skipped items record `"NA"` as the response with actual elapsed RT (> 0)
- For `multicheck` when required, at least 1 option must be checked before NEXT is enabled
- For `short` and `long` when required, blank responses are rejected with a prompt
- For compound types (`vas_page`, `grid`), SKIP skips the entire compound question

**Translation key:** Runners SHOULD support a `skip_label` translation key for localizing the SKIP button text (default: `"SKIP"` or `*NEXT*`).

Runners MUST prevent advancing past a section until all required items in that section are answered.

### C7. Dimension Selection

Dimensions can be marked as selectable, allowing researchers to administer a subset of a multi-dimensional scale:

```json
{
  "dimensions": [
    {
      "id": "extraversion",
      "name": "Extraversion",
      "selectable": true,
      "default_enabled": true,
      "enabled_param": "do_extraversion"
    },
    {
      "id": "agreeableness",
      "name": "Agreeableness",
      "selectable": true,
      "default_enabled": true
    }
  ]
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `selectable` | boolean | `false` | Whether this dimension can be enabled/disabled |
| `default_enabled` | boolean | `true` | Whether enabled by default |
| `enabled_param` | string | `null` | Runtime parameter that controls this dimension |
| `visible_when` | object | `null` | Condition for showing all questions in this dimension. Uses the same condition syntax as question-level `visible_when` (S1). Evaluated dynamically during administration. |

When a dimension is disabled, all questions belonging to that dimension are skipped, and its scoring is omitted. Questions not assigned to any dimension are always shown.

### C8. Parameters

Runtime parameters let researchers customize scale behavior without editing the definition:

```json
{
  "parameters": {
    "system_name": {
      "type": "string",
      "default": "the system",
      "description": "Name of the system being evaluated"
    },
    "shuffle_questions": {
      "type": "boolean",
      "default": false,
      "description": "Randomize question order within sections"
    }
  }
}

For selectable dimensions (*C7*), these should be selectable by researchers automatically using the parameter-setting interface, and default to ON for all dimensions.

```

**Reserved parameter names** — runners give these names special treatment in addition to normal parameter substitution:

| Name | Type | Default | Effect |
|------|------|---------|--------|
| `shuffle_questions` | boolean | `false` | Randomize item order within randomization groups (see S4). When declared in an OSD, the declared default overrides the runner's built-in default. |
| `show_header` | boolean | `true` | Whether to display the scale title above the questionnaire. Set to `false` for scales where revealing the title would bias responses (e.g., scales measuring susceptibility or burnout administered as part of a larger battery). |

Scales that require specific behavior SHOULD declare these in their `parameters` block with the appropriate default so the platform uses the correct value without researcher configuration.

**Parameter types:**

| Type | Values | Description |
|------|--------|-------------|
| `string` | any string | Free text |
| `boolean` | `true`/`false` (or `0`/`1`) | Toggle |
| `integer` | whole numbers | Numeric integer |
| `number` | any number | Numeric (float) |
| `choice` | from `options` list | Constrained selection |

For `choice` type, include an `options` array:

```json
{
  "scale_version": {
    "type": "choice",
    "default": "full",
    "options": ["full", "short", "screening"],
    "description": "Which version of the scale to administer"
  }
}
```

### C9. Input Validation

Per-question validation rules for text entry and selection items. Validation is defined as a flat object on the question; **multiple constraints may coexist** on a single question, each checked independently and each with its own error message.

**Applicable types:** `short` and `long` for text constraints; `short` only for numeric and pattern constraints; `multicheck` for selection count constraints.

**Constraint fields:**

| Field | Applies to | Description |
|-------|-----------|-------------|
| `min_length` | `short`, `long` | Minimum character count |
| `max_length` | `short`, `long` | Maximum character count |
| `min_words` | `short`, `long` | Minimum word count |
| `max_words` | `short`, `long` | Maximum word count |
| `number_min` | `short` | Minimum numeric value (also restricts input to digits) |
| `number_max` | `short` | Maximum numeric value (also restricts input to digits) |
| `pattern` | `short` | Regular expression — response must match |
| `min_selected` | `multicheck` | Minimum number of options that must be checked |
| `max_selected` | `multicheck` | Maximum number of options that may be checked |

Each constraint has a paired `{field}_error` key naming a translation string for the error message shown when that constraint fails. If omitted, the runner displays a generic message.

**Example — multiple constraints on one question:**

```json
{
  "id": "age",
  "type": "short",
  "text_key": "age_question",
  "validation": {
    "number_min": 0,
    "number_min_error": "age_too_low",
    "number_max": 150,
    "number_max_error": "age_too_high"
  }
}
```

```json
{
  "id": "bio",
  "type": "long",
  "text_key": "bio_question",
  "validation": {
    "min_words": 10,
    "min_words_error": "bio_too_short",
    "max_length": 500,
    "max_length_error": "bio_too_long"
  }
}
```

```json
{
  "id": "hobbies",
  "type": "multicheck",
  "text_key": "hobbies_question",
  "options": ["hobby_reading", "hobby_sports", "hobby_music", "hobby_travel"],
  "validation": {
    "min_selected": 1,
    "min_selected_error": "hobbies_min",
    "max_selected": 3,
    "max_selected_error": "hobbies_max"
  }
}
```

```json
{
  "id": "code",
  "type": "short",
  "text_key": "code_question",
  "validation": {
    "pattern": "^[A-Z]{3}-\\d{4}$",
    "pattern_error": "code_format_error"
  }
}
```

**Evaluation order:** When multiple constraints are present, they are evaluated in the order listed in the table above (length before words before numeric before pattern before selection). The first failing constraint's error message is shown; remaining constraints are not checked until the current error is resolved.

**Word counting:** Word count is determined by splitting the response on whitespace and counting non-empty tokens.

**Numeric constraints:** When `number_min` or `number_max` is present, runners SHOULD restrict input to numeric characters only. An empty response satisfies numeric constraints (use `required` to enforce non-empty responses separately).

**Pattern matching:** The `pattern` value is a regular expression. An empty response satisfies the pattern constraint (use `required` separately). Runners that do not support regex MAY skip pattern validation and SHOULD warn the user.

**PEBL runner — pattern support:**

The PEBL ScaleRunner supports pattern validation via the built-in `RegexMatch(text, pattern)` function, which wraps the [tiny-regex-c](https://github.com/rurban/tiny-regex-c) library (public domain). Supported syntax:

- `.` `^` `$` `*` `+` `?` — standard metacharacters
- `[abc]` `[^abc]` `[a-z]` — character classes and ranges
- `\s` `\S` `\w` `\W` `\d` `\D` — shorthand classes
- `{n}` `{n,m}` `{n,}` `{,m}` — quantifiers
- `|` — alternation
- `(...)` — grouping

---

## STANDARD — Recommended for Full-Featured Runners

### S1. Conditional Logic / Skip Logic

Show or hide items or sections based on previous answers or parameters.

**Simple condition referencing a previous item's response:**

```json
{
  "id": "q5",
  "type": "likert",
  "text_key": "q5",
  "visible_when": {
    "item": "q1",
    "operator": "equals",
    "value": "Yes"
  }
}
```


**Operators:**

| Operator | Description |
|----------|-------------|
| `equals` | Exact match (string comparison) |
| `not_equals` | Not equal |
| `greater_than` | Numeric greater than |
| `less_than` | Numeric less than |
| `in` | Value is in list |
| `not_in` | Value is not in list |
| `is_answered` | Item has been answered |
| `is_not_answered` | Item has not been answered |

**Conditions on parameters:**

```json
{
  "visible_when": {
    "parameter": "show_followup",
    "operator": "equals",
    "value": true
  }
}
```

**Compound conditions:**

```json
{
  "visible_when": {
    "all": [
      {"item": "q1", "operator": "equals", "value": "Yes"},
      {"parameter": "show_followup", "operator": "equals", "value": true}
    ]
  }
}
```

Connectors: `all` (AND), `any` (OR).

**Section-level conditions:**

A `visible_when` field on a section marker controls the entire section:

```json
{
  "id": "sec_followup",
  "type": "section",
  "visible_when": {"item": "q1", "operator": "equals", "value": "Yes"}
}
```

All items following this marker (until the next section marker) are skipped when the condition is false. The condition is evaluated once when the section is reached.

### S2. Pattern Substitution / Templating

Insert parameter values into question text via `{param_name}` syntax in translation values:

```json
{
  "q1": "How easy is it to use {system_name}?",
  "q2": "I would recommend {system_name} to a colleague."
}
```

Combined with parameters (C8), this allows scales where the target system or task is configurable.

**Reserved substitution prefixes:**

| Prefix | Source | Example |
|--------|--------|---------|
| `{param_name}` or `{param.name}` | Parameter value | `{system_name}` |
| `{answer.id}` | Previous answer | `{answer.q5}` |
| `{score.dim}` | Computed score | `{score.PHQ_total}` |
| `{computed.name}` | Computed variable | `{computed.bmi}` |
| `{loop.var}` | Loop variable | `{loop.current_task}` |

### S3. Answer Piping

Reference previous answers in subsequent question text:

```json
{
  "q10": "You said your favorite activity is {answer.q5}. How often do you do it?"
}
```

The runner substitutes the participant's actual response. If the referenced question hasn't been answered (e.g., skipped), the runner should use a fallback.

**Answer aliases** provide semantic names:

```json
{
  "id": "q5",
  "type": "short",
  "text_key": "q5",
  "answer_alias": "favorite_activity"
}
```

Then use `{answer.favorite_activity}` instead of `{answer.q5}`.

### S4. Randomization

Control question ordering within sections, and section ordering within the scale.

#### Per-item randomization groups (`random_group`)

Every item carries a `random_group` integer (see C2). This is the primary mechanism for controlling shuffle behavior:

- `random_group: 0` — item stays in its defined position regardless of any shuffle setting
- `random_group: 1` — item shuffles with other group-1 items in the same section
- `random_group: 2`, `3`, … — independent pools; group 2 shuffles within itself, independently of group 1, etc.

Items with no explicit `random_group`: `inst` items and items with `visible_when` default to group 0 (fixed); all other items default to group 1.

This mechanism is activated by the scale-level `shuffle_questions` parameter (or by the section-level `randomize` field described below).

#### Section-level `randomize` field

For simple per-section shuffle — "shuffle everything in this section, pin a few items" — add `randomize` to the section marker:

```json
{
  "id": "sec_main",
  "type": "section",
  "randomize": {
    "method": "shuffle",
    "fixed": ["q1", "q6"]
  }
}
```

When a section marker has `randomize.method: "shuffle"`:
- All items in the section are shuffled into a **single pool** (higher `random_group` numbers are not used for independent sub-pools in this mode)
- Items are pinned (kept in place) if their `random_group` is `0`, **or** if their `id` appears in the `fixed` list — both methods are equivalent and can be combined
- The scale-level `shuffle_questions` parameter is ignored for this section; `randomize` on the section marker takes priority

The `fixed` list is a convenience alternative to setting `random_group: 0` on individual items. Use whichever is cleaner for the scale's structure.

**Randomization methods:**

| Method | Description | Implemented |
|--------|-------------|-------------|
| `shuffle` | Random order, optionally with `fixed` items pinned | ✓ |
| `blocks` | Shuffle within defined blocks, optionally shuffle block order | planned |
| `latin_square` | Counterbalanced ordering across participants | planned |
| `reverse` | Half of participants get reversed order | planned |

**Block randomization within a section:**

```json
{
  "id": "sec_main",
  "type": "section",
  "randomize": {
    "method": "blocks",
    "blocks": [["q1","q2","q3"], ["q4","q5","q6"]],
    "shuffle_blocks": true
  }
}
```

**Section-order randomization** — `randomize_sections` at the top level shuffles the order in which sections are administered. References section IDs (the `id` of each section marker):

```json
{
  "randomize_sections": {
    "method": "shuffle",
    "fixed": ["sec_intro", "sec_debrief"]
  }
}
```

The implicit first section (questions before any marker) is always fixed and never included in section-order randomization.

### S5. Response Option Randomization

Shuffle the order of options within a question:

```json
{
  "id": "q5",
  "type": "multi",
  "text_key": "q5",
  "options": [...],
  "randomize_options": true
}
```

### S6. Immediate Feedback

Show feedback after a response (for knowledge tests, training):

```json
{
  "id": "q1",
  "type": "multi",
  "text_key": "q1",
  "options": [
    {"value": "a", "text_key": "q1_a"},
    {"value": "b", "text_key": "q1_b"},
    {"value": "c", "text_key": "q1_c"}
  ],
  "correct": ["b"],
  "feedback": {
    "correct_key": "q1_correct_feedback",
    "incorrect_key": "q1_incorrect_feedback",
    "explanation_key": "q1_explanation"
  }
}
```

Feedback translation strings can use `{answer.q1}` for what they chose and `{correct.q1}` for the right answer.

### S7. Computed Variables

Computed variables are intermediate runtime values derived during administration. They complement scoring blocks (C3) but serve a different purpose: while scoring blocks produce the named, reportable outputs of a scale (dimensions visible in reports, with optional norms), computed variables are helper values used to drive administration logic — skip conditions, answer piping, eligibility gates, and in-scale feedback.

Typical uses:
- Deriving a boolean risk flag from a score (`score.PHQ_total >= 10`) for use in a `visible_when` condition or gate
- Computing a continuous variable from free-text responses (`answer.weight / (answer.height * answer.height)`) for eligibility screening or piping into question text
- Combining scores into a derived index that is not itself a primary scale output

Computed variables require an expression evaluator and are therefore Standard conformance. Runners that implement only Core conformance MUST ignore the `computed` block and still compute scoring blocks correctly. Additional functionality may be exposed by also supporting computed variables — for example, displaying an inline risk interpretation during debriefing, or enabling skip logic that depends on a running total.

**Data flow is one-directional:** items → scoring blocks → computed variables. A computed variable may reference `score.*`, `answer.*`, and other `computed.*` variables. A scoring block may not reference `computed.*`.

```json
{
  "computed": {
    "depression_risk": {
      "expression": "score.PHQ_total >= 10",
      "type": "boolean"
    },
    "bmi": {
      "expression": "answer.weight / (answer.height * answer.height)",
      "type": "number"
    }
  }
}
```

Computed variables may optionally include `norms` (identical structure to scoring block norms — see C3) for normative interpretation. When present, runners SHOULD display the norm label alongside the computed variable value in reports.

```json
{
  "computed": {
    "met_total": {
      "expression": "computed.met_vigorous + computed.met_moderate + computed.met_walking",
      "type": "number",
      "norms": {
        "thresholds": [
          {"min": 0, "max": 599, "label": "Inactive"},
          {"min": 600, "max": 2999, "label": "Minimally Active"},
          {"min": 3000, "max": 99999, "label": "HEPA Active"}
        ],
        "source": "IPAQ Scoring Protocol (ipaq.ki.se)"
      }
    }
  }
}
```

Computed variables can be referenced in `visible_when`, pattern substitution (`{computed.depression_risk}`), and `gate` conditions (S8).

**Real-world example — IPAQ MET scoring:**

The IPAQ (International Physical Activity Questionnaire) uses computed variables to calculate MET-minutes/week from raw item responses. Each activity domain multiplies days × minutes × a MET weight factor:

```json
{
  "computed": {
    "met_vigorous": {
      "expression": "answer.ipaq1 * answer.ipaq2 * 8.0",
      "type": "number"
    },
    "met_moderate": {
      "expression": "answer.ipaq3 * answer.ipaq4 * 4.0",
      "type": "number"
    },
    "met_walking": {
      "expression": "answer.ipaq5 * answer.ipaq6 * 3.3",
      "type": "number"
    },
    "met_total": {
      "expression": "computed.met_vigorous + computed.met_moderate + computed.met_walking",
      "type": "number"
    }
  }
}
```

This demonstrates computed variables with multiplication and cross-referencing (`met_total` references other computed variables). The raw scoring dimensions remain simple sums; the MET calculations live in `computed` where they can be referenced in reports and feedback.

### S8. Consent / Screening Gates

Terminate the scale based on a response:

```json
{
  "id": "consent",
  "type": "multi",
  "text_key": "consent_question",
  "options": [
    {"value": "yes", "text_key": "consent_yes"},
    {"value": "no", "text_key": "consent_no"}
  ],
  "gate": {
    "required_value": "yes",
    "terminate_message_key": "consent_declined_message"
  }
}
```

If the participant's answer doesn't match `required_value`, the scale ends with the message from `terminate_message_key`.

Supports `"operator"` for numeric thresholds (e.g., age screening):

```json
{
  "gate": {
    "operator": "greater_than",
    "value": 17,
    "terminate_message_key": "age_too_young"
  }
}
```

### S9. Timing Constraints

Time limits and minimum display times.

**Section-level timing** — add `time_limit_seconds` and `timeout_action` to a section marker:

```json
{
  "id": "sec_timed",
  "type": "section",
  "time_limit_seconds": 60,
  "timeout_action": "advance"
}
```

`time_limit_seconds` is a budget shared across all questions in the section. When the budget is exhausted, `timeout_action` determines what happens.

**Per-question timing:**

```json
{
  "id": "q1",
  "type": "likert",
  "text_key": "q1",
  "min_display_seconds": 3,
  "time_limit_seconds": 30
}
```

**Timeout actions:**

| Action | Description |
|--------|-------------|
| `advance` | Skip to next page/question |
| `submit` | Submit current answer |
| `warn` | Show warning, allow continuation |

### S10. Norms / Interpretation Thresholds

Reference data for score interpretation:

```json
{
  "scoring": {
    "PHQ_total": {
      "method": "sum_coded",
      "items": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9"],
      "norms": {
        "thresholds": [
          {"min": 0, "max": 4, "label_key": "norm_minimal"},
          {"min": 5, "max": 9, "label_key": "norm_mild"},
          {"min": 10, "max": 14, "label_key": "norm_moderate"},
          {"min": 15, "max": 19, "label_key": "norm_mod_severe"},
          {"min": 20, "max": 27, "label_key": "norm_severe"}
        ],
        "source": "Kroenke et al., 2001"
      }
    }
  }
}
```

Runners can display the interpretation label in reports and feedback.

---

## ADVANCED — Optional for Specialized Use Cases

### A1. Random Branching / A/B Assignment

The `branches` array defines one or more branch groups. Each group selects one arm from its list; sections in the selected arm are shown, sections in all other arms are hidden. Sections not referenced by any branch group are always shown.

A branch group is evaluated once at scale start, before any items are displayed.

**Structure:**

```json
{
  "branches": [
    {
      "id": "condition",
      "method": "random",
      "arms": [
        {"id": "A", "sections": ["sec_condition_a"]},
        {"id": "B", "sections": ["sec_condition_b"]}
      ]
    }
  ]
}
```

The items list still contains section markers for **all** arms; the runner hides the sections belonging to unchosen arms:

```json
{
  "items": [
    {"id": "sec_intro",       "type": "section"},
    {"id": "q_intro",         "type": "inst",    "text_key": "intro"},
    {"id": "sec_condition_a", "type": "section"},
    {"id": "q_a1",            "type": "likert",  "text_key": "q_a1"},
    {"id": "sec_condition_b", "type": "section"},
    {"id": "q_b1",            "type": "likert",  "text_key": "q_b1"},
    {"id": "sec_debrief",     "type": "section"},
    {"id": "q_debrief",       "type": "inst",    "text_key": "debrief"}
  ]
}
```

With the branch group above, participants see `sec_intro → q_intro` then either `sec_condition_a → q_a1` or `sec_condition_b → q_b1`, then `sec_debrief → q_debrief`. The intro and debrief sections are always shown because they are not referenced by any branch arm.

An arm can reference multiple sections:

```json
{"id": "long_form", "sections": ["sec_lf_part1", "sec_lf_part2"]}
```

**Methods:**

| Method | Description | Implemented |
|--------|-------------|-------------|
| `random` | Uniform random selection across arms | ✓ |
| `parameter` | Arm selected by a named OSD parameter value | ✓ |
| `balanced` | Counterbalanced across participants (requires server-side state) | planned |

**Branch arm fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Arm identifier — matched against parameter value for `method: "parameter"` |
| `sections` | array | Section marker IDs to show when this arm is selected |

The selected arm ID is recorded in the output data (one column per branch group).

### A2. Item Sampling / Item Pools

Draw a random subset from a pool of items:

```json
{
  "item_pools": {
    "extraversion_pool": {
      "items": ["e1","e2","e3","e4","e5","e6","e7","e8","e9","e10"],
      "sample_count": 4,
      "method": "random"
    }
  }
}
```

The section marker references the pool in place of a fixed item list:

```json
{
  "id": "sec_extraversion",
  "type": "section",
  "items_from_pool": "extraversion_pool"
}
```

The runner samples `sample_count` items from the pool at runtime and administers them in that section.

**Methods:** `random`, `stratified`, `balanced`.

### A3. Looping / Iteration

Repeat a block of questions for each item in a list:

```json
{
  "id": "sec_task_ratings",
  "type": "section",
  "loop_over": {
    "parameter": "task_list",
    "variable": "current_task"
  }
}
```

The questions following this marker (until the next section marker) are repeated for each value in the `task_list` parameter, with `current_task` substituted in translation strings.

Translation strings use `{loop.current_task}`:

```json
{
  "tlx_mental": "How mentally demanding was {loop.current_task}?"
}
```

The `task_list` parameter provides the list: `["Task A", "Task B", "Task C"]`.

### A4. Scale Composition / Includes

Combine multiple scale definitions into a battery:

```json
{
  "scale_info": {
    "name": "Well-being Battery",
    "code": "wellbeing_battery"
  },
  "includes": [
    {
      "scale": "PHQ9",
      "parameters": {"shuffle_questions": false}
    },
    {
      "scale": "GAD7"
    },
    {
      "scale": "SWLS",
      "dimensions": ["life_satisfaction"]
    }
  ]
}
```

Each included scale runs in sequence. The `dimensions` field selects subscales (C7). The `parameters` field overrides defaults.

### A5. Ranking / Ordering Response Type

Participant ranks items by preference:

```json
{
  "id": "q1",
  "type": "rank",
  "text_key": "q1",
  "options": [
    {"value": "item_a", "text_key": "q1_a"},
    {"value": "item_b", "text_key": "q1_b"},
    {"value": "item_c", "text_key": "q1_c"}
  ]
}
```

Response recorded as ordered list: `["item_b", "item_a", "item_c"]`.

### A6. Audio / Video Media

Extend media support beyond images:

```json
{
  "id": "q1",
  "type": "audio",
  "text_key": "q1",
  "media_file": "audio/clip1.mp3",
  "autoplay": true,
  "allow_replay": true
}
```

**Additional types:** `audio`, `video`, `audioresponse`, `videoresponse`.

Media files are stored in the scale directory.

### A7. Pre-population / Defaults

Pre-fill answers from parameters or prior sessions:

```json
{
  "id": "q1",
  "type": "short",
  "text_key": "q1",
  "default_value": {"parameter": "participant_name"}
}
```

For test-retest: `"default_value": {"prior_answer": "q1"}` fills in the previous session's answer.

---

## Runner-Specific Hints

Sections that are runner-specific should be placed under a namespaced `runner_hints` key. Runners ignore namespaces they don't recognize:

```json
{
  "runner_hints": {
    "pebl": {
      "data_output": {
        "individual_file": "PHQ9-{subnum}.csv",
        "pooled_file": "PHQ9-pooled.csv"
      }
    },
    "web": {
      "theme": "clinical",
      "progress_bar": true
    }
  }
}
```

For backward compatibility, fields like `data_output` and `report` MAY appear at the top level. Runners that don't recognize these fields MUST ignore them.

---

## Expression Language

Used in `computed` expressions and complex conditions.

**References:**

| Syntax | Source |
|--------|--------|
| `answer.{id}` | Participant's answer to question |
| `parameter.{name}` | Runtime parameter value |
| `score.{dim}` | Computed dimension score |
| `computed.{name}` | Computed variable value |

**Operators:**

| Category | Operators |
|----------|-----------|
| Comparison | `==`, `!=`, `>`, `<`, `>=`, `<=` |
| Membership | `in`, `not_in` |
| Logic | `and`, `or`, `not` |
| Math | `+`, `-`, `*`, `/` |

**Functions:** `count()`, `sum()`, `abs()`, `min()`, `max()`

For simple conditions, the structured object format is preferred. The expression string format is for computed variables and complex logic.

---

## Data Output (Runner Hint)

The `data_output` section is a runner hint specifying output file conventions:

```json
{
  "data_output": {
    "individual_file": "SUS-{subnum}.csv",
    "pooled_file": "SUS-pooled.csv",
    "report_file": "SUS-report-{subnum}.html",
    "columns": "subnum,order,time,qnum,ques,dim,valence,resp,rt",
    "pooled_columns": "subnum,timestamp,time,SUS01,SUS02,...,usability"
  }
}
```

| Field | Description |
|-------|-------------|
| `individual_file` | Per-participant data file pattern |
| `pooled_file` | Aggregated data file |
| `report_file` | Per-participant report file pattern |
| `columns` | Column headers for individual file |
| `pooled_columns` | Column headers for pooled file |

`{subnum}` is replaced with the participant identifier. `{code}` is replaced with the scale code.

---

## Report Configuration (Runner Hint)

```json
{
  "report": {
    "template": "standard",
    "include": ["timestamp", "completion_time", "dimension_scores"],
    "header": "Description shown at top of report.",
    "footer_refs": [
      "Citation text.",
      "See <a href='url'>link</a> for more information."
    ]
  }
}
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-15 | Initial specification |
| 1.0.1 | 2026-02-17 | C9 rewritten: flat multi-constraint format replacing single-type format; added `min_words`/`max_words`; per-constraint `{field}_error` keys; clarified evaluation order, word counting, numeric and pattern empty-response behavior |
| 1.0.2 | 2026-02-17 | C5 rewritten: sections replace pages; section-break inline model (`"type": "section"` marker in `questions` list) replaces separate `sections` array; C2 `random_group` clarified as section-scoped; S1/S4/S9/A1/A2/A3 updated accordingly; `randomize_pages` renamed `randomize_sections` |
| 1.0.3 | 2026-02-18 | C2: "questions" → "items" throughout; `questions` array key renamed to `items` (`questions` retained as backward-compat alias); `image`/`imageresponse` types deprecated in favour of `<img>` embedding; C4a added: Media Embedding — `<img>` in any item text splits into text-above / image / text-below regions; `section` type added to C2 type table; S1: `"question"` condition key renamed to `"item"` (`"question"` retained as alias) |
| 1.0.4 | 2026-02-18 | C4a: Remote media sourcing policy added — images/audio block remote URLs by default; `remote="true"` attribute opts in per-tag; `allow_remote_media` scale parameter permits all remote images; video allows remote by default; ScaleBuilder caching prompt noted |
| 1.0.5 | 2026-02-19 | C5: `revisable` and `randomize` promoted to named fields in the section marker fields table (previously only referenced via Standard/Advanced sections); `visible_when` likewise added to table; `revisable` description extended: when returning to a previously answered item via Back, runners CAN and SHOULD pre-fill the response widget and immediately enable Next (not required); S4: randomization methods table updated with implementation status; clarified that per-section `randomize` takes priority over scale-level `shuffle_questions` for that section (the two mechanisms are mutually exclusive per section); randomization method descriptions updated accordingly |
| 1.0.6 | 2026-02-22 | C3: added `max` and `min` scoring methods; added `scores` field allowing a scoring block to take other dimension scores as inputs (enabling hierarchical/composite scoring); added `item_coding` applicability to `scores` references; added evaluation-order requirement and circular-reference error; added QIDS example illustrating max-of-group + sum-of-groups pattern; added rationale paragraph distinguishing scoring blocks from computed variables and clarifying that implementing scoring is Core while computed variables are Standard. S7: rewritten to clarify role as intermediate runtime helper values (skip logic, piping, gates) distinct from primary scale outputs; explicit statement of one-directional data flow (items → scoring blocks → computed variables); added note that Core runners MUST ignore `computed` and still compute scores correctly |
| 1.0.7 | 2026-02-25 | C3: added `sd` scoring method (standard deviation of coded item values); added `transform` field — optional sequence of affine steps (`add`, `subtract`, `multiply`, `divide`) applied to the raw score after the scoring method; `value` in each step is a literal number or a named statistic (`mean`, `sum`, `sd`, `min`, `max`, `range`, `n` from participant responses; `theoretical_min`, `theoretical_max`, `theoretical_range` from item definitions); runner builds a variable map before executing steps — no expression parser required; clarified interaction between `transform` and `scores`-based inputs; clarified distinction between `"method": "sd"` and `"sd"` as a transform reference |
| 1.0.8 | 2026-02-26 | C2: added `question_head` to optional common item fields — a per-item translation key for a shared question stem, overrides `likert_options.question_head` for that item; future multi-item-per-page runners MAY suppress repeated identical heads; `question_head` in `likert_options` clarified to apply to all scored item types (`likert`, `vas`, `grid`, `multi`, `multicheck`), not Likert only; `multi`/`multicheck` `options` format extended: plain strings accepted as shorthand (stored value = translation key); object options `value` field may now be a number (useful when value doubles as scoring value) |
| 1.0.9 | 2026-03-01 | C2: added `likert_reverse` boolean field on `likert` items — when `true`, response buttons are displayed in descending order (highest value on left, lowest on right); stored response value is unchanged; `likert_labels` continues to be indexed by value offset from `likert_min` regardless of display order; ScaleBuilder note: "Reverse display order" checkbox added to Likert item editor |
| 1.0.10 | 2026-03-03 | C3: added `weighted_mean` scoring method — Σ(weight × value) ÷ Σ(weights), complementing the existing `weighted_sum`; `weights` field now applies to both methods and may reference `scores` inputs as well as `items`; clarified that `weighted_sum`/`weighted_mean` inputs absent from `weights` are excluded (not zero-weighted); when `scores` are weighted inputs, the transformed output of each score is used; added QOLIE-89 example illustrating weighted composite of subscale 0–100 scores followed by T-score normalization; added ScaleBuilder UI note: weights editor with per-item numeric inputs, running weight-sum display, and zero/negative-weight warning; C2: `grid` type: added adaptive rendering note — narrow screens SHOULD present each row as an independent question; wide screens MAY show full matrix and paginate |
| 1.0.11 | 2026-03-19 | C3: added `answer_categories` — top-level scoring container for named answer-category sets, enabling multiple `sum_correct` dimensions to score the same `short`-answer items against different answer sets; added `answer_category` field on scoring blocks to reference a named category; use case: CRT-2 scoring both correct answers and intuitive-lure errors from the same free-text responses |
| 1.0.12 | 2026-04-01 | C1: added `implementation` object — metadata about who created the .osd file and licensing for the digital implementation (distinct from scale content license); fields: `author`, `organization`, `date`, `license`, `license_url`, `notes` |
