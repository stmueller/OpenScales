# MISS Collection — Measurement Instruments for the Social Sciences

Scales in this collection are sourced from [*Measurement Instruments for the Social Sciences*](https://miss.psychopen.eu/) (MISS), an open-access peer-reviewed journal published by PsychOpen GOLD (Leibniz Institute for Psychology, ZPID).

All MISS articles are published under **CC BY 4.0**, making them freely implementable in OSD format.

## Directory naming convention

Each scale directory is named after its **MISS article ID** (the numeric identifier in the article URL and DOI):

```
scales/miss/{article_id}/{article_id}.osd
```

**Example** — article ID `20841`:

| Field | Value |
|-------|-------|
| Directory | `scales/miss/20841/` |
| OSD file | `scales/miss/20841/20841.osd` |
| Article URL | `https://miss.psychopen.eu/index.php/miss/article/view/20841` |
| DOI | `https://doi.org/10.5964/miss.20841` |

The article ID is the canonical key — it appears in the directory name, the OSD filename, and is embedded in the `scale_info.url` field of the OSD file.

## OSD conventions for MISS scales

Every MISS scale OSD should include:

```json
{
  "scale_info": {
    "url": "https://miss.psychopen.eu/index.php/miss/article/view/{article_id}",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "license_explanation": "Published in Measurement Instruments for the Social Sciences under CC BY 4.0."
  },
  "implementation": {
    "author": "...",
    "organization": "OpenScales Project",
    "date": "YYYY-MM-DD",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "notes": "MISS article ID: {article_id}. DOI: 10.5964/miss.{article_id}"
  }
}
```

## Excluding scales

Add a row to `EXCLUDE.csv` to suppress a scale from the website manifest without removing the OSD file:

```csv
code,reason
20841,Example: clinician-administered, not suitable for self-report
```

Then rebuild the manifest:

```bash
python3 tools/build_manifest_miss.py
```
