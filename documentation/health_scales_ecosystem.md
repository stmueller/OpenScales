# The Health-Measurement Ecosystem — Players, Interoperability Layers, and Where OpenScales Fits

*A landscape reference for OpenScales. Compiled 2026-07-11. Companion to
`SPECIFICATION.md` (Roadmap R3: `codes`) and `TODO.md` (FHIR runner output).*

Health/psychological measurement is not one thing — it's a **stack of separable
layers**, and each "player" operates on one or two of them. Confusing the layers is
what makes the landscape seem chaotic (e.g. "is ICHOM like MAPI?" — no, they're on
different layers). This document maps the layers, the players, and the standards.

---

## 1. The five layers

| Layer | What it is | Example artifacts |
|-------|-----------|-------------------|
| **A. Content** | the actual instrument — item wording, response options, scoring, translations | the PHQ-9 questionnaire itself; a `.osd` file |
| **B. Curation / recommendation** | *which* measures to use for a condition/domain, and when | ICHOM Standard Sets, PhenX protocols, COMET core outcome sets, CDISC QRS |
| **C. Terminology (codes)** | controlled vocabularies giving each concept/question/answer a stable code | LOINC, SNOMED CT, ICD-10 |
| **D. Format / exchange** | the machine-readable file structure that carries content + codes | FHIR Questionnaire/SDC, CDISC ODM, REDCap data dictionary, `.osd`, QTI |
| **E. Distribution / licensing** | how you obtain the content and under what rights | Mapi/ePROVIDE, HealthMeasures, ICHOM, OpenScales, journal archives |

**Key mental model:** *Content* (A) is what's copyrighted and licensed (E). *Codes* (C)
give it meaning; *Formats* (D) package it; *Curation* (B) tells you which to use.
Terminology and format are the **interoperability** layers — they are largely orthogonal
to the licensing fight over content.

---

## 2. The players

### ICHOM — International Consortium for Health Outcomes Measurement
- **Layer:** B (curation) + C/D (its "IT-ready" sets add codes + format). **NOT a content vault.**
- Non-profit standards body. Publishes **~47 "Standard Sets"** — per-condition consensus
  bundles of *which* outcomes matter (clinical + PROM + case-mix + timing). Covers ~60% of
  global disease burden. (The "800–900" one sometimes sees is *data elements*, not sets.)
- **Standard Set PDFs are free** (registered users). **IT-ready** machine-readable versions
  (data dictionaries + **LOINC/SNOMED/ICD-10** mappings + **JSON** + **HL7 FHIR** IGs) may
  carry fees for commercial use; free for research/low-resource/patient/contributor use.
- **Does NOT license the instruments** — "some PROMs may require a license" from their owners.
- Site: https://www.ichom.org/  ·  IT-ready: https://www.ichom.org/it-ready-sets/  ·
  local note: `misc/ICHOM/README.md`.

### MAPI Research Trust / ePROVIDE
- **Layer:** E (distribution/licensing) + A (holds content). **The content clearinghouse.**
- Licenses and distributes the actual **COA/PROM content** — items, official translations,
  scoring/user manuals, permissions. Many instruments are fee/permission-gated. This is the
  "vault" most copyrighted clinical PROMs flow through (ePROVIDE, formerly PROQOLID).
- OpenScales status: a **collaboration is in discussion** (no result yet); their licensed
  COAs are the biggest gated content pool. Site: https://eprovide.mapi-trust.org/

### PhenX Toolkit
- **Layer:** B (curation) + D (provides data dictionaries / REDCap formats).
- NIH/NHGRI-funded (RTI International). "**Ph**enotypes and e**X**posures" — a catalog of
  **recommended, standardized measurement protocols** organized by research domain, so studies
  measure the same things the same way. Free. Ships **Data Collection Worksheets + REDCap
  zips + data dictionaries**; measures carry **PhenX IDs**. Mix of free and licensed underlying
  instruments. OpenScales already implements a chunk (see `scales/phenx/`, `tools/convert_phenx_to_osd.py`).
- Site: https://www.phenxtoolkit.org/

### PROMIS / HealthMeasures
- **Layer:** A (content) + E (distribution, free-with-terms).
- NIH-developed **item banks + short forms + computer-adaptive tests** (PROMIS, Neuro-QoL,
  ASCQ-Me, NIH Toolbox), distributed via **HealthMeasures** (Northwestern). Modern, **free to
  use under their own terms** (generally reproducible for research), IRT-scored. Frequently the
  *free* recommended instrument inside ICHOM/PhenX sets. Site: https://www.healthmeasures.net/

### REDCap
- **Layer:** D (format) + a data-capture platform. **Not a scale registry.**
- Vanderbilt's research electronic data-capture platform. Its **"data dictionary" is a CSV**
  format defining instruments (field name, type, choices, branching logic) — a *de-facto*
  standard in academic research, but **proprietary and un-coded by default**. Has a **Shared
  Library** of instruments and **CDIS** (Clinical Data Interoperability Services) that pulls EHR
  data via **FHIR**. Site: https://projectredcap.org/

### CDISC (QRS + ODM)
- **Layer:** B (curation) + D (format) — the *clinical-trials* standard.
- **QRS** (Questionnaires, Ratings and Scales) supplements standardize named scales (items +
  scoring) for regulatory analysis datasets (SDTM/ADaM). **ODM** is CDISC's XML CRF/exchange
  format. Site: https://www.cdisc.org/standards/foundational/qrs

### COMET Initiative
- **Layer:** B (curation). Academic **core outcome sets** — consensus on *which outcomes* to
  measure per condition (broader/research-driven cousin of ICHOM). https://www.comet-initiative.org/

### Scale archives / journals (content sources we mine)
- **ZIS / GESIS** (social-science scales), **ZPID/PsychArchives**, **Dove Press** journals,
  **BMC/PLoS** open access, **HTx** PROM overview — layer A/E sources of publishable instruments.
  (See `misc/GESIS/`, `misc/ZPID/`, `misc/DovePress/`, `misc/HTx/`.)

### OpenScales (us)
- **Layer:** A (open content) + D (`.osd` format) + a runner + converters. Soon **C** (codes).
- An **open repository** of runnable, scored, translated instruments in the JSON-native **`.osd`**
  format, with a client-side runner and exporters to many platforms. The distinctive combination:
  *open + runnable + scored + translated*, and (planned) *code-mapped*.

---

## 3. The interoperability layers in detail

### C. Terminology / code systems (what the data *means*)
| System | Codes what | Licensing | Role for scales |
|--------|-----------|-----------|-----------------|
| **LOINC** (Regenstrief) | observations/measurements — incl. **survey instruments, items, and answers** (as *panels* + *answer lists* `LA…`) | **free** (registration) | the primary code system for PROM items/answers; publishes panels **as FHIR Questionnaires** |
| **SNOMED CT** (SNOMED Int'l) | fine-grained clinical concepts (~350k) | **Affiliate License** required in non-member countries | diagnoses/findings referenced by a scale; redistribution is gated |
| **ICD-10** (WHO) | disease **categories** (~14k; ICD-10-CM ~70k) | free (WHO) | diagnosis/case-mix variables; billing/statistics layer |
| **UMLS** (NLM) | meta-thesaurus mapping *across* LOINC/SNOMED/ICD/etc. | free (UMLS license) | crosswalks between the above |

Division of labour: **LOINC = observations & survey Q/A · SNOMED = detailed clinical concepts ·
ICD-10 = coarse diagnosis/billing.** SNOMED and ICD-10 overlap on diseases (granular vs coarse).

### D. Exchange formats (how the file is *written*)
| Format | Owner | Notes |
|--------|-------|-------|
| **FHIR `Questionnaire` + SDC** | HL7 | **the interoperability standard** for defining/exchanging a scale: item hierarchy, `answerOption` bound to LOINC answer lists, `enableWhen` skip logic, **scoring via `itemWeight`** (formerly `ordinalValue`) + `calculatedExpression`. Serialized as **JSON** or XML. Closest analog to `.osd`. |
| **CDISC ODM** | CDISC | XML CRF/questionnaire exchange for trials |
| **REDCap data dictionary** | Vanderbilt | CSV instrument definition; ubiquitous, proprietary, un-coded by default |
| **QTI** | 1EdTech | assessment/test interchange (education-leaning) |
| **`.osd`** | OpenScales | JSON-native; items + response scales + **scoring** + **translations** + variants, first-class; simpler than FHIR but similar scope |

**JSON** is not a vocabulary — it is the common **envelope**. `.osd` is JSON; FHIR resources are
usually JSON; ICHOM ships JSON. The *coded meaning* lives inside via LOINC/SNOMED/ICD-10.

---

## 4. Where `.osd` sits, and the plan

`.osd` occupies the same niche as **FHIR Questionnaire + SDC** (content + answers + scoring +
skip logic + translations) but is JSON-native, simpler, and treats **scoring and translations as
first-class** rather than extension-bolt-ons. What it lacks today is the **terminology layer (C)**.

**The roadmap to interoperate with this whole ecosystem:**
1. **`codes` metadata in `.osd`** — optional LOINC/SNOMED/ICD-10 codes on the scale, items, and
   answer options (**SPECIFICATION.md Roadmap R3**). LOINC-first (free); SNOMED only where its
   Affiliate License permits. Additive/optional — no existing `.osd` breaks.
2. **`osd` → FHIR conversion tool (`convert_to_fhir.py`)** — emit a FHIR **`Questionnaire`**
   (weights via `itemWeight`, answers via LOINC answer lists, skip logic via `enableWhen`) and,
   at runtime, a **`QuestionnaireResponse` / `Observation`** from the runner (**TODO: "FHIR
   Interoperability (scale-runner)"**). **This is the key next tool to build once R3 lands.**
3. Result: an `.osd` administered by the runner (self-hosted or embedded) can export
   FHIR-conformant, code-mapped data that plugs straight into **EHRs, outcome registries, and
   ICHOM's IT-ready pipeline** — the interoperability value that is attractive to commercial and
   registry partners *independent of* the open-vs-licensed content question.

---

## 5. Public FHIR `Questionnaire` archives, tools, and the round-trip opportunity

FHIR resources are representation-agnostic (**XML / JSON / RDF-Turtle**; the spec models them
in UML), and there is a real public corpus of FHIR `Questionnaire` instruments to align with.

### Canonical, terminology-backed (largest)
- **LOINC FHIR terminology service** — LOINC publishes its **Panels & Forms** (PROMs +
  standardized assessment instruments) *as* FHIR `Questionnaire`s, retrievable at canonical URLs
  `http://loinc.org/q/{LOINC-code}` from the LOINC FHIR server (`https://fhir.loinc.org`).
  Hundreds of instruments (PHQ-9/-2, GAD-7, AUDIT, FACIT/FACT family, ...).
  https://loinc.org/fhir/ · https://loinc.org/panels/
- **NLM CDE Repository** — NIH Common Data Elements, exportable as FHIR Questionnaires.
  https://cde.nlm.nih.gov/
- **NLM LForms + Form Builder** (Lister Hill / NLM) — a form renderer *and* authoring tool that
  imports LOINC panels → FHIR `Questionnaire`, with a browsable demo library and a SMART-on-FHIR
  app. Form Builder https://formbuilder.nlm.nih.gov/ · LHC-Forms demo
  https://lhcforms.nlm.nih.gov/lhcforms · https://github.com/lhncbc/lforms ·
  SMART app https://github.com/lhncbc/lforms-fhir-app

### Standards / reference examples
- HL7 FHIR spec example Questionnaires: https://hl7.org/fhir/questionnaire-examples.html
- **SDC** Implementation Guide (scoring via `itemWeight`, skip logic, LOINC-bound examples):
  https://hl7.org/fhir/uv/sdc/
- Argonaut Questionnaire (simple-assessment guidance + examples):
  https://github.com/argonautproject/questionnaire
- ICHOM FHIR IGs (e.g. breast cancer): https://build.fhir.org/ig/HL7/fhir-ichom-breast-cancer-ig/

### Community GitHub collections
- **smart-on-fhir/sample-patients-prom** — PROM Questionnaires + responses:
  https://github.com/smart-on-fhir/sample-patients-prom
- **uwcirg/fhir-questionnaires** — curated Questionnaire JSONs: https://github.com/uwcirg/fhir-questionnaires
- **navikt/fhir-questionnaires** (Norway NAV), **i4mi/fhir-questionnaire** — national/institutional sets
- Topic hub: https://github.com/topics/fhir-questionnaire

### Live FHIR servers (queryable for `Questionnaire` resources)
- Public **HAPI test server**: `https://hapi.fhir.org/baseR4/Questionnaire`
- **LOINC FHIR server** (above); **Simplifier.net** FHIR registry: https://simplifier.net/

### The content-vs-code caveat (again)
A FHIR `Questionnaire` carries *structure + LOINC/SNOMED codes* freely, but the **item text of a
copyrighted instrument stays copyrighted**. LOINC/NLM include full item text only where permission
was granted; gated instruments (many FACIT, EORTC) provide **codes + structure, not necessarily
reproducible items**. So these archives are strongest for the **free/open** instruments and the
**coding/structure** layer — the interoperability-safe part.

### Relevance to OpenScales — a two-way bridge + validation target
- **`convert_to_fhir.py`** (`.osd` → FHIR `Questionnaire`; runner → `QuestionnaireResponse` /
  `Observation`) can be **round-trip validated against the LOINC FHIR service**: convert an `.osd`
  and diff it against LOINC's own FHIR version of the same instrument.
- A **`convert_from_fhir`** companion could **import** FHIR `Questionnaire`s → `.osd`. **Caveat
  (important):** this is a *format bridge, not a licensing shortcut.* A FHIR `Questionnaire` being
  public (on a server or GitHub) does **not** license its item content — most reproduce copyrighted
  instruments under the poster's own use rights, not a redistribution grant. `convert_from_fhir`
  would still need the same content-licensing triage we apply everywhere. Where it *does* pay off
  is the **genuinely-open subset**: HL7/SDC example forms; **public-domain / U.S.-government-authored
  instruments** (many CDC / AHRQ / NIH measures, parts of the **NLM CDE Repository**); **PROMIS /
  HealthMeasures** (free under its own terms); national-gov sets (e.g. NAV); and the LOINC FHIR
  forms whose item text is public-domain or permission-granted. Bounded, but real — and code-clean
  by construction (the *structure + LOINC/SNOMED codes* are always open even when item text is not).

### Who actually *collects* with FHIR `Questionnaire` (EHR vs. open stack)
FHIR Questionnaire is an HL7 standard — **not Epic-locked.** Two worlds use it:
- **Licensed hospital EHRs** — Epic, Oracle Health (Cerner), MEDITECH expose FHIR R4 + SMART on
  FHIR. But native SDC behavior (skip logic, scoring, pre-population) is usually delivered by a
  **SMART app embedded in the EHR**, not the EHR engine; and getting a *custom* Questionnaire into
  clinician use generally requires the health system's own **build/config** (you can't simply POST
  one to Epic and have it appear).
- **Open / standalone stack (no EHR license):**
  - *Renderers:* NLM **LForms** + `lforms-fhir-app`, **CSIRO Smart Forms** (AU), Helsenorge
    **Structor**, the fhirpath-lab Questionnaire tester.
  - *Mobile/offline:* **Google Android FHIR SDK** (Structured Data Capture) — used by **WHO SMART
    Guidelines** and global-health programs (explicitly for low-resource settings).
  - *Servers to store `QuestionnaireResponse`s:* **HAPI FHIR**, **Medplum**, **Aidbox**; cloud FHIR
    (**Google Cloud Healthcare API, Azure Health Data Services, AWS HealthLake**).
  - *National programs:* **Norway Helsenorge**, **NHS England**, **Australia** (Smart Forms / AU Core).

### Testing & ingesting an `osd → FHIR` export (practical notes)
- **Test on open servers:** (1) validate the resource with the official HL7 **FHIR validator**
  against the **SDC** profiles; (2) POST it to the public **HAPI test server** (`hapi.fhir.org`, no
  auth); (3) render it in **LForms / CSIRO Smart Forms / fhirpath-lab tester** to eyeball layout,
  skip logic, and scoring; (4) **round-trip** — fill it → get a `QuestionnaireResponse` → POST that
  back. Good CI target: validate against **FHIR R4 + SDC IG + LOINC** on each build.
- **Can users import it?** *Open stack — yes, drop-in:* a well-formed **R4** Questionnaire loads into
  any FHIR server / SDC renderer. Caveats: target **FHIR R4** (widest support); non-SDC systems
  ignore SDC extensions (scoring/skip logic degrade gracefully); commercial **EHRs are gated** —
  importing a Questionnaire for clinician use in Epic/Cerner needs the health system's IT build, not
  a simple API write.
- **Are LOINC / SNOMED / ICD-10 codes required?** *Not for basic rendering/collection* — a
  Questionnaire with **local codes** renders and collects fine and yields responses. Codes are
  needed for **meaning across systems**: LOINC lets another system recognize "this = PHQ-9 item 1"
  and file the answer to a **coded `Observation` / flowsheet** rather than opaque data; ICHOM and
  registry pipelines *require* the LOINC/SNOMED/ICD-10 mappings; ICD-10 codes the diagnosis/case-mix
  variables. So codes are **optional for collection, required for interoperable ingestion** —
  LOINC first (free), SNOMED where its license permits, ICD-10 for diagnoses. (Exactly why Roadmap
  R3 makes `codes` optional-but-valuable.)

---

## 5b. PROMIS / HealthMeasures licensing in detail

The ecosystem doc above characterizes PROMIS as "free under their own terms." That summary is
correct but understates the restriction relative to Creative Commons or public-domain instruments.

### Copyright holder and governing terms

All four HealthMeasures instrument families are **copyrighted by Northwestern University**
(Department of Medical Social Sciences, Feinberg School of Medicine) under a custom
**HealthMeasures Terms of Use** (currently v7.1 for Assessment Center). There is no CC license
and no public-domain dedication for any item, short form, or item bank.

### What "free to use" actually covers

| Use case | Allowed? | Notes |
|---|---|---|
| Administering in a single research/clinical/educational study | **Yes** (PROMIS, Neuro-QoL, ASCQ-Me) | NIH Toolbox Cognition/Motor require paid subscription ($599–$2,499/yr) |
| Reproducing item text in a published paper | **Requires written permission** | Prior written agreement needed; contact help@HealthMeasures.net |
| Redistributing item text in a software repository | **No — explicitly prohibited** | Constitutes distributing to third parties without prior written agreement |
| Embedding in a commercial product / electronic administration | **Requires HEAP permit** | ~$700/measure/3-year term; non-profits exempt from HEAP for a single study but redistribution prohibition still applies |

Verbatim from the Terms of Use:
> "User shall not reproduce HealthMeasures Instruments except as needed to conduct the authorized single use."
> "User shall not distribute, publish, sell, license, or provide HealthMeasures products to third parties... without the prior written agreement of the Provider."

### Differences among the four families

| Family | Free research use | Commercial / broader use |
|---|---|---|
| **PROMIS** | Yes | HEAP permit (~$700/measure/3yr) |
| **Neuro-QoL** | Yes | Same as PROMIS |
| **ASCQ-Me** | Yes (non-commercial) | Licensing agreement required |
| **NIH Toolbox** | Emotion/select Sensation domains only | Cognition/Motor: paid subscription; institutional quotes available |

### Assessment Center API (api.assessmentcenter.net)

Provides programmatic access to PROMIS, ASCQ-Me, and Neuro-QoL: CAT delivery, item metadata
(JSON), scoring endpoints, FHIR Questionnaire resources. Registration required (name, institution,
intended use); sandbox is free but expires after 6 months; production API carries an annual
license fee. The API can return item-level JSON, but re-hosting that content elsewhere would
still violate the same ToU prohibition on redistribution.

### No public-domain / CC subsets exist

Open-access journal articles *about* PROMIS instruments carry CC-BY — that applies to the
article text, not the item content. No carve-outs exist for specific short forms or legacy items.

### What OpenScales can do with PROMIS content

1. **Link out** — point users to HealthMeasures download pages so they agree to ToU themselves.
2. **Scoring code only** — store subscale weights and T-score lookup tables without item text,
   similar to how some platforms handle other gated content.
3. **Request permission** — contact help@HealthMeasures.net for explicit written permission for
   open-source/non-commercial repository inclusion. HealthMeasures has granted this to other
   projects; worth asking given OpenScales's non-commercial/research character.
4. **FHIR structure without item text** — LOINC publishes PROMIS *structure + codes* as FHIR
   Questionnaires (with item text where permission was granted); usable for the interoperability
   layer (codes, format) even where content redistribution is gated.

---

## 6. Strategic takeaways

- **OpenScales is unique on the intersection**: *open content* (A) + *runnable/scored/translated*
  (D + a runner) + *soon code-mapped* (C). No single other player covers all of these — MAPI has
  content+licensing but not open/runnable; ICHOM/PhenX/COMET curate but don't run; REDCap runs but
  is proprietary/un-coded; PROMIS is open-ish content but a single family.
- **Partnerships map to layers**: ICHOM/registries → interoperability (C/D, FHIR); MAPI → licensed
  content (A/E); PhenX/PROMIS → free content to implement (A). These can **fund development**
  without requiring the open repository to solve the copyrighted-content problem.
- **Build order:** R3 `codes` (format) → `convert_to_fhir.py` + runner FHIR output → then court the
  interoperability partners with a working demonstration.

### Sources / local records
`misc/ICHOM/README.md` · `misc/HTx/README.md` · `misc/DovePress/README.md` · `SPECIFICATION.md`
(R3) · `TODO.md` (FHIR runner). ICHOM: ichom.org · LOINC: loinc.org · FHIR SDC:
hl7.org/fhir/uv/sdc · CDISC QRS: cdisc.org/standards/foundational/qrs · PhenX: phenxtoolkit.org ·
HealthMeasures/PROMIS: healthmeasures.net · REDCap: projectredcap.org · MAPI/ePROVIDE:
eprovide.mapi-trust.org.
