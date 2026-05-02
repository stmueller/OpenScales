#!/usr/bin/env python3
"""Scrape available IPIP item translations from ipip.ori.org and build
per-language master translation JSON files in scales/ipip/.

Each output file is named ipip_master_{lang}.json and has the same key structure
as ipip_master_en.json, mapping ipip_HXXX → translated text.

Only keys present in ipip_master_en.json are written (items we actually use).
Shared keys (ipip_likert_1…5, ipip_question_head, ipip_debrief) are NOT included
— those are handled per-language separately.

Usage:
    python3 tools/scrape_ipip_translations.py [--lang LANG] [--dry-run]

Options:
    --lang    Only scrape this language code (e.g. es_mx)
    --dry-run Print results without writing files
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT       = Path(__file__).parent.parent
SCALES_DIR      = REPO_ROOT / "scales" / "ipip"
TRANS_DIR       = SCALES_DIR / "translations"
ITEM_CODES_PATH = SCALES_DIR / "ipip_item_codes.json"
MASTER_EN       = TRANS_DIR / "ipip_master_en.json"
BASE_URL        = "https://ipip.ori.org/"

# Translation sources: lang_code → list of (url, format_hint)
# Format hints:
#   'num_en_tr'  — [item_num, English, Translation]   (most common)
#   'num_tr_en'  — [item_num, Translation, English]   (German, Spanish, Portuguese, ...)
#   'tr_en'      — [Translation, English]             (Russian, some 2-col)
#   'en_tr'      — [English, Translation]             (Croatian-NEO style)
#   'tr_code_en' — [Translation, IPIP_code, English]  (Swedish: has direct IPIP codes)
#   'tr_num_code'— [Translation, num, IPIP_code]      (Turkish: direct IPIP codes)
#   'fr_multi'   — French multi-column: col0=trans, col7=English
#   'hr50'       — Croatian 50: item text in col0 ending ".", English in last col
TRANSLATION_SOURCES = {
    'ar': [
        ('ArabicBigFiveFactorMarkers.htm',  'num_en_tr'),
        ('ArabicBigFiveFactorMarkers2.htm', 'num_en_tr'),
    ],
    'hy': [
        ('ArmenianIPIP-NEO-120.htm', 'num_en_tr'),
    ],
    'zh': [
        ('ChineseAB5CFactorMarkers.htm', 'num_en_tr'),
        # Mandarin NEO-120 has space in URL — skip, need manual
    ],
    'hr': [
        ('CroatianIPIP-NEOFacets.htm', 'en_tr'),
        ('Croatian100-itemBigFiveFactorMarkers-Self-Report.htm', 'hr50'),
    ],
    'da': [
        ('DanishIPIP-NEO-120.htm', 'num_en_tr'),
    ],
    'nl': [
        ('DutchIPIP-NEO-120.htm', 'num_en_tr'),
        ('DutchMini-IPIP.htm', 'num_en_tr'),
    ],
    'et': [
        ('EstonianIPIP-NEOFacets.htm', 'en_tr'),
        ('EstonianRevisedIPIP-NEOFacets.htm', 'en_tr'),
    ],
    'fr': [
        ('French50-itemBigFiveFactorMarkers&Conservatism.htm', 'fr_multi'),
        ('FrenchCanadian300-Item-IPIP-NEO.htm', 'num_tr_en'),
    ],
    'de': [
        ('German50-itemBigFiveFactorMarkers.htm', 'num_tr_en'),
        ('German100-ItemBig-FiveFactorMarkers.htm', 'num_tr_en'),
    ],
    'el': [
        ('Greek50-itemBigFiveFactorMarkers.htm', 'num_en_tr'),
    ],
    'he': [
        # [sign, Hebrew, '', English] — col1=tr, col3=en
        ('HebrewIPIP-NEOFacets.htm', 'he_neo'),
    ],
    'hu': [
        ('HungarianIPIP-NEODomains.htm', 'num_en_tr'),
        ('HungarianVIAScales.htm', 'num_en_tr'),
    ],
    'is': [
        ('IcelandicHEXACO-PI.htm', 'is_hexaco'),  # [tr, factor, facet, sign, English, ...]
    ],
    'id': [
        ('IndonesianBFM.htm', 'num_en_tr'),
        ('IndonesianBFM2.htm', 'num_en_tr'),
    ],
    'it': [
        # [#, '', key, '', facet, English, Italian_facet, Italian] — col5=en, col7=tr
        ('ItalianIPIP-NEO-120.htm', 'it_neo'),
    ],
    'ja': [
        # [English, Japanese] 2-col (UTF-8)
        ('JapaneseIPIP-NEOFacets.htm', 'en_tr'),
        ('Japanese100-ItemIPIP-NEODomains.htm', 'en_tr'),
    ],
    'ko': [
        # [English, Korean] 2-col (UTF-8)
        ('KoreanIPIP-NEO-300.htm', 'en_tr'),
    ],
    'lv': [
        ('LatvianBFFM.htm', 'num_tr_en'),
    ],
    'mk': [
        ('MacedonianIPIP-NEOFacets.htm', 'num_en_tr'),
    ],
    'fa': [
        ('FarsiBFAS.htm', 'num_en_tr'),
    ],
    'pt': [
        ('Portuguese50-itemBigFiveFactorMarkers.htm', 'num_tr_en'),
        ('Portuguese100-itemBigFiveFactorMarkers.htm', 'num_tr_en'),
    ],
    'ro': [
        ('Romanian2504Items.htm', 'num_en_tr'),
    ],
    'ru': [
        ('Russian50-itemBigFiveFactorMarkers.htm', 'tr_en'),
    ],
    'sr': [
        ('Serbian2544Items.htm', 'num_en_tr'),
    ],
    'sl': [
        ('SloveneIPIP-NEOFacets.htm', 'en_tr'),
        ('Slovene100-ItemBig-FiveFactorMarkers.htm', 'num_tr_en'),
    ],
    'es_mx': [
        ('MexicanIPIP-NEO-120.htm', 'num_en_tr'),
    ],
    'es': [
        ('SpanishBig-FiveFactorMarkers.htm', 'num_tr_en'),
    ],
    'sv': [
        ('Swedish1955Items.htm', 'tr_code_en'),
    ],
    'tr': [
        ('Turkish924Items.htm', 'tr_num_code'),
    ],
}


# ── HTML table parser ────────────────────────────────────────────────────────

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = []
        self.current_cell = []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == 'tr':
            self.current_row = []
        elif tag in ('td', 'th'):
            self.current_cell = []
            self.in_cell = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == 'tr':
            if self.current_row:
                self.rows.append(self.current_row[:])
            self.current_row = []
        elif tag in ('td', 'th'):
            text = ' '.join(self.current_cell).strip()
            text = re.sub(r'\s+', ' ', text)
            self.current_row.append(text)
            self.current_cell = []
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell and data.strip():
            self.current_cell.append(data.strip())

    def handle_entityref(self, name):
        if self.in_cell:
            ents = {'nbsp': ' ', 'amp': '&', 'apos': "'", 'lt': '<', 'gt': '>',
                    'ldquo': '\u201c', 'rdquo': '\u201d', 'lsquo': '\u2018', 'rsquo': '\u2019'}
            ch = ents.get(name, '')
            if ch:
                self.current_cell.append(ch)

    def handle_charref(self, name):
        if self.in_cell:
            try:
                ch = chr(int(name[1:], 16)) if name.startswith('x') else chr(int(name))
                self.current_cell.append(ch)
            except (ValueError, OverflowError):
                pass


def fix_encoding(text: str) -> str:
    """Fix double-encoded latin-1 → UTF-8 characters."""
    try:
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def fetch(url: str) -> str | None:
    """Fetch URL, return HTML string or None on error."""
    if not url.startswith('http'):
        url = BASE_URL + urllib.parse.quote(url, safe='/:?=&')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            ct = resp.headers.get('content-type', '')

        # Detect charset from HTTP header
        m = re.search(r'charset\s*=\s*([\w-]+)', ct)
        if m:
            declared = m.group(1).lower()
        else:
            # Check HTML meta charset
            head = raw[:2000]
            m2 = re.search(rb'charset\s*=\s*["\']?([\w-]+)', head, re.IGNORECASE)
            declared = m2.group(1).decode('ascii').lower() if m2 else None

        # Decode in preference order
        for enc in filter(None, [declared, 'utf-8', 'latin-1']):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode('latin-1', errors='replace')
    except Exception as e:
        print(f"    FETCH ERROR {url}: {e}")
        return None


def _is_header(text: str) -> bool:
    """True if text looks like a section header rather than an item."""
    t = text.strip()
    if not t:
        return True
    # ALL-CAPS short string = header (only check if text has ASCII letters)
    has_ascii_letters = any('a' <= c.lower() <= 'z' for c in t)
    if has_ascii_letters and t == t.upper() and len(t) < 60 and not any(c.isdigit() for c in t):
        return True
    # Common header strings
    lower = t.lower()
    if any(h in lower for h in ['english', 'item no', 'item #', 'translation',
                                  'key', 'factor', 'facet', 'domain', 'scale']):
        if len(t) < 30:
            return True
    return False


def _clean(text: str) -> str:
    text = fix_encoding(text.strip())
    text = re.sub(r'\s+', ' ', text)
    # Normalize trailing punctuation
    if text and not text.endswith(('.', '?', '!')):
        text += '.'
    return text


def extract_pairs(rows: list, fmt: str) -> list[tuple[str, str]]:
    """Extract (english, translation) pairs from parsed table rows.

    fmt options:
      num_en_tr   — [num, English, Translation]
      num_tr_en   — [num, Translation, English]
      en_tr       — [English, Translation]  (2-col, no num)
      tr_en       — [Translation, English]  (2-col reversed)
      tr_code_en  — [Translation, IPIP_code, English]  (Swedish)
      tr_num_code — [Translation, num, IPIP_code]       (Turkish)
      fr_multi    — French: col0=trans, col7=English (9-col)
      hr50        — Croatian: item text in col0, English in last col
    """
    pairs = []
    code_to_text: dict | None = None  # loaded lazily for code-based formats

    for row in rows:
        ncols = len(row)
        eng = trans = ''

        if fmt == 'num_en_tr':
            if ncols < 3:
                continue
            eng, trans = row[1], row[2]
        elif fmt == 'num_tr_en':
            if ncols < 3:
                continue
            trans, eng = row[1], row[2]
        elif fmt == 'en_tr':
            if ncols < 2:
                continue
            if ncols >= 3 and row[0] in ('+', '-', ''):
                # Croatian-NEO style: [sign, English, Croatian]
                eng, trans = row[1], row[2]
            else:
                eng, trans = row[0], row[1]
            # Strip leading "N. " numbering
            eng = re.sub(r'^\d+\.\s*', '', eng)
            trans = re.sub(r'^\d+\.\s*', '', trans)
        elif fmt == 'tr_en':
            if ncols < 2:
                continue
            trans, eng = row[0], row[1]
            # Russian has "1. Text." numbering — strip leading "N. "
            eng = re.sub(r'^\d+\.\s*', '', eng)
            trans = re.sub(r'^\d+\.\s*', '', trans)
        elif fmt == 'tr_code_en':
            # Swedish: [Translation, IPIP_code, English]
            if ncols < 3:
                continue
            trans, eng = row[0], row[2]
            # Swedish items may lack period
        elif fmt == 'tr_num_code':
            # Turkish: [Translation, num, IPIP_code]
            # We return (ipip_code, translation) directly — caller handles
            if ncols < 3:
                continue
            trans_text = fix_encoding(row[0].strip())
            ipip_code = row[2].strip() if row[2].strip() else ''
            if ipip_code and trans_text and not _is_header(trans_text):
                pairs.append((f'__code__{ipip_code}', trans_text))
            continue
        elif fmt == 'fr_multi':
            # French: 9 cols, col0=translation, col7=English
            if ncols < 8:
                continue
            trans, eng = row[0], row[7]
        elif fmt == 'hr50':
            # Croatian 50: [item_text_hr, 1, 2, 3, 4, 5, English]
            if ncols < 7:
                continue
            trans, eng = row[0], row[-1]
            trans = re.sub(r'^\d+\.\s*', '', trans)
        elif fmt == 'it_neo':
            # Italian: [#, '', key, '', facet, English, Italian_facet, Italian]
            if ncols < 8:
                continue
            eng, trans = row[5], row[7]
        elif fmt == 'is_hexaco':
            # Icelandic: [Translation, factor, facet, sign, English, factor_en, facet_en]
            if ncols < 5:
                continue
            trans, eng = row[0], row[4]
        elif fmt == 'he_neo':
            # Hebrew: [sign, Hebrew, '', English]
            if ncols < 4:
                continue
            trans, eng = row[1], row[3]
        else:
            # Default: try num_en_tr
            if ncols >= 3:
                eng, trans = row[1], row[2]
            elif ncols == 2:
                eng, trans = row[0], row[1]
            else:
                continue

        eng   = fix_encoding(eng.strip())
        trans = fix_encoding(trans.strip())

        if not eng or not trans:
            continue
        if _is_header(eng) or _is_header(trans):
            continue
        if eng == trans:
            continue

        # Normalize trailing punctuation on English side
        if not eng.endswith(('.', '?', '!')):
            eng += '.'

        pairs.append((eng, trans))

    return pairs


def scrape_source(url_path: str, fmt: str, text_to_code: dict,
                  en_keys: set) -> dict:
    """Scrape one translation URL. Returns dict of ipip_key → translated_text."""
    print(f"    Fetching {url_path} ...")
    html = fetch(url_path)
    if not html:
        return {}

    parser = TableParser()
    parser.feed(html)

    pairs = extract_pairs(parser.rows, fmt)
    print(f"    Found {len(pairs)} pairs")

    result = {}
    matched = 0
    for eng_or_code, trans in pairs:
        # Turkish/Swedish use direct IPIP codes
        if eng_or_code.startswith('__code__'):
            ipip_code = eng_or_code[8:]
            key = f"ipip_{ipip_code}"
        else:
            eng = eng_or_code
            code = text_to_code.get(eng)
            if not code:
                # Try without trailing period
                code = text_to_code.get(eng.rstrip('.'))
            if code:
                key = f"ipip_{code}"
            else:
                slug = re.sub(r'[^a-z0-9]+', '_', eng.lower().strip()).strip('_')[:40]
                key = f"ipip_text_{slug}"

        if key in en_keys:
            result[key] = trans
            matched += 1

    print(f"    Matched {matched}/{len(pairs)} to known keys")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lang', help='Only scrape this language (e.g. es_mx)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    # Load lookups
    if not ITEM_CODES_PATH.exists():
        sys.exit(f"Missing {ITEM_CODES_PATH} — run build_ipip_from_excel.py first")
    if not MASTER_EN.exists():
        sys.exit(f"Missing {MASTER_EN} — run build_ipip_from_excel.py first")

    text_to_code = json.loads(ITEM_CODES_PATH.read_text(encoding='utf-8'))['text_to_code']
    master_en    = json.loads(MASTER_EN.read_text(encoding='utf-8'))
    en_keys      = set(master_en.keys())

    langs = TRANSLATION_SOURCES.keys()
    if args.lang:
        if args.lang not in TRANSLATION_SOURCES:
            sys.exit(f"Unknown lang: {args.lang}. Available: {sorted(langs)}")
        langs = [args.lang]

    for lang in sorted(langs):
        sources = TRANSLATION_SOURCES[lang]
        print(f"\n=== {lang} ({len(sources)} sources) ===")

        lang_trans: dict = {}
        for url_path, fmt in sources:
            result = scrape_source(url_path, fmt, text_to_code, en_keys)
            lang_trans.update(result)  # later sources win for conflicts
            time.sleep(0.5)

        print(f"  Total unique keys for {lang}: {len(lang_trans)}")

        if not lang_trans:
            print(f"  Skipping {lang} — no translations found")
            continue

        out_path = TRANS_DIR / f"ipip_master_{lang}.json"

        if args.dry_run:
            print(f"  DRY-RUN: would write {out_path}")
            sample = list(lang_trans.items())[:3]
            for k, v in sample:
                print(f"    {k}: {v[:60]}")
        else:
            out_path.write_text(
                json.dumps(lang_trans, indent=2, ensure_ascii=False) + "\n",
                encoding='utf-8'
            )
            print(f"  Wrote {out_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
