# Open Scale Chain (OSC) Specification v0.1 — DRAFT

*Companion format to the [Open Scale Definition (OSD) Specification](SPECIFICATION.md)*

A JSON format for defining multi-scale study sessions — chaining consent forms, scales, and completion actions into a single runnable protocol.

## Overview

An OSC file (`.osc`) describes a **study session**: an ordered sequence of OSD scales, consent gates, between-subjects assignments, and completion actions. It is intentionally separate from the OSD format — scales remain pure instrument definitions; study-level orchestration lives here.

**Design goals:**
- A researcher can define a complete study protocol in one file
- The runner loads the `.osc`, walks the chain, invokes the existing scale runner for each step
- Results are uploaded per-scale, plus a master session log with timestamps
- No server-side logic required — the runner handles flow, randomization, and data submission client-side

---

## File Structure

```
my_study.osc                — Study chain definition (required)
scales/                     — Local OSD files (optional; scales may also be URLs)
  Consent.osd
  AUDIT.osd
  PHQ9.osd
  ...
```

---

## Top-Level Fields

```json
{
  "osc_version": "0.1",
  "study_info": { ... },
  "parameters": { ... },
  "data": { ... },
  "chain": [ ... ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `osc_version` | string | yes | Specification version (currently `"0.1"`) |
| `study_info` | object | yes | Study metadata |
| `parameters` | object | no | Variables available throughout the chain |
| `data` | object | no | Data upload and session logging configuration |
| `chain` | array | yes | Ordered sequence of steps to execute |

---

## S1. Study Metadata (`study_info`)

```json
{
  "study_info": {
    "name": "Alcohol Recovery Study — Wave 2",
    "code": "ARS_W2",
    "version": "1.0",
    "description": "Monthly assessment battery for alcohol recovery participants.",
    "irb": "UW-2024-0847",
    "contact": "lab@example.edu"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Display name of the study |
| `code` | string | no | Short identifier |
| `version` | string | no | Study protocol version |
| `description` | string | no | Brief description |
| `irb` | string | no | IRB protocol number |
| `contact` | string | no | Contact email for participants |

---

## S2. Parameters

Parameters are named variables available throughout the chain — in URLs, data filenames, and condition assignments. Values come from URL query parameters, random generation, or explicit defaults.

```json
{
  "parameters": {
    "pid": {
      "source": "url",
      "required": true,
      "description": "Participant ID"
    },
    "session": {
      "source": "url",
      "default": "1",
      "description": "Session number"
    },
    "condition": {
      "source": "random",
      "values": ["A", "B", "C"],
      "description": "Between-subjects condition assignment"
    },
    "timestamp": {
      "source": "auto",
      "type": "iso8601",
      "description": "Session start timestamp (generated automatically)"
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | `"url"` (from query param), `"random"` (random selection), `"auto"` (system-generated), `"fixed"` (hardcoded value) |
| `required` | boolean | If `true` and `source` is `"url"`, the runner MUST halt with an error if the parameter is missing |
| `default` | any | Fallback value when source is `"url"` and the parameter is absent |
| `values` | array | For `source: "random"` — the set of values to choose from (uniform random) |
| `type` | string | For `source: "auto"` — `"iso8601"` (current datetime), `"uuid"` (random UUID), `"sequential"` (auto-incrementing, requires server support) |
| `value` | any | For `source: "fixed"` — the literal value |
| `description` | string | Human-readable description |

**Variable substitution:** Parameters are referenced as `${name}` in string fields throughout the chain (URLs, filenames, etc.). The runner performs literal string replacement before using the value. Unresolved `${...}` references are left as-is (not an error) to allow pass-through to external systems.

---

## S3. Data Upload and Session Log (`data`)

```json
{
  "data": {
    "endpoint": "https://myserver.example.com/upload",
    "method": "POST",
    "filename_pattern": "${study_code}_${pid}_${scale_code}_${timestamp}.csv",
    "session_log": true,
    "session_log_filename": "${study_code}_${pid}_session_${timestamp}.json",
    "headers": {
      "X-Study-Key": "abc123"
    }
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `endpoint` | string | none | URL to POST result data to. If omitted, data is offered as local download only. |
| `method` | string | `"POST"` | HTTP method for upload |
| `filename_pattern` | string | `"${scale_code}_${pid}.csv"` | Template for per-scale data filenames |
| `session_log` | boolean | `true` | Whether to generate and upload a master session log |
| `session_log_filename` | string | `"session_${pid}_${timestamp}.json"` | Filename for the session log |
| `headers` | object | `{}` | Additional HTTP headers sent with each upload (e.g., API keys) |
| `include_condition` | boolean | `true` | Whether to include the `condition` parameter value in each data file |

### Session Log Format

The session log is a JSON file recording the participant's path through the chain:

```json
{
  "osc_version": "0.1",
  "study_code": "ARS_W2",
  "pid": "P042",
  "condition": "B",
  "session_start": "2026-03-28T14:30:00Z",
  "session_end": "2026-03-28T14:52:13Z",
  "parameters": { "pid": "P042", "session": "2", "condition": "B" },
  "steps": [
    {
      "step": 1,
      "type": "consent",
      "scale_code": "Consent",
      "started": "2026-03-28T14:30:00Z",
      "completed": "2026-03-28T14:31:12Z",
      "outcome": "consented"
    },
    {
      "step": 2,
      "type": "scale",
      "scale_code": "AUDIT",
      "started": "2026-03-28T14:31:12Z",
      "completed": "2026-03-28T14:35:44Z",
      "outcome": "completed",
      "data_file": "ARS_W2_P042_AUDIT_20260328.csv"
    },
    {
      "step": 3,
      "type": "scale",
      "scale_code": "PHQ9",
      "started": "2026-03-28T14:35:44Z",
      "completed": "2026-03-28T14:40:01Z",
      "outcome": "completed",
      "data_file": "ARS_W2_P042_PHQ9_20260328.csv"
    }
  ]
}
```

---

## S4. Chain Steps

The `chain` is an ordered array of step objects. The runner executes steps sequentially unless flow control (gates, branches) alters the path.

### Step Types

| Type | Description |
|------|-------------|
| `consent` | Consent form — runs an OSD, checks for consent response |
| `scale` | Standard scale administration |
| `branch` | Between-subjects or conditional branching |
| `redirect` | Navigate to an external URL (e.g., completion page) |
| `message` | Display a static message (instructions, debriefing) |

### Common Step Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Step type (see table above) |
| `id` | string | Optional unique identifier for the step (used in skip/branch logic) |

---

### `consent` Step

Runs an OSD consent form. If the participant declines, the runner skips all remaining steps (or jumps to a specified step).

```json
{
  "type": "consent",
  "osd": "Consent.osd",
  "consent_item": "consent_agree",
  "consent_value": "yes",
  "on_decline": "end",
  "decline_message": "decline_msg"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `osd` | string | required | Path or URL to the consent OSD file |
| `consent_item` | string | required | Item ID in the OSD whose response determines consent |
| `consent_value` | any | required | The response value that indicates consent was given |
| `on_decline` | string | `"end"` | What to do if consent is not given: `"end"` (stop session), `"skip"` (skip to next step), or a step `id` to jump to |
| `decline_message` | string | none | Translation key in the OSD for a message shown on decline |
| `parameters` | object | `{}` | Parameters to pass to this OSD (overrides study-level params) |

---

### `scale` Step

Runs a standard OSD scale.

```json
{
  "type": "scale",
  "osd": "AUDIT.osd",
  "parameters": {
    "lang": "es"
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `osd` | string | required | Path or URL to the OSD file |
| `parameters` | object | `{}` | Parameters passed to the scale runner (e.g., `lang`, `show_header`, scale-specific params) |

---

### `branch` Step

Selects one of several sub-chains based on a parameter value or random assignment.

```json
{
  "type": "branch",
  "on": "${condition}",
  "arms": {
    "A": [
      { "type": "scale", "osd": "FormA_Battery.osd" }
    ],
    "B": [
      { "type": "scale", "osd": "FormB_Battery.osd" }
    ],
    "C": [
      { "type": "scale", "osd": "FormC_Short.osd" },
      { "type": "scale", "osd": "FormC_Long.osd" }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `on` | string | The value to branch on — typically a `${parameter}` reference. Resolved before matching. |
| `arms` | object | Keys are possible values of `on`; values are arrays of chain steps (sub-chains). |
| `default` | array | Optional sub-chain executed when `on` doesn't match any arm key. |

**Use case — randomized forms:** Define `condition` as a `"random"` parameter with `values: ["A", "B", "C"]`. The `branch` step routes each participant to their assigned form.

**Use case — adaptive testing:** Branch on a computed score from an earlier scale (requires the runner to expose prior scale scores as parameters — future extension).

---

### `redirect` Step

Navigates the browser to an external URL. Typically the final step — used for Sona/MTurk/Prolific completion callbacks.

```json
{
  "type": "redirect",
  "url": "https://uwmadison.sona-systems.com/webstudy_credit.aspx?experiment_id=1234&credit_token=abc&survey_code=${pid}"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Target URL. Supports `${parameter}` substitution. |
| `delay` | integer | Optional delay in seconds before redirecting (to show a thank-you message) |
| `message` | string | Translation key or literal text shown while waiting for redirect |

---

### `message` Step

Displays a static message (no data collection). Useful for inter-scale instructions or debriefing.

```json
{
  "type": "message",
  "title": "Part 2",
  "text": "You have completed the first set of questionnaires. The next section asks about your experiences in the past week. Press Continue when ready.",
  "button": "Continue"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | none | Optional heading |
| `text` | string | required | Message body (plain text or HTML) |
| `button` | string | `"Continue"` | Button label to advance |

---

## S5. Scale Resolution

The `osd` field in `consent` and `scale` steps can be:

1. **Relative path** — `"AUDIT.osd"` or `"scales/AUDIT.osd"` — resolved relative to the `.osc` file's location
2. **Absolute URL** — `"https://example.com/scales/AUDIT/AUDIT.osd"` — fetched directly

For simplicity, users should host the `.osc` file and all referenced `.osd` files on the same server. If using absolute URLs pointing to a different origin, the remote server must include appropriate `Access-Control-Allow-Origin` headers for the runner to fetch the files.

---

## S6. Order Randomization

Within the chain, consecutive `scale` steps can be shuffled using a `random_group` field (analogous to item randomization in OSD):

```json
{
  "chain": [
    { "type": "consent", "osd": "Consent.osd", "consent_item": "agree", "consent_value": "yes" },
    { "type": "scale", "osd": "AUDIT.osd", "random_group": 1 },
    { "type": "scale", "osd": "PHQ9.osd", "random_group": 1 },
    { "type": "scale", "osd": "GAD7.osd", "random_group": 1 },
    { "type": "redirect", "url": "https://sona.example.com/complete?pid=${pid}" }
  ]
}
```

Steps sharing the same `random_group` are shuffled among themselves. Steps without `random_group` (or `random_group: 0`) remain in fixed position. This is within-subjects order counterbalancing.

For **between-subjects** form assignment (each participant gets one of N forms), use the `branch` step with a `"random"` parameter.

---

## Complete Example

```json
{
  "osc_version": "0.1",
  "study_info": {
    "name": "Monthly Recovery Assessment",
    "code": "MRA",
    "irb": "UW-2025-1234"
  },
  "parameters": {
    "pid": { "source": "url", "required": true },
    "session": { "source": "url", "default": "1" },
    "condition": { "source": "random", "values": ["standard", "brief"] },
    "timestamp": { "source": "auto", "type": "iso8601" }
  },
  "data": {
    "endpoint": "https://mylab.example.com/api/upload",
    "filename_pattern": "MRA_${pid}_s${session}_${scale_code}.csv",
    "session_log": true,
    "headers": { "X-API-Key": "study-key-here" }
  },
  "chain": [
    {
      "type": "consent",
      "osd": "Consent.osd",
      "consent_item": "consent_agree",
      "consent_value": "yes",
      "on_decline": "end"
    },
    {
      "type": "message",
      "title": "Welcome",
      "text": "Thank you for participating. This session includes several short questionnaires and should take about 20 minutes."
    },
    {
      "type": "branch",
      "on": "${condition}",
      "arms": {
        "standard": [
          { "type": "scale", "osd": "AUDIT.osd", "random_group": 1 },
          { "type": "scale", "osd": "PHQ9.osd", "random_group": 1 },
          { "type": "scale", "osd": "GAD7.osd", "random_group": 1 },
          { "type": "scale", "osd": "YAACQ.osd" }
        ],
        "brief": [
          { "type": "scale", "osd": "AUDIT.osd" },
          { "type": "scale", "osd": "PHQ9.osd" }
        ]
      }
    },
    {
      "type": "scale",
      "osd": "MAM.osd"
    },
    {
      "type": "message",
      "title": "Thank you!",
      "text": "You have completed this session. Your responses have been recorded. You will be redirected to receive credit."
    },
    {
      "type": "redirect",
      "url": "https://uwmadison.sona-systems.com/webstudy_credit.aspx?experiment_id=5678&credit_token=xyz&survey_code=${pid}",
      "delay": 3
    }
  ]
}
```

---

## Relationship to the OSD Specification

The OSC format is **not part of** the OSD specification. It is a companion format that orchestrates OSD scales. The OSD spec remains focused on defining individual instruments. An OSC-aware runner must also be a conforming OSD runner.

The two formats share:
- JSON encoding
- Parameter passing conventions
- The same runner infrastructure

They do not share:
- File extensions (`.osc` vs `.osd` / `.json`)
- Validation schemas
- Conformance levels

---

## Security Considerations

- **CORS:** Runners loading OSD files cross-origin must handle CORS. Document recommended server configurations.
- **Redirect URLs:** The `redirect` step navigates away from the runner. Runners SHOULD warn if the redirect URL is not HTTPS. Runners MAY maintain an allowlist of trusted redirect domains.
- **Data endpoints:** The `endpoint` URL receives participant data. Runners SHOULD use HTTPS exclusively. The `headers` field may contain API keys — `.osc` files containing credentials should not be committed to public repositories.
- **Variable injection:** `${parameter}` substitution in URLs must be URI-encoded to prevent injection. Runners MUST apply `encodeURIComponent()` (or equivalent) to parameter values before substituting into URLs.
