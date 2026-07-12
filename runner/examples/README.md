# Self-hosting the OpenScales runner

A minimal, complete example of an author **self-hosting a single scale** with the
OpenScales runner. It administers, scores, and shows a report entirely in the browser —
**no server and no PHP required**.

See `index.html` in this folder (the example scale is **DEMO5**, an original CC0 sample).

## Files
- `index.html` — the demo page: mounts the runner and points it at the `.osd`
- `DEMO5.osd` — a single self-contained scale-definition bundle (definition + translations + scoring)
- `scale-runner.js`, `scale-runner.css` — the runner engine + styles (here referenced one level up in `../`, since they live in the OpenScales `runner/` directory)

## Self-host it for your own scale, on your own site
1. Put these files in **one folder** on any static web host (GitHub Pages, Netlify, S3, plain nginx/Apache):
   - `scale-runner.js` and `scale-runner.css` (copy from the OpenScales `runner/` directory)
   - your `myscale.osd`
   - a copy of `index.html`
2. In `index.html`, point the two asset paths at the same folder (`scale-runner.css`, `scale-runner.js`)
   and set `osdURL: 'myscale.osd'`.
3. Open it **over http(s)** — not `file://`. Browsers block `fetch()` of the `.osd` on `file://`.
   Quick test: run `python3 -m http.server` in the folder, then visit `http://localhost:8000/`.

That's the whole minimal set: **one HTML page + `scale-runner.js` + `scale-runner.css` + your `.osd`.**

## Notes
- **No PHP to run/score.** A backend is only needed to *save* responses — set `demo: false` and
  `collect: 'your-endpoint'` (any URL that accepts a multipart POST; it does not have to be PHP).
  Otherwise use the `onComplete` callback / the `peblTestComplete` DOM event to handle results in JS.
- The `.osd` can be served same-folder, or remotely via `osdURL: 'https://…'` (the host must send
  CORS headers — OSF downloads and GitHub-raw do).
- Convert an `.osd` to Qualtrics, REDCap, SurveyJS, LimeSurvey, formr, and more:
  <https://openscales.net/convert.php>
- Format spec and project home: <https://openscales.net>
