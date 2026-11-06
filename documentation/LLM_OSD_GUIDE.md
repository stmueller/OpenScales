# Implementing OSD Files with LLMs

*Companion to [SPECIFICATION.md](SPECIFICATION.md). Use this when prompting an LLM to author an Open Scale Definition (`.osd`) file.*

## Why this guide exists

LLMs given only the full specification often invent plausible-but-invalid structures: they put item text in the wrong place, invent response-scale shapes, and use scoring shapes from other survey formats. The result may open in ScaleBuilder but show **blank questions**, wrong response buttons, or broken scoring.

This page is the **short, example-driven contract** to paste into a prompt (or link alongside the spec).

---

## Copy-paste prompt (recommended)

```
You are implementing an OpenScales .osd scale file.

Read these rules carefully — they override generic survey-JSON habits:

1. Output ONE JSON object saved as `{CODE}.osd` (extension .osd, not .json).
2. Top-level keys MUST be exactly: osd_version, definition, translations.
3. ALL participant-facing strings live ONLY under translations.{lang}.
   Items MUST have text_key pointing into that map. Never put item wording
   only under translations without text_key on the item, and never put
   wording inline on the item as "text".
4. likert_options is ONE object with points, min, max, labels (array of
   translation keys or null) — NOT a dict of named option lists, NOT
   arrays of {value, text}.
5. scoring is an OBJECT keyed by score id (not an array). Use method
   mean_coded or sum_coded (not type/average/sum).
6. Match published response values. If options are 0,10,...,100 (not
   consecutive integers), use type multi with numeric value + text_key
   options, or use likert 0..10 with a scoring transform multiply by 10.
7. Follow the minimal template and anti-patterns below. Prefer the
   OpenScales PHQ9.osd pattern for ordinary Likert scales.

Then implement: <SCALE NAME / SOURCE URL / PDF>.
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

**File name:** `EX.osd` (same as `scale_info.code`). Prefer codes without spaces or hyphens (`MDS16` not `MDS-16`) so filenames and URLs stay simple.

---

## Case study: what Gemini got wrong for MDS-16

Prompt used: review SPECIFICATION.md + implement MDS-16 from the MDRH measures page. Output was structurally close at the envelope level but **invalid for runners/ScaleBuilder**.

| # | Gemini output | Spec / runner requirement | Effect |
|---|---------------|---------------------------|--------|
| 1 | Items like `{"id":"mds_1","type":"likert","options":"mds_options"}` — **no `text_key`** | Every scored item MUST have `text_key` into `translations` | ScaleBuilder imports `text: ''` → **blank questions online** even though wording exists under `translations.en.mds_1` |
| 2 | `likert_options: { "mds_options": [ {"value":0,"text":"0%"}, ... ] }` | `likert_options` is a **single** object: `points`, `min`, `max`, `labels` (translation keys). Named formats go in `response_scales`. Labels are keys, not `"text"` | Response UI ignored / wrong; invented schema |
| 3 | Item field `"options": "mds_options"` | Likert uses optional `response_scale` (name into `response_scales`). `options` is for `multi`/`multicheck` and must be an **array** (or use `option_set`) | Options not resolved |
| 4 | `scoring` as an **array** with `"type":"average"` | `scoring` is an **object**; use `"method":"mean_coded"` (or `"mean"`) | Scoring dropped / ignored |
| 5 | `translations.en.instruction` | Shared stem → `likert_options.question_head` → key such as `question_head` (not `instruction`) | Instructions not shown as stem |
| 6 | License `"Open Access (...)"`; missing `domain`, `license_explanation`, `abbreviation`, `version` | Prefer short recommended license labels; document grant in `license_explanation` | Weak / nonstandard metadata |
| 7 | Downloaded as `.json` from the chat UI | Canonical extension is **`.osd`** (content is JSON). ScaleBuilder download uses `.osd`; rename chat exports | Confusing for upload workflows |
| 8 | Response values 0,10,…,100 as if ordinary Likert | Spec Likert `max` must equal `min + points − 1` (unit steps). Non-unit spacing needs `multi` values or Likert 0–10 + `transform` ×10 | Even a “fixed” Likert 0–100 with 11 points would violate `max = min+points-1` if max=100 and points=11 |

### Corrected MDS-16 pattern (excerpt)

MDS-16 items are rated **0%, 10%, …, 100%**; total score is the **mean** (0–100); cutoff ≈ **40**. Because spacing is 10, prefer `multi` with numeric values (preserves published scores) **or** Likert 0–10 with mean×10.

**Option A — `multi` with published values (recommended for fidelity):**

```json
{
  "osd_version": "1.0",
  "definition": {
    "scale_info": {
      "name": "Maladaptive Daydreaming Scale-16",
      "code": "MDS16",
      "abbreviation": "MDS-16",
      "description": "16-item self-report of maladaptive daydreaming. Items rated 0–100% in 10% steps; total score is the mean (0–100). A mean ≥40 suggests suspected clinical-level MD (English cutoff; see Soffer-Dudek corrigenda).",
      "citation": "Somer, E., Lehrfeld, J., Jopp, D. S., & Bigelsen, J. (2016). Development and validation of the Maladaptive Daydreaming Scale (MDS). Consciousness and Cognition, 39, 77–91. https://doi.org/10.1016/j.concog.2015.12.001",
      "license": "free for research use",
      "license_explanation": "MDRH states the MDS-16 is open access for research and clinical use without charge; share resulting publications with the authors. Not a diagnostic tool.",
      "license_url": "https://daydreamresearch.wixsite.com/md-research/measures",
      "version": "1.0",
      "url": "https://daydreamresearch.wixsite.com/md-research/measures",
      "domain": "Mental Health"
    },
    "implementation": {
      "author": "Your Name",
      "organization": "OpenScales Project",
      "date": "2026-11-05",
      "license": "CC BY 4.0",
      "license_url": "https://creativecommons.org/licenses/by/4.0/",
      "notes": "Item wording must be transcribed from an authorized MDS-16 form. Response options 0–100 step 10 encoded as multi values."
    },
    "option_sets": {
      "default": [
        {"value": 0, "text_key": "pct_0"},
        {"value": 10, "text_key": "pct_10"},
        {"value": 20, "text_key": "pct_20"},
        {"value": 30, "text_key": "pct_30"},
        {"value": 40, "text_key": "pct_40"},
        {"value": 50, "text_key": "pct_50"},
        {"value": 60, "text_key": "pct_60"},
        {"value": 70, "text_key": "pct_70"},
        {"value": 80, "text_key": "pct_80"},
        {"value": 90, "text_key": "pct_90"},
        {"value": 100, "text_key": "pct_100"}
      ]
    },
    "dimensions": [
      { "id": "total", "name": "MDS-16 Total", "description": "Mean of 16 items (0–100). ≥40 suggests probable MD (English)." }
    ],
    "items": [
      { "id": "mds1", "type": "multi", "text_key": "mds1" },
      { "id": "mds2", "type": "multi", "text_key": "mds2" }
    ],
    "scoring": {
      "total": {
        "method": "mean_coded",
        "items": ["mds1", "mds2"],
        "description": "Mean of item values (0–100). Cutoff 40 (English)."
      }
    }
  },
  "translations": {
    "en": {
      "question_head": "In answering the following questions, please refer to your daydreaming activities in the last month.",
      "mds1": "(Full published item 1 text…)",
      "mds2": "(Full published item 2 text…)",
      "pct_0": "0%",
      "pct_10": "10%",
      "pct_100": "100%",
      "debrief": "Thank you."
    }
  }
}
```

**Option B — Likert 0–10 + transform ×10:**

```json
"likert_options": {
  "points": 11,
  "min": 0,
  "max": 10,
  "labels": ["pct_0","pct_10","pct_20","pct_30","pct_40","pct_50","pct_60","pct_70","pct_80","pct_90","pct_100"],
  "question_head": "question_head",
  "show_numbers": "none"
},
"scoring": {
  "total": {
    "method": "mean_coded",
    "items": ["mds1", "mds2", "..."],
    "transform": [ { "op": "multiply", "value": 10 } ],
    "description": "Mean of 0–10 ratings ×10 → 0–100 scale."
  }
}
```

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

// GOOD:
"scoring": { "total": { "method": "mean_coded", "items": ["q1"] } }
```

---

## Validation checklist (LLM self-check before finishing)

1. [ ] File is valid JSON; top-level keys: `osd_version`, `definition`, `translations` only (plus optional `_` provenance keys).
2. [ ] Every item has `id`, `type`, and (unless `section`) `text_key`.
3. [ ] Every `text_key` / label key / option `text_key` exists under `translations.en` (or target language).
4. [ ] `likert_options` (if used) has `points`, `min`, `max`, `labels` with `max === min + points - 1`.
5. [ ] `scoring` is an object; methods are from the spec (`mean_coded`, `sum_coded`, …).
6. [ ] `scale_info.code` matches the intended filename stem; prefer `[A-Za-z0-9_]+`.
7. [ ] License uses a short recommended label + `license_explanation` + `license_url` when possible.
8. [ ] `implementation.author` is the actual implementer (not a fictional “OpenScales Community”).
9. [ ] Rename chat downloads from `.json` → `.osd` before sharing.
10. [ ] Run `python3 tools/validate_scale.py path/to/CODE.osd` when available.

---

## Related docs

- [SPECIFICATION.md](SPECIFICATION.md) — normative reference  
- [CONTRIBUTING.md](CONTRIBUTING.md) — repo submission  
- Website help: “Implementing OSD with LLMs” (OpenScales help center)  
- Working examples: `scales/openscales/PHQ9/PHQ9.osd`, `scales/openscales/GAD7/GAD7.osd`
