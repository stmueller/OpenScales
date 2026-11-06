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
4. Ask the user any open choices below (or state the defaults you will use
   and proceed only if they already answered / said to use defaults)

ASK THE USER (or apply defaults and say so):
- show_numbers on likert_options — MUST be a STRING enum, never a boolean:
    "all" | "labeled_only" | "none"
  NEVER "show_numbers": false or true (boolean false is ignored → numbers still show).
  DEFAULT when every label already states the value (e.g. "0%", "10%", …,
  or "−3"…"3"): "none". Otherwise DEFAULT "all" for ordinary Never…Always
  anchors. Prefer "labeled_only" when only endpoints are labeled and
  middles are null.
- Any other display/scoring ambiguity from the source measure.

Rules (override generic survey-JSON habits — do NOT invert these):

1. Output ONE JSON object. Filename `{CODE}.osd` (not .json). Prefer CODE
   without spaces or hyphens (letters, digits, underscore).
2. Top-level keys MUST be exactly: osd_version, definition, translations.
3. EVERY item MUST include "text_key" (usually same as "id"). Wording lives ONLY
   under translations.en[text_key]. Missing text_key → blank questions in ScaleBuilder.
4. likert_options MUST look like:
     { "points": N, "min": A, "max": A+N-1, "labels": ["key1", ...],
       "show_numbers": "all"|"labeled_only"|"none", "question_head": "question_head" }
   NEVER: { "my_opts": [ {"value": 0, "text": "Never"}, ... ] }
   NEVER item field "options": "some_name" on likert items.
5. scoring MUST be a keyed OBJECT. Score id is the OBJECT KEY, not an "id" field:
     CORRECT: "scoring": { "total": { "method": "mean_coded", "items": ["q1","q2"] } }
     WRONG:   "scoring": [ { "id": "total", "method": "mean_coded", "items": ["q1"] } ]
   Do not "fix" a keyed object into an array — that is the common reject shape.
6. Subscales / totals: EVERY score needs a matching entry in BOTH
   `dimensions` and `scoring` with the SAME id. ScaleBuilder keeps scoring
   only for ids listed in dimensions; scoring-only keys are dropped on
   import, so Preview can still run the items with an empty Summary.
   See "Subscales (dimensions + scoring)" below.
7. Non-unit response spacing (e.g. published values 0,10,20,…): use type "multi" +
   option_sets with numeric values, OR a unit-step likert plus scoring transform
   (see Scoring section). Do not invent a likert_options shape for that.
8. Optional transform is ALWAYS an array of steps with field "op" (not "operation"):
     CORRECT: "transform": [{ "op": "multiply", "value": 10 }]
     WRONG:   "transform": { "operation": "multiply", "value": 10 }
   Score text uses literal "description": "...", NEVER "description_key".
9. After writing JSON, self-check and list: (a) every item has text_key,
   (b) likert_options has "points" OR you used option_sets, (c) scoring is a
   non-array object with "method" under each key, (d) every scoring key has a
   matching dimensions[].id, (e) transform is an array of {op, value} if present,
   (f) if the published measure has subscales, each subscale (and any total)
   appears as its own dimensions+scoring pair with the correct item lists,
   (g) show_numbers is set intentionally. If any check fails, fix before answering.

Then implement: <SCALE NAME / SOURCE URL / PDF>.
Use PHQ9.osd for a single total score; DASS21.osd for multiple subscales.
```

Also attach or link:

- https://github.com/stmueller/OpenScales/blob/main/documentation/SPECIFICATION.md  
- https://github.com/stmueller/OpenScales/blob/main/documentation/LLM_OSD_GUIDE.md  
- Single total: `scales/openscales/PHQ9/PHQ9.osd`  
- Multiple subscales: `scales/openscales/DASS21/DASS21.osd`

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
      "show_numbers": "all",
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

If output matches **any** of these, it is invalid — delete and regenerate (do not “explain” and ship it):

- Items like `{"id":"q1","type":"likert","options":"my_opts"}` with **no** `text_key`
- `likert_options` shaped as `{ "my_opts": [ {"value":0,"text":"Never"}, ... ] }`
- **`scoring` as an array** — including “fixes” that wrap a keyed object into
  `[{ "id": "total", "method": "mean_coded", ... }]`. The score name is the
  **object key**, never an `"id"` field inside an array element.
- `scoring` entries that use `"type": "average"` instead of `"method": "mean_coded"`
- `"show_numbers": false` or `true` (boolean) — must be the string `"none"` / `"all"` / `"labeled_only"`

**Do not invert the scoring rule.** A keyed object is the *correct* OSD shape.
Converting `{ "total": { ... } }` into `[ { "id": "total", ... } ]` is a known
LLM failure mode and produces no usable scores in ScaleBuilder.

ScaleBuilder and runners **reject** this shape — they do not auto-repair it. Linking this guide is not enough unless the model quotes the fingerprint and self-checks.

### Related failures (loads questions, but no summary score / wrong UI)

| Mistake | Wrong | Correct |
|---------|-------|---------|
| `scoring` as array | `"scoring": [{ "id": "total", ... }]` | `"scoring": { "total": { ... } }` |
| No `dimensions` | only `scoring.total` | also `"dimensions": [{ "id": "total", "name": "Total" }]` — **same id** |
| Subscale scoring without dimension rows | `scoring.anxiety` only | `dimensions` entry `{ "id": "anxiety", ... }` **and** `scoring.anxiety` |
| Bad `transform` | `"transform": { "operation": "multiply", "value": 10 }` | `"transform": [{ "op": "multiply", "value": 10 }]` |
| Wrong description field | `"description_key": "score_desc"` | `"description": "Literal explanation of the score."` |
| Boolean `show_numbers` | `"show_numbers": false` | `"show_numbers": "none"` (string enum) |

**Silent Preview trap:** ScaleBuilder may still open and Preview a file that has `scoring` but no matching `dimensions` (or that used an array `scoring` which was dropped). On import it rebuilds scoring **only from** `dimensions`, so orphan / invalid `scoring` is discarded. The run looks fine (items + responses) while Summary stays empty. Treat missing `dimensions` or array-shaped `scoring` as a hard error even if Preview “works.”

### Recurring “I fixed it” mistakes (still wrong)

After a failed attempt, models often partially correct one issue and invent another. Treat this checklist as still-broken until **all** pass:

1. **Keyed `scoring` object** — good. Do **not** re-wrap it as an array later.
2. **`dimensions` with matching ids** — still required; keyed scoring alone is not enough for ScaleBuilder.
3. **`transform`** — array of `{ "op": "...", "value": N }`. A single object with `"operation"` is ignored (no ×10 / rescale).
4. **`description`** — literal string on the scoring block. `"description_key"` is not read for scores.
5. **`show_numbers`** — string `"none"`, never boolean `false`. In the JS runner, `false` is falsy and falls through to default `"all"`, so under-numbers **still appear**.
6. Prefer `osd_version": "1.0"` unless you are intentionally targeting a newer documented envelope; do not invent `"1.1.0"` as a substitute for using `show_numbers` correctly.

---

## Suppressing numeric labels under Likert buttons (`show_numbers`)

By default the runner draws the **stored numeric value** under each button *and*
the label text above it (`show_numbers: "all"`). When labels already encode the
metric (percentages, signed integers, letter grades), that under-number is
redundant and confusing (e.g. label `10%` with a `1` underneath because
`min=0`…`max=10`).

Set on `likert_options` (or a named `response_scales` entry). **Type is a string
enum — not a boolean:**

| Value | Behavior | When to use |
|-------|----------|-------------|
| `"all"` | Number under every button (default) | Ordinary verbal anchors (“Never”…“Always”) |
| `"labeled_only"` | Number only on `null` label slots | Endpoint-anchored scales with blank middles |
| `"none"` | Labels only; no under-numbers | Labels already show the value (`"0%"`, `"10%"`, … / `"−3"`…`"3"`) |

```json
"likert_options": {
  "points": 11,
  "min": 0,
  "max": 10,
  "labels": ["opt_0","opt_10","opt_20","opt_30","opt_40","opt_50",
             "opt_60","opt_70","opt_80","opt_90","opt_100"],
  "show_numbers": "none"
}
```

```json
// WRONG — boolean is not in the enum; runner treats false as missing → "all"
"show_numbers": false
```

Legacy alias only: `suppress_likert_numbers: true` (boolean) ≡ `show_numbers: "none"`.
Prefer the string enum; do not invent `"show_numbers": false`.

**Authoring rule for LLMs:** Before emitting JSON, **ask the user** which
`show_numbers` mode they want. If they do not answer, use the defaults in the
prompt above (`"none"` when labels encode values; otherwise `"all"`) and state
that choice in the reply so it can be tested. Repo example: `TiA.osd`
(`"show_numbers": "none"`).

---

## Subscales (dimensions + scoring)

OSD splits **display metadata** (`dimensions`) from **computation** (`scoring`). Each reported score — a single total, each subscale, or both — needs the **same id** in both places.

Mental model:

```
dimensions[].id  ←→  scoring.<id>   (1:1 for every score that should appear)
scoring.<id>.items  = which item ids feed that score
```

### Rules

1. One `dimensions` object per score you want in the report (subscale **or** total).
2. `dimensions[].id` must equal the key under `scoring`.
3. `scoring.<id>.items` lists the item ids for that subscale (or all items for a total).
4. An item may appear in more than one scoring block (e.g. a subscale and a total).
5. Prefer published subscale names as ids when they are filename-safe (`depression`, `anxiety`); otherwise use short snake_case ids and put the printed name in `dimensions[].name`.
6. Use `method: "sum_coded"` or `"mean_coded"` as the publication specifies — not `"type": "average"`.
7. If the publication multiplies/rescales after summing/averaging, put that in `transform` (array of `{op, value}`), not in a homemade field.

### Pattern A — one total score (no subscales)

```json
"dimensions": [
  { "id": "total", "name": "Total" }
],
"scoring": {
  "total": {
    "method": "sum_coded",
    "items": ["q1", "q2", "q3", "q4"],
    "description": "Sum of all items."
  }
}
```

Repo template: `PHQ9.osd`.

### Pattern B — several subscales (no overall total)

Each subscale is its own dimension + scoring block with a disjoint (or overlapping, if published that way) item list:

```json
"dimensions": [
  { "id": "factor_a", "name": "Factor A" },
  { "id": "factor_b", "name": "Factor B" },
  { "id": "factor_c", "name": "Factor C" }
],
"items": [
  { "id": "q1", "type": "likert", "text_key": "q1" },
  { "id": "q2", "type": "likert", "text_key": "q2" },
  { "id": "q3", "type": "likert", "text_key": "q3" },
  { "id": "q4", "type": "likert", "text_key": "q4" },
  { "id": "q5", "type": "likert", "text_key": "q5" },
  { "id": "q6", "type": "likert", "text_key": "q6" }
],
"scoring": {
  "factor_a": {
    "method": "sum_coded",
    "items": ["q1", "q2"],
    "description": "Sum of Factor A items."
  },
  "factor_b": {
    "method": "sum_coded",
    "items": ["q3", "q4"],
    "description": "Sum of Factor B items."
  },
  "factor_c": {
    "method": "sum_coded",
    "items": ["q5", "q6"],
    "description": "Sum of Factor C items."
  }
}
```

Repo template: `DASS21.osd` (three subscales, seven items each).

### Pattern C — subscales plus an overall total

Add a `total` dimension whose `items` are all scored items (or use `scores` to combine subscale scores when the publication defines a composite that way — see SPECIFICATION.md):

```json
"dimensions": [
  { "id": "factor_a", "name": "Factor A" },
  { "id": "factor_b", "name": "Factor B" },
  { "id": "total", "name": "Total" }
],
"scoring": {
  "factor_a": {
    "method": "mean_coded",
    "items": ["q1", "q2", "q3"],
    "description": "Mean of Factor A items."
  },
  "factor_b": {
    "method": "mean_coded",
    "items": ["q4", "q5", "q6"],
    "description": "Mean of Factor B items."
  },
  "total": {
    "method": "mean_coded",
    "items": ["q1", "q2", "q3", "q4", "q5", "q6"],
    "description": "Mean of all items."
  }
}
```

Repo template: `FFMQ15.osd` (five facets + total).

### Pattern D — rescaling after the method

When the published metric is “mean (or sum), then multiply by N”:

```json
"dimensions": [
  { "id": "total", "name": "Total" }
],
"scoring": {
  "total": {
    "method": "mean_coded",
    "items": ["q1", "q2", "q3"],
    "transform": [{ "op": "multiply", "value": 10 }],
    "description": "Mean of items, multiplied by 10."
  }
}
```

Apply the same `transform` on each subscale block if every subscale uses that rescaling.

### Reverse-coded items within a subscale

When some items are reverse-scored inside one subscale, use an **object** for `items` (coding −1) instead of a plain array — see SPECIFICATION.md / RFQ examples. Do not invent a separate `"reverse": true` flag unless you also emit the object coding form the runner understands.

### Self-check for subscales

Before finishing, list every published subscale/total and confirm:

- [ ] `dimensions` length equals the number of scores you intend to report  
- [ ] every `dimensions[].id` exists as `scoring.<id>`  
- [ ] every `scoring` key exists in `dimensions`  
- [ ] each subscale’s `items` list matches the publication (no accidental empty or all-items lists)  
- [ ] any post-score multiply/add is a `transform` **array** with `"op"`, not `"operation"`

---

## Scoring that actually appears in the report

Every score id must exist in **both** `dimensions` and `scoring` (see patterns above). Optional norms:

```json
"norms": {
  "thresholds": [
    { "min": 0, "max": 9, "label": "Low" },
    { "min": 10, "max": 20, "label": "High" }
  ]
}
```

**Optional affine rescaling** after the method — always an **array**:

```json
"transform": [ { "op": "multiply", "value": 10 } ]
```

`op` is one of `add`, `subtract`, `multiply`, `divide`.

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

// BAD: scoring as array (including "id" inside the element) — NEVER do this
"scoring": [ { "id": "total", "method": "mean_coded", "items": ["q1"] } ]
"scoring": [ { "id": "total", "type": "average", "items": ["q1"] } ]

// BAD: scoring without dimensions (Preview may run; Summary stays empty)
"scoring": { "total": { "method": "mean_coded", "items": ["q1"] } }
// (missing "dimensions": [{ "id": "total", "name": "Total" }])

// BAD: transform as a single object
"transform": { "operation": "multiply", "value": 10 }

// BAD: percent/signed labels with default show_numbers (duplicates the metric)
"labels": ["opt_0","opt_10",...],  // translations "0%","10%",...
// (omit show_numbers → "all" → button shows "10%" and "1")

// BAD: boolean show_numbers (ignored → still shows numbers)
"show_numbers": false

// BAD: description_key (not used for score text)
"description_key": "score_desc"

// GOOD: keyed scoring + dimensions; transform array; string show_numbers
"likert_options": {
  "points": 11, "min": 0, "max": 10,
  "labels": ["opt_0","opt_10","opt_20","opt_30","opt_40","opt_50",
             "opt_60","opt_70","opt_80","opt_90","opt_100"],
  "show_numbers": "none"
},
"dimensions": [{ "id": "total", "name": "Total" }],
"scoring": {
  "total": {
    "method": "mean_coded",
    "items": ["q1"],
    "transform": [{ "op": "multiply", "value": 10 }],
    "description": "Mean × 10."
  }
}
```

---

## Validation checklist (LLM self-check before finishing)

1. [ ] File is valid JSON; top-level keys: `osd_version`, `definition`, `translations` only (plus optional `_` provenance keys).
2. [ ] Every item has `id`, `type`, and (unless `section`) `text_key`.
3. [ ] Every `text_key` / label key / option `text_key` exists under `translations.en` (or target language).
4. [ ] `likert_options` (if used) has `points`, `min`, `max`, `labels` with `max === min + points - 1`.
5. [ ] `scoring` is a **keyed object** (not an array); methods are from the spec (`mean_coded`, `sum_coded`, …).
6. [ ] `dimensions` is present whenever `scoring` is; every `scoring` key has a matching `dimensions[].id`.
7. [ ] If the measure has subscales, each subscale (and any total) is its own dimensions+scoring pair with the correct item lists.
8. [ ] If `transform` is present, it is an **array** of `{ "op": "...", "value": ... }` (field is `op`, not `operation`).
9. [ ] Scoring uses `"description": "..."` (string), not `description_key`.
10. [ ] `show_numbers` is the string `"all"` / `"labeled_only"` / `"none"` (not boolean); asked the user or stated the default.
11. [ ] `scale_info.code` matches the intended filename stem; prefer `[A-Za-z0-9_]+`.
12. [ ] License uses a short recommended label + `license_explanation` + `license_url` when possible.
13. [ ] `implementation.author` is the actual implementer (not a fictional org name).
14. [ ] Rename chat downloads from `.json` → `.osd` before sharing.
15. [ ] Run `python3 tools/validate_scale.py path/to/CODE.osd` when available.

---

## Related docs

- [SPECIFICATION.md](SPECIFICATION.md) — normative reference  
- [CONTRIBUTING.md](CONTRIBUTING.md) — repo submission  
- Website help: “Implementing OSD with LLMs” (OpenScales help center)  
- Working examples: `PHQ9.osd` (single total), `DASS21.osd` (subscales), `FFMQ15.osd` (subscales + total), `GAD7.osd`
