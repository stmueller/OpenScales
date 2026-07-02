# OpenScales How-To Video Script
# "Converting and Importing a Scale into Every Supported Platform"

**Demo scale:** PHQ-9 (`scales/openscales/PHQ9/`)
**Working directory for all commands:** `OpenScales/` repo root

---

## Setup (before recording)

Run all conversions in advance so the video shows importing, not waiting for scripts:

```bash
cd ~/Dropbox/Research/pebl/OpenScales

python3 tools/convert_to_qualtrics.py  scales/openscales/PHQ9/ --output /tmp/PHQ9_qualtrics.txt
python3 tools/convert_to_limesurvey.py scales/openscales/PHQ9/ --output /tmp/PHQ9_limesurvey.txt
python3 tools/convert_to_psytoolkit.py scales/openscales/PHQ9/ --output /tmp/PHQ9_psytoolkit.txt
python3 tools/convert_to_surveyjs.py   scales/openscales/PHQ9/ --output /tmp/PHQ9_surveyjs.json
python3 tools/convert_to_surveydown.py  scales/openscales/PHQ9/ --output /tmp/PHQ9_surveydown.zip
python3 tools/convert_to_googleforms.py scales/openscales/PHQ9/ --output /tmp/PHQ9_googleforms.gs
```

Have open in advance:
- Terminal in `OpenScales/` directory
- File manager showing `/tmp/` (or Desktop if you copy files there)
- Browser tabs pre-loaded: `scale-runner.html`, Qualtrics login, LimeSurvey `localhost:8090`, PsyToolkit account, `tools/surveyjs_test.html`

---

## Section 1 — The OSD File

**Narration:** "We start with a single file — the PHQ-9 in Open Scale Definition format."

```bash
cat scales/openscales/PHQ9/PHQ9.osd | python3 -m json.tool | head -60
```

Point out: items, likert_options, translations, scoring dimensions — all in one bundle.

---

## Section 2 — OpenScales Web Runner

**Narration:** "The simplest way to run any OSD scale is the built-in web runner — no conversion needed."

1. Open browser → `http://localhost:8080/runner/scale-runner.html?scale=PHQ9&base=../scales`
2. Show the scale running — answer a few items
3. Complete it — show the score summary

**What to highlight:** No accounts, no upload, runs in the browser. Self-hostable.

---

## Section 3 — PEBL Desktop Runner

**Narration:** "The same OSD file runs on the desktop in PEBL."

1. Open PEBL launcher
2. Load `scales/openscales/PHQ9/PHQ9.osd` in ScaleRunner
3. Run through a few items
4. Show completion and data file written to disk

**What to highlight:** Offline-capable, same format as the web runner.

---

## Section 4 — Qualtrics

**Narration:** "To use this scale in Qualtrics, we run one command."

**Show the command (already run):**
```bash
python3 tools/convert_to_qualtrics.py scales/openscales/PHQ9/ --output PHQ9_qualtrics.txt
```

**Import steps:**
1. Open Qualtrics → **Create project** → **Survey** → **Import a QSF** — wait, use **Create blank survey** then **Tools → Import/Export → Import Survey**
2. Choose `PHQ9_qualtrics.txt`
3. Show the imported survey — matrix question, 4 answer options
4. Note the scoring block at the end — manual configuration needed

**What to highlight:** One command, standard Qualtrics Advanced Format, imports in seconds.

---

## Section 5 — LimeSurvey (two paths)

**Narration:** "For LimeSurvey we have two options — a direct OSD importer plugin, or a classic TSV import."

### Path A — OSD Importer Plugin (recommended)

1. Open `http://localhost:8090`
2. Log in → **Surveys** → **Create a new survey** → click **OSD Import** (plugin link)
3. Upload `scales/openscales/PHQ9/PHQ9.osd`
4. Show the imported survey — array question, subquestions, answer columns

### Path B — TSV Converter

**Show the command (already run):**
```bash
python3 tools/convert_to_limesurvey.py scales/openscales/PHQ9/ --output PHQ9_limesurvey.txt
```

1. **Surveys** → **Create a new survey** → **Import** tab → choose `PHQ9_limesurvey.txt`
2. Show the same result

**What to highlight:** Plugin path is simpler; TSV path works on any LimeSurvey instance without plugin access.

---

## Section 6 — PsyToolkit

**Narration:** "PsyToolkit is a free platform for academic survey and experiment hosting."

**Show the command (already run):**
```bash
python3 tools/convert_to_psytoolkit.py scales/openscales/PHQ9/ --output PHQ9_psytoolkit.txt
```

**Import steps:**
1. Open psytoolkit.org → log in → **My surveys** → **New survey**
2. Open `PHQ9_psytoolkit.txt` in a text editor — show the format briefly
3. Select all → copy → paste into PsyToolkit survey editor
4. Click **Compile** — show it validates
5. Click **Run** — show the survey running in browser

**What to highlight:** Free, no installation, paste-and-run.

---

## Section 7 — SurveyJS (local)

**Narration:** "SurveyJS is a popular open-source survey library. We include a local test runner."

**Show the command (already run):**
```bash
python3 tools/convert_to_surveyjs.py scales/openscales/PHQ9/ --output PHQ9_surveyjs.json
```

**Run steps:**
1. Open `tools/surveyjs_test.html` in browser (File → Open, or double-click)
2. Click **Choose file** → select `PHQ9_surveyjs.json`
3. Show the survey rendering immediately — no server, no account
4. Complete it — show the JSON results displayed at the bottom

**What to highlight:** The JSON can also be dropped into any SurveyJS-based application or hosted on Pavlovia.

---

## Section 8 — SurveyDown (R)

**Narration:** "SurveyDown is an R-based survey framework using Quarto and Shiny."

**Show the command (already run):**
```bash
python3 tools/convert_to_surveydown.py scales/openscales/PHQ9/ --output PHQ9_surveydown.zip
```

**Run steps:**
1. Unzip `PHQ9_surveydown.zip` — show 3 files: `questions.yml`, `survey.qmd`, `app.R`
2. Open RStudio (or terminal) in that folder
3. `install.packages("surveydown")` — skip if already installed
4. Run `shiny::runApp("app.R")` — survey opens in browser
5. Show the Quarto-rendered survey running

**What to highlight:** R-native, integrates with existing R data pipelines, responses go to a database or local CSV.

---

## Section 9 — Google Forms

**Narration:** "Google Forms has no file import format, but it does have a scripting API. We generate a Google Apps Script that builds the form automatically."

**Show the command (already run):**
```bash
python3 tools/convert_to_googleforms.py scales/openscales/PHQ9/ --output PHQ9_googleforms.gs
```

Briefly show the `.gs` file — point out `FormApp.create()`, `addGridItem()`, rows and columns.

**Import steps:**
1. Open forms.google.com → create a blank form
2. Click the three-dot menu (⋮) → **Script editor**
3. Select all existing code, paste contents of `PHQ9_googleforms.gs`
4. Click **Save** (floppy disk icon), then **Run** → `createForm`
5. Click **Review permissions** → **Allow**
6. Open Google Drive — find the new form, open and preview it

**What to highlight:** No account needed beyond a Google account. The script runs once and can be discarded. All 9 PHQ items appear as a single matrix grid.

---

## Section 10 — ReproSchema / ReproNim


**Narration:** "ReproSchema is a linked-data format used by the ReproNim project and tools like MindLogger. The converter produces a directory of JSON-LD files that can be hosted anywhere with a public URL."

**Show the command and output:**
```bash
python3 tools/convert_to_reproschema.py scales/openscales/PHQ9/ --output /tmp/PHQ9_reproschema/
ls /tmp/PHQ9_reproschema/
ls /tmp/PHQ9_reproschema/items/
```

Briefly show the structure: `PHQ9_schema`, `items/phq1` … `items/phq9`, `valueConstraints`.

**Show the viewer (using already-hosted PHQ-9 at openscales.net):**
1. Navigate to the ReproNim viewer URL pointing at `https://openscales.net/activities/PHQ-9/PHQ9_schema`
2. Show the PHQ-9 running in the ReproNim web UI

**Narration:** "Once you host the output directory somewhere with a public URL — GitHub Pages, openscales.net, any web server — you paste that URL into the ReproNim viewer or MindLogger and the scale is ready to use."

**What to highlight:** The viewer is already live at openscales.net/activities/ for all OpenScales scales — no upload needed for scales already in the repository.

---

## Closing

**Narration:** "One file, eight platforms. All conversions are open source — the tools are in the OpenScales repository on GitHub."

Show the repo URL / OpenScales website.

---

## Dry Run Checklist

- [ ] Run all 6 conversions in Setup block — check all output files present
- [ ] `scale-runner.html?scale=PHQ9` loads and runs correctly at localhost:8080
- [ ] PEBL ScaleRunner opens PHQ9.osd without errors
- [ ] Qualtrics import of `PHQ9_qualtrics.txt` succeeds — check matrix formatting
- [ ] LimeSurvey plugin import of `PHQ9.osd` succeeds at localhost:8090
- [ ] LimeSurvey TSV import of `PHQ9_limesurvey.txt` succeeds
- [ ] PsyToolkit compile+run succeeds after paste
- [ ] `surveyjs_test.html` loads `PHQ9_surveyjs.json` via file picker
- [ ] SurveyDown `app.R` runs without error in R
- [ ] ReproNim viewer URL loads PHQ-9 correctly (using openscales.net/activities/PHQ-9/PHQ9_schema)
- [ ] Google Forms: paste `PHQ9_googleforms.gs`, run `createForm`, verify form appears in Drive
- [ ] All 6 output files present in `/tmp/` before recording

## Open Questions to Resolve Before Recording

1. **ReproNim viewer URL** — confirm exact viewer URL pattern; PHQ-9 already hosted at openscales.net/activities/PHQ-9/PHQ9_schema so just need the viewer's `?url=` format
2. **Qualtrics import path** — double-check exact menu: Tools → Import/Export → Import Survey, or via project creation wizard
3. **PEBL ScaleRunner** — confirm PHQ9.osd loads without issues (no post-March spec features used)
4. **SurveyDown** — confirm `surveydown` package is installed in your R environment
