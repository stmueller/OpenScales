# Implementing OSD Files with LLMs

*Companion to [SPECIFICATION.md](SPECIFICATION.md). Use this when prompting an LLM to author an Open Scale Definition (`.osd`) file.*

## Why this guide exists

LLMs given only the full specification often invent plausible-but-invalid structures: they put item text in the wrong place, invent response-scale shapes, and use scoring shapes from other survey formats. The result may open in ScaleBuilder but show **blank questions**, wrong response buttons, or missing summary scores.

This page is the **short, example-driven contract** to paste into a prompt (or link alongside the spec). Examples here are generic (`EX`, `q1`, `total`) — apply the same patterns to whatever scale you are implementing. Prefer a real repo file such as `PHQ9.osd` as the structural template.

---

## Copy-paste prompt (recommended)

```
You are implementing an OpenScales .osd scale file.

BEFORE writing any JSON:
1. Open https://github.com/stmueller/OpenScales/blob/main/documentation/LLM_OSD_GUIDE.md
2. Quote the section "Fingerprint of a REJECT file" verbatim in your reply
3. Confirm you will NOT emit that fingerprint

Rules (override generic survey-JSON habits):

1. Output ONE JSON object. Filename `{CODE}.osd` (not .json). Prefer CODE
   without spaces or hyphens (letters, digits, underscore).
2. Top-level keys MUST be exactly: osd_version, definition, translations.
3. EVERY item MUST include "text_key" (usually same as "id"). Wording lives ONLY
   under translations.en[text_key]. Missing text_key → blank questions in ScaleBuilder.
4. likert_options MUST look like:
     { "points": N, "min": A, "max": A+N-1, "labels": ["key1", ...], "question_head": "question_head" }
   NEVER: { "my_opts": [ {"value": 0, "text": "Never"}, ... ] }
   NEVER item field "options": "some_name" on likert items.
5. scoring MUST be an object, NOT an array:
     "scoring": { "total": { "method": "mean_coded", "items": ["q1", "q2"] } }
   NEVER: "scoring": [ { "id": "...", "type": "average", ... } ]
6. Non-unit response spacing (e.g. published values 0,10,20,…): use type "multi" +
   option_sets with numeric values, OR a unit-step likert plus scoring transform
   (see Scoring section). Do not invent a likert_options shape for that.
7. Scoring that appears in reports requires matching ids:
     - dimensions: [{ "id": "total", "name": "Total" }]
     - scoring: { "total": { "method": "mean_coded", "items": [...], "description": "..." } }
     - optional transform as an ARRAY: "transform": [{ "op": "multiply", "value": 10 }]
     NEVER omit dimensions when you define scoring.
     NEVER "transform": { "operation": "multiply", "value": 10 }.
     NEVER description_key — use literal "description" on the scoring block.
8. After writing JSON, self-check and list: (a) every item has text_key,
   (b) likert_options has "points" OR you used option_sets, (c) scoring is an object
   with "method", (d) every scoring key has a matching dimensions[].id,
   (e) transform is an array of {op, value} if present. If any check fails, fix before answering.

Then implement: <SCALE NAME / SOURCE URL / PDF>.
Use PHQ9.osd as the structural template for ordinary Likert scales.
```

Also attach or link:

- https://github.com/stmueller/OpenScales/blob/main/documentation/SPECIFICATION.md  
- https://github.com/stmueller/OpenScales/blob/main/documentation/LLM_OSD_GUIDE.md  
- A working example: `scales/openscales/PHQ9/PHQ9.osd`

---

## Minimal valid skeleton

```json
{
  "osd_version": "1.0",
  "definition": {
    "scale_info": {
      "name": "Example Scale",
      "code": "EX",
      "abbreviation": "EX",
      "description": "One sentence.",
      "citation": "Author, A. (Year). Title. Journal. https://doi.org/...",
      "license": "free for research use",
      "license_explanation": "Rights holder states free for research/clinical use; cite source page.",
      "license_url": "https://example.org/measures",
      "version": "1.0",
      "domain": "Mental Health"
    },
    "implementation": {
      "author": "Your Name",
      "organization": "OpenScales Project",
      "date": "2026-11-05",
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
    "dimensions": [
      { "id": "total", "name": "Total" }
    ],
    "items": [
      { "id": "q1", "type": "likert", "text_key": "q1" },
      { "id": "q2", "type": "likert", "text_key": "q2" }
    ],
    "scoring": {
      "total": {
        "method": "mean_coded",
        "items": ["q1", "q2"],
        "description": "Mean of items (range depends on response scale)."
      }
    }
  },
  "translations": {
    "en": {
      "question_head": "Please answer each item.",
      "q1": "First item wording.",
      "q2": "Second item wording.",
      "likert_1": "Never",
      "likert_2": "Rarely",
      "likert_3": "Sometimes",
      "likert_4": "Often",
      "likert_5": "Always",
      "debrief": "Thank you."
    }
  }
}
```

**File name:** `EX.osd` (same as `scale_info.code`). Prefer codes that are safe filename stems: `[A-Za-z0-9_]+`.

---

## Fingerprint of a REJECT file

If output matches **all** of these, it is invalid — delete and regenerate (do not “explain” and ship it):

- Items like `{"id":"q1","type":"likert","options":"my_opts"}` with **no** `text_key`
- `likert_options` shaped as `{ "my_opts": [ {"value":0,"text":"Never"}, ... ] }`
- `scoring` as an **array** with `"type":"average"`

ScaleBuilder and runners **reject** this shape — they do not auto-repair it. Linking this guide is not enough unless the model quotes the fingerprint and self-checks.

### Related failures (loads questions, but no summary score)

| Mistake | Wrong | Correct |
|---------|-------|---------|
| No `dimensions` | only `scoring.total` | also `"dimensions": [{ "id": "total", "name": "Total" }]` — **same id** |
| Bad `transform` | `"transform": { "operation": "multiply", "value": 10 }` | `"transform": [{ "op": "multiply", "value": 10 }]` |
| Wrong description field | `"description_key": "score_desc"` | `"description": "Literal explanation of the score."` |

Without a matching `dimensions` entry, ScaleBuilder drops the scoring block on import. With a non-array `transform`, rescaling never runs.

---

## Scoring that actually appears in the report

Every score id must exist in **both** `dimensions` and `scoring`:

```json
"dimensions": [
  { "id": "total", "name": "Total", "description": "Mean of items." }
],
"scoring": {
  "total": {
    "method": "mean_coded",
    "items": ["q1", "q2", "q3"],
    "description": "Mean of item responses.",
    "norms": {
      "thresholds": [
        { "min": 1, "max": 2.5, "label": "Low" },
        { "min": 2.5, "max": 5, "label": "High" }
      ]
    }
  }
}
```

**Optional affine rescaling** after the method (e.g. map a 0–10 mean onto another published range):

```json
"transform": [ { "op": "multiply", "value": 10 } ]
```

`op` is one of `add`, `subtract`, `multiply`, `divide`. `transform` is always an **array** of steps.

**Non-unit published option values** (spacing ≠ 1): either

- `type: "multi"` with `option_sets` / `options` using numeric `value` + `text_key`, or  
- unit-step `likert` (`max === min + points - 1`) plus a `transform` that recovers the published metric.

Do not put `{value, text}` arrays inside `likert_options`.

---

## Anti-patterns (do not emit)

```json
// BAD: text only in translations, no text_key on item
{ "id": "q1", "type": "likert" }

// BAD: inline text on the item (OSD separates structure from strings)
{ "id": "q1", "type": "likert", "text": "How often…" }

// BAD: invented likert_options shape
"likert_options": { "my_scale": [ { "value": 1, "text": "Never" } ] }

// BAD: scoring as array / wrong field names
"scoring": [ { "id": "total", "type": "average", "items": ["q1"] } ]

// BAD: transform as a single object
"transform": { "operation": "multiply", "value": 10 }

// GOOD:
"scoring": {
  "total": {
    "method": "mean_coded",
    "items": ["q1"],
    "transform": [{ "op": "multiply", "value": 10 }]
  }
}
```

---

## Validation checklist (LLM self-check before finishing)

1. [ ] File is valid JSON; top-level keys: `osd_version`, `definition`, `translations` only (plus optional `_` provenance keys).
2. [ ] Every item has `id`, `type`, and (unless `section`) `text_key`.
3. [ ] Every `text_key` / label key / option `text_key` exists under `translations.en` (or target language).
4. [ ] `likert_options` (if used) has `points`, `min`, `max`, `labels` with `max === min + points - 1`.
5. [ ] `scoring` is an object; methods are from the spec (`mean_coded`, `sum_coded`, …).
6. [ ] Every `scoring` key has a matching `dimensions[].id` (required for ScaleBuilder + reports).
7. [ ] If `transform` is present, it is an **array** of `{ "op": "...", "value": ... }` (field is `op`, not `operation`).
8. [ ] Scoring uses `"description": "..."` (string), not `description_key`.
9. [ ] `scale_info.code` matches the intended filename stem; prefer `[A-Za-z0-9_]+`.
10. [ ] License uses a short recommended label + `license_explanation` + `license_url` when possible.
11. [ ] `implementation.author` is the actual implementer (not a fictional org name).
12. [ ] Rename chat downloads from `.json` → `.osd` before sharing.
13. [ ] Run `python3 tools/validate_scale.py path/to/CODE.osd` when available.

---

## Related docs

- [SPECIFICATION.md](SPECIFICATION.md) — normative reference  
- [CONTRIBUTING.md](CONTRIBUTING.md) — repo submission  
- Website help: “Implementing OSD with LLMs” (OpenScales help center)  
- Working examples: `scales/openscales/PHQ9/PHQ9.osd`, `scales/openscales/GAD7/GAD7.osd`
