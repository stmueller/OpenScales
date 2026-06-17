# Proposal: Scale Variants (alternative item forms & language-specific item sets in one OSD)

**Status:** PROMOTED — incorporated into SPECIFICATION.md §A8 (v1.0.16, 2026-06-17). This document is retained as the design rationale.
**Author:** OpenScales Project
**Date:** 2026-06-17
**Affects:** `SPECIFICATION.md` C2 (items), C3 (dimensions/scoring), C4 (translations); runners; ScaleBuilder; converters.
**Motivating scales:** Schwarzer family — Teacher Self-Efficacy (TSES), Proactive Attitude (PAS), Proactive Coping Inventory (PCI), Environmental Worry (EWS).

---

## 1. Problem

A single instrument frequently exists in **variants** that share most — but not all — of their content. Three escalating cases, all present in scales we are adding right now:

1. **Framing-reversed single item.** *Teacher Self-Efficacy*: 9 of 10 items are identical across English and German. **Item 7** differs in valence — the English (Schwarzer, Schmitz & Daytner 1999) is positively worded and forward-coded; the official German (FU-Berlin skalen) is negatively worded and **reverse-coded** ("…weiß ich, daß ich nicht viel ausrichten kann"). Same construct slot, opposite framing and coding.

2. **Overlapping-but-different item sets.** *PCI*: English = 55 items / 7 subscales (Greenglass, Schwarzer & Taubert 1999); German "deviates strongly" = 57 items with a different subscale layout. *Environmental Worry*: English = 17 items (Bowler & Schwarzer 1991); German = 16 items (Hodapp, Neuhann & Reinschmidt 1996) — different authors, different items, related construct. The variants overlap in spirit but not item-for-item, and **their scoring/subscale structure differs**.

3. **Revised editions.** A short form that is a strict subset of a long form; a v2 that adds three items and drops one; a culturally-adapted edition. Same family, different administered set.

Today an OSD shares **one** `items` list and **one** `scoring` block across all languages (`translations` vary only the *text*, never *which* items exist or *how* they score). There is no way to express "German administers item 7N (reverse) instead of 7P," "this language uses only items 1–16," or "the English and German editions have different subscales."

The current workaround is to either (a) silently translate one variant's items into the other language — losing the official wording and mis-coding reversed items — or (b) fork a near-duplicate OSD per variant, which fragments translations, scoring fixes, and metadata. Neither scales.

## 2. Design principles

1. **One file, many variants.** Keep alternative item forms and language-specific item sets in the same OSD. The on-disk `definition.items` is the **union** of all items across variants; each variant selects a subset (and its order).
2. **A variant is a named selection.** It names *which items are administered*, *in what order*, and *which scoring applies*. It is not itself text.
3. **Items own their coding.** Reverse/forward coding is already a property of an item's role in a dimension (the `items`-object `{id: 1|-1|0}` form). Mutually-exclusive variant items (7P forward, 7N reverse) both live in `scoring`; only the administered one ever contributes.
4. **Score only administered items.** A dimension's value is computed over the **intersection** of its item list, the active variant's item set, and the answered items. (The spec already tolerates partial answering via `"n" = count of answered items`.)
5. **Two kinds of selector, which must compose.** Variant membership can be driven by either:
   - a **forced** axis — the **language** the runner is displaying. The respondent does not choose; the language dictates the item form (e.g. the German item 7 *must* be the reverse-keyed one).
   - a **free** axis — a **choice parameter** the administrator/respondent selects (e.g. `form` = `standard` vs `reverse`, or `edition` = `full` vs `short`).

   These are **orthogonal and may apply at once**: *German × reverse-form* can reverse items that *English × reverse-form* does not, while plain *standard* shares one pattern across languages. A single scalar `axis` cannot express this — membership is a function of the **whole coordinate** (language, *and every choice parameter*). The mechanism below therefore makes item membership a **condition over selectors**, not a single set id.
6. **Reuse existing machinery.** Free axes are exactly the existing `parameters` block (`type: "choice"`). Conditional inclusion is exactly `visible_when`, extended to read the `language` and parameter selectors. The variant strategy is mostly *connective tissue* over features OSD already has, not a parallel system.
7. **Backward compatible.** No variant conditions / no `variants` block ⇒ exactly one implicit variant = all items, all scoring — i.e. today's behavior, unchanged. Existing files need no edits.

## 3. Schema additions

### 3.1 Item grouping (C2)

One optional field on `likert`/`multi`/etc. items:

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `variant_group` | string | — | Items sharing a value are **mutually exclusive** alternatives for the same construct slot. At most one is administered for any given variant. Purely advisory for validation/ScaleBuilder; membership is still governed by each variant's `items` list. |

### 3.2 Definition-level `variants` block (new)

```json
"variants": {
  "axis": "language",
  "default": "en",
  "sets": {
    "en": {
      "name": "English (Schwarzer, Schmitz & Daytner, 1999)",
      "languages": ["en"],
      "items": ["tse1","tse2","tse3","tse4","tse5","tse6","tse7P","tse8","tse9","tse10"]
    },
    "de": {
      "name": "German (FU-Berlin skalen)",
      "languages": ["de"],
      "items": ["tse1","tse2","tse3","tse4","tse5","tse6","tse7N","tse8","tse9","tse10"]
    }
  }
}
```

| Field (per set) | Type | Meaning |
|-----------------|------|---------|
| `name` | string | Editor/report label (literal, like `dimensions[].name`). |
| `languages` | array | When `axis="language"`, the language codes that select this set. A language in no set falls back to `default`. |
| `items` | array | **Ordered** list of administered item IDs. Defines both membership and presentation order. |
| `scoring` | array of strings | *(optional)* IDs of the scoring blocks that apply to this variant. Omit ⇒ all scoring blocks whose items are fully present. Needed for case 2 (PCI/EWS) where EN and DE have different subscales. |
| `base` / `add` / `remove` | string / array / array | *(optional sugar)* Inherit `items` from another set, then add/remove IDs. For revised editions and subsets. |

Top-level: `default` (set id used when nothing matches). **`sets` is sugar for the common single-axis case** (membership driven by one selector, usually language). It compiles to the conditional form in §3.2a. When membership depends on **two or more axes** (language × form), use conditions directly — `sets` cannot express a coordinate.

### 3.2a Selectors and conditional membership (the general mechanism)

Two selectors are available to conditions:

| Selector | Kind | Value at runtime |
|----------|------|------------------|
| `language` | **forced** | the active language code (e.g. `"de"`). |
| a `parameters` entry of `type: "choice"` | **free** | the option the user/administrator chose (e.g. `form = "reverse"`). |

An item MAY carry `variant_when` — a condition (same grammar as `visible_when`, with `all`/`any` nesting) that reads these selectors:

```json
{ "selector": "language", "operator": "in",     "value": ["de"] }
{ "parameter": "form",    "operator": "equals", "value": "reverse" }
```

**Resolution:** an item is part of the administered set iff it has no `variant_when`, **or** its `variant_when` evaluates true for the current `(language, parameters…)` coordinate. `variant_when` is resolved **once at instantiation** (from language + parameter choices); `visible_when` continues to resolve **at runtime** from answers. The two compose — an item can have both.

This is what makes the axes orthogonal: the *forced* language axis and each *free* parameter axis are independent inputs to the same condition, so `{all: [ {selector:language,in:[de]}, {parameter:form,equals:reverse} ]}` selects exactly the German-reverse item, while an item with no `variant_when` is shared across every coordinate.

`variant_group` (§3.1) stays advisory: members of a group should have mutually-exclusive `variant_when` so that exactly one resolves true per coordinate (the validator checks this).

**Declaring axes (optional, for tooling).** A `variants.axes` array lets ScaleBuilder and the validator enumerate the design space without scanning every item:

```json
"variants": {
  "axes": [
    { "id": "language", "selector": "language" },
    { "id": "form", "selector": "parameter", "parameter": "form" }
  ],
  "default": { "form": "standard" }
}
```
`default` may be a coordinate object (per-axis defaults) in the multi-axis form, or a set id in the `sets` sugar form.

### 3.2b How `sets` and `variant_when` compose

Both are kept; they own **different axes** and combine with **AND**:

- **`sets`** expresses the **language axis** (one forced axis) by enumeration — the readable "here is exactly what the German version contains" form.
- **`variant_when`** expresses **free/parameter axes** and any **multi-axis** condition.

**Resolution rule.** An item is administered iff **both** hold:
1. **(if a `sets` block exists)** the item is in the active language's set — or the item is not governed by `sets` at all (an item listed in *no* set is treated as shared across all sets, so shared items need not be repeated only if the `sets` form is used purely for the divergent ones; the enumerated form lists them for readability); **and**
2. **(if the item has `variant_when`)** its condition passes for the current parameters/coordinate.

So the *language × form* matrix is written as `sets` (language) **+** a `form` parameter referenced by `variant_when` on the form-specific items. Guidance to avoid ambiguity (validator-enforced): **do not** drive the *same* axis from both mechanisms — if a scale uses `sets` for language, its `variant_when` conditions should reference parameters (or non-language selectors), not `selector:language`. A scale with no multi-axis needs only `sets`; a scale with no language divergence needs only `variant_when` (or nothing).

### 3.3 Scoring (C3) — variant-scoped blocks

A scoring block (and its dimension) MAY carry:

| Field | Type | Meaning |
|-------|------|---------|
| `variants` | array of strings | Set IDs this block/dimension applies to. Default: all. Runners compute a block only when the active variant is listed (or when `default`/all). |

This lets the English PCI's seven subscales and the German PCI's seven (different) subscales coexist in one `scoring` object, each tagged with `"variants": ["en"]` / `["de"]`.

### 3.4 Translations (C4)

No structural change. A language only needs text keys for the items in the variant(s) it selects. **Validation becomes per-variant:** completeness is checked against the active variant's item set, not the union — so the `de` file need not (and should not) provide text for `tse7P`, only `tse7N`.

## 4. Runtime semantics

Given a chosen language L (and/or explicit `variant`):
1. **Resolve the active set** S: if `axis="language"`, the set whose `languages` contains L, else `default`; if `axis≠"language"`, the UI/`variant` choice, else `default`.
2. **Administer** exactly `S.items`, in that order, pulling text from `translations[L]`.
3. **Score** each block B where (B applies to S, per §3.2 `scoring`/§3.3 `variants`) over `B.items ∩ S.items ∩ answered`, using each item's coding. Mutually-exclusive group members never co-occur, so opposite codings are safe.
4. **Report** ranges/labels from the block; when counts differ across variants, prefer `mean_coded` or document per-variant ranges.

## 5. Worked examples

### 5.1 Case 1 — TSES item 7 (framing reversal)

`items` (union) contains `tse7P` and `tse7N`, both `variant_group: "tse7"`, both `dimension: teacher_self_efficacy`. Variant `en` administers `tse7P`; `de` administers `tse7N`. Scoring:

```json
"teacher_self_efficacy": {
  "method": "sum_coded",
  "items": { "tse1":1,"tse2":1,"tse3":1,"tse4":1,"tse5":1,"tse6":1,
             "tse7P":1, "tse7N":-1,
             "tse8":1,"tse9":1,"tse10":1 }
}
```
English administers 7P (forward); German administers 7N (reverse-coded so a "stimmt nicht"=1 on the negatively-worded item maps high). One block, both variants correct, range 10–40 either way.

### 5.2 Case 2 — PCI / Environmental Worry (different item sets *and* scoring)

Largely-disjoint membership: `items` is the union of the English and German item pools (shared IDs only where wording truly corresponds). Each subscale dimension is tagged `"variants": ["en"]` or `["de"]`; each variant set lists its own `items` and (optionally) its `scoring` block IDs. The English respondent sees 55 items scored on the 7 English subscales; the German respondent sees the 57-item German version on its own subscales — one file, no cross-contamination.

### 5.3 Case 3 — revised edition / short form (sugar)

```json
"sets": {
  "full":  { "name":"20-item original", "items":["q1", "...", "q20"] },
  "short": { "name":"10-item short form", "base":"full",
             "remove":["q3","q6","q9","q12","q14","q16","q18","q19","q20","q11"] }
}
```
`axis: "edition"`, selected by UI; both score from the same dimension blocks (short form's blocks tagged `variants:["short"]` if its scoring differs).

### 5.4 Composite — language (forced) × form (free) at once

The hard case: a scale exists as **XXX** and **XXX-R** (free `form` parameter), where **XXX-R reverses certain items only in German**, while **XXX** shares one pattern across languages. Selectors compose:

```json
"parameters": {
  "form": { "type": "choice", "options": ["standard","reverse"], "default": "standard" }
},
"items": [
  { "id":"q5",  "type":"likert", "text_key":"q5", "dimension":"d" },          // shared everywhere
  { "id":"q5_rev_de", "type":"likert", "text_key":"q5_rev_de", "dimension":"d",
    "variant_group":"q5alt",
    "variant_when": { "all": [ {"selector":"language","operator":"in","value":["de"]},
                               {"parameter":"form","operator":"equals","value":"reverse"} ] } }
],
"scoring": {
  "d": { "method":"mean_coded", "items": { "q5":1, "q5_rev_de":-1, "...":1 } }
}
```

- *English × standard* and *English × reverse* → administer `q5` (the German-only reversed form never resolves).
- *German × standard* → `q5`.
- *German × reverse* → `q5_rev_de` (reverse-coded), `q5` excluded (same `variant_group`).

One file expresses the full 2-D matrix; scoring is correct in every cell because only the resolved item contributes and it carries its own coding.

## 6. Backward compatibility & graceful degradation

- **No `variants` block** → unchanged single-variant behavior. All existing OSDs are valid as-is.
- **Naive runner (variant-unaware) encounters a `variants` block** → it would administer the full union (showing both 7P and 7N) — *incorrect*. Mitigations, in order of preference: (a) update runners to honor `variants` (the real fix; small for the language-axis case); (b) until then, a build step can **emit the `default` variant as a flattened single-variant OSD** for legacy runners while the source keeps all variants. We should not ship a `variants` OSD to a runner that ignores it.

## 7. Impact

| Component | Change |
|-----------|--------|
| **SPECIFICATION.md** | New `variant_group` (C2), `variants` block (new subsection under C3 or its own), `variants` tag on scoring/dimensions (C3), per-variant translation-completeness note (C4). |
| **Runners (JS, scale.php)** | Resolve active set by language/param; administer `S.items`; score over `∩`; per-variant translation lookup. Language-axis case is modest; `scoring`-override case a bit more. |
| **build_manifest** | Report per-variant language coverage; a scale's `languages` = union of sets' `languages`. |
| **validate_scale** | Validate `variants.sets[*].items ⊆ items`; every `variant_group` has ≥2 members across sets; per-variant translation completeness; scoring block items resolve within their tagged variants. |
| **ScaleBuilder** | "Variant" editor: define sets, drag items per set, choose group member per variant; "this item is an alternative form of…" control. |
| **Converters** | Export the active/selected variant (most target platforms are single-variant). |

## 8. Open questions

1. **DECIDED — keep `sets` *and* `variant_when`.** `sets` is the readable sugar for a single forced axis (almost always language); `variant_when` is the general mechanism for free/parameter axes and multi-axis coordinates. They compose (§3.2b).
2. **DECIDED — distinct `variant_when`** (not an overload of `visible_when`). `variant_when` resolves **once at instantiation** from the (language, parameters…) coordinate; `visible_when` resolves **at runtime** from answers. Keeping them separate preserves the "fixed at start" vs. "reacts to answers" distinction and lets the runner build the administered item list once, before the first item is shown.
3. **Condition grammar for selectors** — finalize `{"selector":"language"|...}` and `{"parameter":"<name>"}` as condition leaves alongside the existing `{"question":...}` leaf; confirm operators (`in`, `equals`, …) are shared.
4. **Range reporting** — when variants differ in item count, standardize on `mean_coded`, or attach per-variant `range` metadata to the dimension?
5. **Legacy flattening (§6b)** — emit a flattened default-coordinate OSD for variant-unaware runners now, or just update the runners?
6. **Parameter exposure** — should a free `form`/`edition` parameter be respondent-visible, administrator-only, or URL/config-set? (Reuses whatever policy `parameters` already implies.)

---

*Companion to `response_scales_proposal.md`. Together they move two kinds of cross-cutting structure — response formats and item variants — into first-class, text-free scale logic.*
