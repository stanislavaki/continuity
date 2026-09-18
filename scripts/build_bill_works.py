#!/usr/bin/env python3
"""Build assets/bill-works.json — the data behind the graph in #billReveal.

Two sources, deliberately kept from overlapping:

  * the art data set, a Google Sheet tab that catalogues the paintings,
    sculptures, drawings, books and objects (404 rows, 1925-1996);
  * Fleischmann's catalogue of Bill's typographic work, 570 printed pieces
    for clients, 1925-1994, exported from the same workbook's typography
    sheet as an .xlsx.

The art set's own "Graphic Design" rows -- posters and advertisements -- are
dropped: the Fleischmann catalogue covers that same ground piece for piece, so
keeping both would count the posters twice. Everything else is carried.

    python3 scripts/build_bill_works.py [path/to/works_extracted.xlsx]
"""
import collections
import csv
import io
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

SHEET = '14uaPRkNVGlXwCusyvrztC1ogfB3QBApsBhgMqKguCy8'
ART_GID = '519898136'
ART_URL = f'https://docs.google.com/spreadsheets/d/{SHEET}/export?format=csv&gid={ART_GID}'
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, 'assets', 'bill-works.json')
TYPO_DEFAULT = os.path.expanduser('~/Downloads/works_extracted_v5 (1).xlsx')

# Order matters: it is the order the dots stack in, bottom first, and the order
# the six labels stand in down the left of the graph.
#
# Sculpture takes the white -- it is the work this page is about, and white is
# what carries furthest on the panel's near-black. Typography takes the green of
# .quote-band--green and product design --signal-yellow from :root; the rest are
# given outright.
#
# The fourth quote band, the Deutsche Bank blue #0018A8, is not here: on this
# ground it comes to 1.65:1 and reads as a stain rather than a colour. It was
# drawn to carry white type on top of it, not to be type itself. Every colour
# below clears 3:1.
DOMAINS = [
    ('typography', 'typography & print', '#00934C'),
    ('painting',   'painting',           '#E41802'),
    ('sculpture',  'sculpture',          '#FFFFFF'),
    ('books',      'books & prints',     '#FE8C01'),
    ('product',    'product design',     '#FFD500'),
    ('drawing',    'drawings & objects', '#25DDDB'),
]
IDX = {k: i for i, (k, _, _) in enumerate(DOMAINS)}

# The art set's own Field column, mapped onto the six. None = dropped.
FIELD_TO_DOMAIN = {
    'Painting': 'painting',
    'Sculpture': 'sculpture',
    'Sculpture, Product Design': 'sculpture',
    'Book Design': 'books',
    'Books': 'books',
    'Lithograph': 'books',
    'Product Design': 'product',
    'Drawing': 'drawing',
    'Other': 'drawing',
    'Graphic Design': None,
}

# The typographic catalogue names each piece by kind and client; the German
# kinds are given in English so the graph speaks the page's language.
KIND = {
    'Prospekt': 'brochure', 'Anzeige': 'advertisement', 'Plakat': 'poster',
    'Briefblatt': 'letterhead', 'Karte': 'card', 'Adresskarte': 'address card',
    'Geschäftskarte': 'business card', 'Anhänger': 'tag',
    'Katalog': 'catalogue', 'Flugblatt': 'leaflet', 'Broschüre': 'booklet',
    'Entwurf': 'design', 'Andere': 'printed matter',
}

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def clean(s, n=96):
    s = re.sub(r'\s+', ' ', (s or '').strip()).strip(' .,;')
    return s[:n - 1] + '…' if len(s) > n else s


def main():
    typo_path = sys.argv[1] if len(sys.argv) > 1 else TYPO_DEFAULT
    works, dropped = [], collections.Counter()

    # --- the art data set -------------------------------------------------
    # Fetched with curl rather than urllib: this Mac's python carries its own
    # certificate bundle, which does not trust the system roots, so urllib
    # cannot open a Google URL while curl can.
    csv_text = subprocess.run(['curl', '-sSLf', ART_URL],
                              capture_output=True, text=True, check=True).stdout
    art = list(csv.DictReader(io.StringIO(csv_text)))
    for row in art:
        field = (row['Field'] or '').strip()
        # An unknown field is a work all the same; it lands in the last cluster.
        domain = FIELD_TO_DOMAIN.get(field, 'drawing')
        if domain is None:
            dropped['graphic design (already in the typographic catalogue)'] += 1
            continue
        year = (row['Beginning'] or '').strip()
        if not re.fullmatch(r'\d{4}', year):
            dropped['no year'] += 1
            continue
        works.append([int(year), IDX[domain], clean(row['Title'])])

    # --- the typographic catalogue ---------------------------------------
    book = zipfile.ZipFile(typo_path)
    ns = {'m': NS[1:-1]}
    strings = [''.join(t.text or '' for t in si.iter(NS + 't'))
               for si in ET.fromstring(book.read('xl/sharedStrings.xml'))
                            .findall('m:si', ns)]
    sheet = ET.fromstring(book.read('xl/worksheets/sheet1.xml'))

    def cell(c):
        t, v = c.get('t'), c.find('m:v', ns)
        return '' if v is None else (strings[int(v.text)] if t == 's' else v.text)

    for row in sheet.findall('.//m:sheetData/m:row', ns)[1:]:
        col = {c.get('r')[0]: cell(c) for c in row.findall('m:c', ns)}
        year = (col.get('A') or '').strip()
        if not re.fullmatch(r'\d{4}', year):
            dropped['no year'] += 1
            continue
        raw = (col.get('C') or '').strip()
        kind = KIND.get(raw, raw.lower())
        client = clean(col.get('B'), 60)
        works.append([int(year), IDX['typography'],
                      clean(f'{kind} — {client}' if client else kind)])

    works.sort(key=lambda w: (w[0], w[1]))
    per_domain = collections.Counter(w[1] for w in works)

    payload = {
        'domains': [{'key': k, 'label': label, 'color': colour, 'n': per_domain[i]}
                    for i, (k, label, colour) in enumerate(DOMAINS)],
        'works': works,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))

    years = [w[0] for w in works]
    print(f'{len(works)} works, {min(years)}-{max(years)} -> {OUT}')
    for i, (_, label, _) in enumerate(DOMAINS):
        print(f'  {per_domain[i]:4d}  {label}')
    for reason, n in dropped.items():
        print(f'  dropped {n}: {reason}')


if __name__ == '__main__':
    main()
