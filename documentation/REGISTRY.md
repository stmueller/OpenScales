# Rebuilding the Scale Registry

The website uses manifest JSON files to know which scales are available. These must be rebuilt whenever scales are added, moved, or modified.

## Manifest files

| Manifest | Source directory | Builder script | Output |
|----------|-----------------|---------------|--------|
| OpenScales (public) | `scales/openscales/` | `tools/build_manifest.py` | `website/manifest.json` |
| Restricted | `scales/restricted/` | `tools/build_manifest_restricted.py` | `website/manifest_restricted.json` |
| Private | `scales/private/` | `tools/build_manifest_private.py` | `website/manifest_private.json` |
| PhenX | `data/phenx_448/osd_output/` | `tools/build_manifest_phenx.py` | `website/manifest_phenx.json` |

## How to rebuild

From the OpenScales root directory:

```bash
# Rebuild all manifests
python3 tools/build_manifest.py
python3 tools/build_manifest_restricted.py
python3 tools/build_manifest_private.py

# Copy to web server directory if needed (restricted/private are separate files)
cp website/manifest_restricted.json ../OpenScales_web/manifest_restricted.json
cp website/manifest_private.json ../OpenScales_web/manifest_private.json
```

Note: `website/manifest.json` and `../OpenScales_web/manifest.json` are the same file (hardlinked), so the openscales manifest does not need copying.

## PhenX exclusions

The PhenX manifest builder reads `scales/phenx/EXCLUDE.csv` to skip scales that should not appear on the website (e.g., requires images/diagrams, clinician-administered, no items). The .osd files remain in the repository.

To exclude a PhenX scale, add a row to `EXCLUDE.csv`:
```csv
PX100101,Requires images (pubertal development diagrams)
```

Then rebuild: `python3 tools/build_manifest_phenx.py`

## When to rebuild

- After adding, removing, or moving a scale between repositories
- After changing scale metadata (name, license, languages, etc.)
- After adding translations to an existing scale
- The `scale_status.csv` is a separate tracking file and is NOT auto-generated from manifests

## Other tools

| Tool | Purpose |
|------|---------|
| `tools/generate_index.py` | Generates `index.json` catalog (only finds `.json` definitions, not `.osd` bundles) |
| `tools/generate_readmes.py` | Auto-generates `README.md` per scale directory |
