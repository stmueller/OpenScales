#!/usr/bin/env python3
"""Download all papers from the MISS journal (Measurement Instruments for the Social Sciences).

For each article:
  - Fetches metadata via OAI-PMH (Dublin Core)
  - Scrapes the article page to find the PDF galley URL
  - Downloads the PDF to scales/miss/{article_id}/{article_id}.pdf
  - Saves metadata to scales/miss/{article_id}/metadata.json
  - Saves BibTeX citation to scales/miss/{article_id}/citation.bib (if available)

Run from the OpenScales root directory:
    python3 tools/download_miss_papers.py

Add --dry-run to list articles without downloading.
Add --force to re-download already-present files.
"""
import argparse
import json
import re
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT  = Path(__file__).parent.parent
MISS_DIR   = REPO_ROOT / 'scales' / 'miss'
BASE_URL   = 'https://miss.psychopen.eu/index.php/miss'
OAI_URL    = BASE_URL + '/oai'
DELAY      = 1.5  # seconds between requests


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def fetch(url, binary=False):
    """Fetch a URL, return bytes or str. Raises on HTTP error."""
    req = urllib.request.Request(url, headers={'User-Agent': 'OpenScales/1.0 (openscales.net)'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    return data if binary else data.decode('utf-8', errors='replace')


# ---------------------------------------------------------------------------
# OAI-PMH harvesting
# ---------------------------------------------------------------------------

NS = {
    'oai':  'http://www.openarchives.org/OAI/2.0/',
    'dc':   'http://purl.org/dc/elements/1.1/',
    'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
}

def oai_list_records():
    """Yield one dict per article from OAI-PMH ListRecords (handles resumption)."""
    url = OAI_URL + '?verb=ListRecords&metadataPrefix=oai_dc'
    while url:
        print(f"  OAI-PMH: {url}")
        xml_text = fetch(url)
        root = ET.fromstring(xml_text)
        time.sleep(DELAY)

        for record in root.findall('.//oai:record', NS):
            header = record.find('oai:header', NS)
            if header is not None and header.get('status') == 'deleted':
                continue

            meta = record.find('.//oai_dc:dc', NS)
            if meta is None:
                continue

            def get(tag):
                el = meta.find(f'dc:{tag}', NS)
                return el.text.strip() if el is not None and el.text else ''

            def getall(tag):
                return [el.text.strip() for el in meta.findall(f'dc:{tag}', NS)
                        if el.text and el.text.strip()]

            identifiers = getall('identifier')
            article_url = next((i for i in identifiers
                                if '/article/view/' in i and not i.startswith('http://doi')), '')
            doi = next((i for i in identifiers if 'doi.org/10.5964/miss.' in i), '')
            article_id = re.search(r'/article/view/(\d+)', article_url)
            article_id = article_id.group(1) if article_id else ''

            if not article_id:
                continue

            yield {
                'article_id': article_id,
                'title':      get('title'),
                'authors':    getall('creator'),
                'abstract':   get('description'),
                'date':       get('date'),
                'language':   get('language') or 'en',
                'subjects':   getall('subject'),
                'type':       get('type'),
                'doi':        doi,
                'article_url': article_url or f'{BASE_URL}/article/view/{article_id}',
                'identifiers': identifiers,
            }

        # Resumption token
        token_el = root.find('.//oai:resumptionToken', NS)
        if token_el is not None and token_el.text and token_el.text.strip():
            url = OAI_URL + '?verb=ListRecords&resumptionToken=' + token_el.text.strip()
        else:
            url = None


# ---------------------------------------------------------------------------
# Article page scraping — find PDF galley URL
# ---------------------------------------------------------------------------

def find_galley_urls(article_id):
    """Fetch article page and return (pdf_url, xml_url) — either may be None."""
    page_url = f'{BASE_URL}/article/view/{article_id}'
    try:
        html = fetch(page_url)
    except Exception as e:
        print(f"    WARNING: could not fetch article page {page_url}: {e}")
        return None, None

    aid = re.escape(article_id)
    base = 'https://miss.psychopen.eu'

    # --- PDF ---
    # Newer articles link as /article/view/{id}/{id}.pdf — use /download/ for binary
    pdf_url = None
    if re.search(r'article/(?:view|download)/' + aid + r'/' + aid + r'\.pdf', html):
        pdf_url = f'{base}/index.php/miss/article/download/{article_id}/{article_id}.pdf'
    else:
        # Older articles: /article/view/{id}/{numeric_galley_id}
        m = re.search(r'article/(?:view|download)/' + aid + r'/(\d+)(?:["\s])', html)
        if m:
            galley_id = m.group(1)
            pdf_url = f'{base}/index.php/miss/article/download/{article_id}/{galley_id}'

    # --- XML ---
    xml_url = None
    if re.search(r'article/(?:view|download)/' + aid + r'/' + aid + r'\.xml', html):
        xml_url = f'{base}/index.php/miss/article/download/{article_id}/{article_id}.xml'

    return pdf_url, xml_url


# ---------------------------------------------------------------------------
# BibTeX download
# ---------------------------------------------------------------------------

def fetch_bibtex(article_id):
    """Try to download BibTeX citation. Returns string or None."""
    url = (f'{BASE_URL}/citationstylelanguage/download/bibtex'
           f'?submissionId={article_id}')
    try:
        return fetch(url)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Download MISS journal papers')
    parser.add_argument('--dry-run', action='store_true', help='List articles, do not download')
    parser.add_argument('--force',   action='store_true', help='Re-download already-present files')
    args = parser.parse_args()

    MISS_DIR.mkdir(parents=True, exist_ok=True)

    print("Harvesting article list via OAI-PMH ...")
    articles = list(oai_list_records())
    articles.sort(key=lambda a: a['article_id'])
    print(f"Found {len(articles)} articles.\n")

    pdf_ok = pdf_skip = pdf_fail = 0

    for art in articles:
        aid = art['article_id']
        title = art['title'][:70] + ('…' if len(art['title']) > 70 else '')
        print(f"[{aid}] {title}")

        if args.dry_run:
            print(f"  DOI: {art['doi']}")
            print(f"  Authors: {'; '.join(art['authors'])}")
            continue

        out_dir = MISS_DIR / aid
        out_dir.mkdir(exist_ok=True)

        # --- metadata.json ---
        meta_path = out_dir / 'metadata.json'
        if not meta_path.exists() or args.force:
            meta_path.write_text(json.dumps(art, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f"  Saved metadata.json")

        # --- PDF + XML ---
        pdf_path = out_dir / f'{aid}.pdf'
        xml_path = out_dir / f'{aid}.xml'
        need_pdf = not pdf_path.exists() or args.force
        need_xml = not xml_path.exists() or args.force

        if not need_pdf and not need_xml:
            print(f"  PDF and XML already present, skipping.")
            pdf_skip += 1
        else:
            pdf_url, xml_url = find_galley_urls(aid)
            time.sleep(DELAY)

            if need_pdf:
                if pdf_url:
                    try:
                        pdf_data = fetch(pdf_url, binary=True)
                        pdf_path.write_bytes(pdf_data)
                        print(f"  Downloaded PDF ({len(pdf_data)//1024} KB)")
                        pdf_ok += 1
                        time.sleep(DELAY)
                    except Exception as e:
                        print(f"  WARNING: PDF download failed: {e}")
                        pdf_fail += 1
                else:
                    print(f"  WARNING: No PDF galley URL found on article page.")
                    pdf_fail += 1

            if need_xml:
                if xml_url:
                    try:
                        xml_data = fetch(xml_url, binary=True)
                        xml_path.write_bytes(xml_data)
                        print(f"  Downloaded XML ({len(xml_data)//1024} KB)")
                        time.sleep(DELAY)
                    except Exception as e:
                        print(f"  WARNING: XML download failed: {e}")
                else:
                    pass  # XML not available for all articles (older ones)

        # --- BibTeX ---
        bib_path = out_dir / 'citation.bib'
        if not bib_path.exists() or args.force:
            bib = fetch_bibtex(aid)
            time.sleep(DELAY)
            if bib and '@' in bib:
                bib_path.write_text(bib, encoding='utf-8')
                print(f"  Saved citation.bib")
            else:
                print(f"  BibTeX not available.")

        print()

    if not args.dry_run:
        print(f"\nDone.  PDFs: {pdf_ok} downloaded, {pdf_skip} already present, {pdf_fail} failed.")


if __name__ == '__main__':
    main()
