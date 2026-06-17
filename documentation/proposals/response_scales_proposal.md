# Proposal: First-Class Named Response Scales

**Status:** Draft proposal — NOT yet part of the OSD specification. For discussion.
**Author:** OpenScales Project
**Date:** 2026-06-16
**Affects:** `SPECIFICATION.md` C2 (item types / Likert), runners, ScaleBuilder, all converters.

---

## 1. Problem

A single instrument frequently uses **two or more distinct response formats**. Examples already in or destined for the repository:

- **MFQ / MFQ-Liberty** — a *relevance* rating block (0 = not at all relevant … 5 = extremely relevant) followed by an *agreement* block (0 = strongly disagree … 5 = strongly agree).
- **Risk batteries** — a *risk-perception* 7-point block and an *expected-benefits* 7-point block with different anchors and different question stems.
- **Mixed surveys** — a 5-point agreement section plus a frequency section ("Never … Always") plus a single 0–10 VAS.
- **Semantic differential** — every item has its own unique endpoint pair.

Today this is expressed through **several overlapping mechanisms** that all describe "what the response buttons look like":

| Mechanism | Where | Purpose |
|-----------|-------|---------|
| `likert_options` | scale level | the default response format |
| `response_scales` | scale level | named alternate formats (added v1.0.14) |
| `likert_labels` / `likert_points` | per item | per-item override (semantic differential) |
| `likert_min` / `likert_max` | per item | numeric range |
| `likert_reverse` | per item | display order (high→low) |
| `suppress_likert_numbers` | `likert_options` or top level | hide the numeric value under buttons |

The result is fragmented: the same concept (a response scale) is defined in up to four places with different shapes, and display concerns (`suppress_likert_numbers`, `likert_reverse`) are bolted on as flat booleans. The null-padded `likert_labels` array (indexed by value-offset, with `null` for unlabeled points) is error-prone and is the direct cause of the "number shown twice" issue that `suppress_likert_numbers` was introduced to patch.

**Key observation:** ScaleBuilder already models this correctly. Internally it *creates a named response scale* — points, anchor labels, shared question head, number display, order — and then lets each question **reference that scale by id**. The on-disk format only partially reflects that mental model (`response_scales` exists but is treated as a secondary add-on to `likert_options`). This proposal promotes the builder's existing model to the **primary, first-class** representation.

## 2. Design principles

1. **One concept, one shape.** Every response format — default, named, or per-item — is the same object.
2. **Structure vs. text separation (hard rule).** Response-scale definitions are **scale logic** and therefore contain **no human-facing text** — only translation *keys*. All anchor labels and question stems resolve through the per-language `translations` files, exactly like `text_key`. The one exception is `name`, an editor-facing identifier (see Open Questions), consistent with how `dimensions[].name` is already a literal editor/report label.
3. **Display is declarative, not a pile of booleans.** Number visibility and ordering are fields of the scale, not separate top-level flags.
4. **Backward compatible.** Existing `likert_options` / `likert_*` files continue to work unchanged; the new model is sugar-free superset, and old fields become deprecated aliases.

## 3. Proposed model

### 3.1 A response scale object

```json
"response_scales": {
  "agree5": {
    "name": "5-point Agreement",
    "points": 5,
    "min": 1,
    "max": 5,
    "labels": ["sd", "d", "n", "a", "sa"],
    "question_head": "agree_head",
    "show_numbers": "labeled_only",
    "order": "ascending"
  },
  "relevance6": {
    "name": "MFQ Relevance",
    "points": 6,
    "min": 0,
    "max": 5,
    "labels": ["rel_0", "rel_1", "rel_2", "rel_3", "rel_4", "rel_5"],
    "question_head": "relevance_head",
    "show_numbers": "all",
    "order": "ascending"
  }
}
```

Every value in `labels` and the `question_head` is a **translation key**, resolved per language. No display string ever appears here.

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `name` | string | no | Editor/report-facing label (not shown to participants). Literal, like `dimensions[].name`. |
| `points` | integer | yes | Number of response options. |
| `min` | integer | yes | Numeric value of the first option. |
| `max` | integer | yes | Numeric value of the last option. |
| `labels` | array of (string \| null) | yes | One translation key per point, indexed by value-offset from `min`. `null` = unlabeled point. |
| `question_head` | string | no | Translation key for a shared question stem for items using this scale. |
| `show_numbers` | enum | no | `all` (default) · `labeled_only` · `none`. Replaces `suppress_likert_numbers`. |
| `order` | enum | no | `ascending` (default) · `descending`. Replaces `likert_reverse`. Stored value is unaffected by display order. |

### 3.2 `show_numbers` semantics

Resolves the double-display problem at the model level:

- `all` — every button shows its numeric value beneath the (possibly empty) label. *Current default behavior.*
- `labeled_only` — show the numeric value only for points that have **no** text label (so an unlabeled middle point shows just its number; a labeled endpoint shows just its text). This is the common "anchored endpoints, bare middle" case (e.g. MRSS) and removes the duplicate number with no need for a separate suppress flag.
- `none` — never show numeric values; labels only. For scales whose labels already encode the number (bipolar "−3 … +3").

### 3.3 Item reference

```json
{ "id": "rp1", "type": "likert", "text_key": "rp1", "response_scale": "rp" }
```

Unchanged from v1.0.14. Items with no `response_scale` use the default scale (§3.4).

### 3.4 The default scale

`likert_options` becomes **syntactic sugar** for a reserved response scale named `default`. These are equivalent:

```json
"likert_options": { "points": 5, "min": 1, "max": 5, "labels": [...], "question_head": "qh" }
```
```json
"response_scales": { "default": { "points": 5, "min": 1, "max": 5, "labels": [...], "question_head": "qh" } }
```

A runner builds the scale table by reading `response_scales`, then overlaying a `default` entry synthesized from `likert_options` if present.

### 3.5 Resolution order (unchanged in spirit)

For a `likert` item, the runner picks its response format by:

1. Per-item `likert_labels` / `likert_points` (legacy per-item override, e.g. semantic differential) — **deprecated** in favor of an inline or named scale, but still honored.
2. `response_scale: "<id>"` → look up in `response_scales`.
3. Fall back to the `default` scale (from `likert_options`).

## 4. Backward compatibility & migration

Nothing breaks. The following become **deprecated aliases**, supported indefinitely, mapped onto the new model:

| Deprecated | Maps to |
|-----------|---------|
| `likert_options` | `response_scales.default` |
| `suppress_likert_numbers: true` | `show_numbers: "none"` (or `labeled_only` — see Open Questions) |
| `likert_reverse: true` (item) | item's scale `order: "descending"` |
| per-item `likert_labels` / `likert_points` | an implicit per-item inline scale |
| `likert_min` / `likert_max` | scale `min` / `max` |

- **Runners:** read the new fields first; synthesize from deprecated fields when the new ones are absent. A Core runner that only understands `likert_options` keeps working for single-scale instruments.
- **Converters (REDCap, Qualtrics, LimeSurvey, PsyToolkit, QTI, Surveydown):** today each re-derives response options from the scattered fields per item. Under this model they read the resolved scale table once and emit one reusable response set per named scale — closer to how REDCap (shared answer choices) and Qualtrics (carry-forward / matrix) natively represent repeated scales.
- **ScaleBuilder:** this *is* the builder's internal model; formalizing it means the on-disk format equals what the builder already constructs ("define a named scale with anchors + item head once, reference it per question"). The builder stops "faking" a structure the spec doesn't bless.

## 5. Worked example — two scales in one test

```json
"response_scales": {
  "rp": { "name": "Risk Perception", "points": 7, "min": 1, "max": 7,
          "labels": ["rp1","rp2","rp3","rp4","rp5","rp6","rp7"],
          "question_head": "rp_head", "show_numbers": "labeled_only" },
  "eb": { "name": "Expected Benefits", "points": 7, "min": 1, "max": 7,
          "labels": ["eb1","eb2","eb3","eb4","eb5","eb6","eb7"],
          "question_head": "eb_head", "show_numbers": "labeled_only" }
},
"items": [
  { "id": "rp1", "type": "likert", "text_key": "rp1", "response_scale": "rp" },
  { "id": "rp2", "type": "likert", "text_key": "rp2", "response_scale": "rp" },
  { "id": "eb1", "type": "likert", "text_key": "eb1", "response_scale": "eb" }
]
```

All participant-facing strings (`rp_head`, `rp1`…, `eb_head`, `eb1`…) live only in `translations`.

## 6. Open questions

1. **`suppress_likert_numbers` mapping.** Its current meaning ("don't show the number anywhere") maps to `show_numbers: "none"`. But the cases that motivated it (MRSS: anchored endpoints + bare middles) actually want `labeled_only`. Decide whether the deprecated flag maps to `none` (literal) or `labeled_only` (intent). Recommendation: map literal `none`; encourage authors to adopt `labeled_only`.
2. **Is `name` text-in-logic?** It is editor/report-facing, never shown to participants, and mirrors `dimensions[].name` (already literal). Proposal keeps it literal. Alternative: make it `name_key` for full purity.
3. **Inline per-item scales.** Should semantic-differential items get a clean inline form (`"scale": { ...object... }` on the item) to fully retire per-item `likert_labels`/`likert_points`, or keep referencing named scales only?
4. **`vas` and `grid`.** Should VAS anchors and grid columns also migrate to this object (they have parallel `min`/`max`/anchor-key concerns), or stay separate for now? Proposal scopes v1 to `likert` only.
5. **Spec version.** This is additive + deprecations → a minor bump (e.g. 1.1.0), since the on-disk surface changes meaningfully even though old files keep working.

## 7. Non-goals

- No change to scoring, dimensions, or translation file format.
- No removal of any existing field in this version — deprecations only.
- Not adopting this into `SPECIFICATION.md` yet; this document is the proposal for review.
