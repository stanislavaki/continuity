#!/usr/bin/env python3
"""Build assets/bill-works.json — the data behind the graph in #billReveal.

Two sources, deliberately kept from overlapping:

  * the art data set, which catalogues the paintings, sculptures, buildings,
    drawings, books and objects (426 rows, 1925-1996). It is read from a local
    export of the workbook when one is given with --art, and from the Google
    Sheet otherwise;
  * Fleischmann's catalogue of Bill's typographic work, 570 printed pieces
    for clients, 1925-1994, exported from the same workbook's typography
    sheet as an .xlsx.

The art set's own "Graphic Design" rows -- posters and advertisements -- are
dropped: the Fleischmann catalogue covers that same ground piece for piece, so
keeping both would count the posters twice. Everything else is carried.

    python3 scripts/build_bill_works.py [--art path/to/art.xlsx] [path/to/works_extracted.xlsx]

The graph on the page is built from the consolidated export,
~/Downloads/Max_Bill_Art_Data_Set_consolidated.xlsx, which carries the twenty
buildings the Google Sheet does not yet have.
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
# the labels stand in up the left of the graph, bottom first too, so each label
# stands on the same side of the list as its dots do in a column.
#
# The colours are dealt against the counts rather than by taste: the fewer works
# a practice left, the further its colour stands off the panel's near-black, so
# the rarest thing in the field is the easiest to pick out of it and the
# commonest sits back and lets the rest be seen. Sculpture is the exception --
# it holds the red outright, because it is the work this page is about.
# Measured against #050505 the six run
#
#     570  typography   #005CD3   3.37:1
#     193  painting     #00934C   5.12:1
#     109  sculpture    #E41802   4.30:1   <- held
#      28  books        #FE8C01   8.70:1
#      28  drawings     #25DDDB  12.08:1
#      20  architecture #FFB8EE  12.95:1
#      15  product      #FFD500  14.33:1
#
# The ladder climbs the whole way but for sculpture, which sits one rung below
# the painting above it: holding the red at 4.30 leaves nothing at or under it
# for painting's larger count, since the only colour lower is typography's own.
# The two clusters of 28 tie and can go either way round. Architecture came
# last, and took the one hue the six had left, a pale pink, lifted to fall
# between the drawings' 28 and product design's 15. Every colour clears 3:1.
#
# Architecture stacks straight after sculpture, so Bill's two practices in
# three dimensions stand next to each other in every column. Change one here and check the ladder, or the figure starts pointing at
# the wrong things.
DOMAINS = [
    ('typography', 'typography & print', '#005CD3'),
    ('painting',   'painting',           '#00934C'),
    ('sculpture',  'sculpture',          '#E41802'),
    ('architecture', 'architecture',     '#FFB8EE'),
    ('books',      'books & prints',     '#FE8C01'),
    ('product',    'product design',     '#FFD500'),
    ('drawing',    'drawings & graphic design', '#25DDDB'),
]
IDX = {k: i for i, (k, _, _) in enumerate(DOMAINS)}

# The art set's own Field column, mapped onto the six. None = dropped.
FIELD_TO_DOMAIN = {
    'Painting': 'painting',
    'Sculpture': 'sculpture',
    'Sculpture, Product Design': 'sculpture',
    'Architecture': 'architecture',
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

# ---- weight: how long a work took -----------------------------------------
# The page draws each work for as long as it took: from the year it was begun to
# the year it was finished, where the catalogue dates it as a range, and
# otherwise by one of five tiers estimated here. Nothing in the catalogues
# records time or importance --
# the art set's "Rank of quotation" and "X-Factor" columns are empty -- so the
# tier is estimated from what each row does say: the kind of print job, the
# canvas, the height of a sculpture, whether a building was built. These are
# rough orders of magnitude, set by rule so they can be argued with and changed
# here, not researched work by work. A work dated to a single year is drawn no
# longer than that year, whatever its tier.
#
# Each work goes out as [year begun, domain, title, tier, year finished].
TIERS = ['days', 'weeks', 'months', 'a year', 'years']
DAYS, WEEKS, MONTHS, A_YEAR, YEARS = range(5)

# The typographic catalogue, by kind: small jobs set in a day or two, against
# the posters and multi-page pieces that took weeks. "Andere" is the catalogue's
# own catch-all, mostly small printed matter, so it goes with the small jobs.
TYPO_TIER = {
    'Plakat': WEEKS, 'Prospekt': WEEKS, 'Broschüre': WEEKS, 'Katalog': WEEKS,
}


def measures_cm(text):
    """Every measure in a free-text dimension, in centimetres.

    The catalogue writes sizes every way there is -- '88 × 35 × 35 cm',
    'H 200 cm', '4,5 m hoch, 80 t schwer', '20 m bzw. 16 m hoch', '32m höhe'.
    Each comma- or semicolon-separated part is read in its own unit: metres
    where a bare 'm' follows a number, millimetres for 'mm', centimetres
    otherwise, which is also what the catalogue means when it gives no unit.
    """
    t = re.sub(r'(\d),(\d)', r'\1.\2', text or '')
    out = []
    for part in re.split(r'[;,]', t):
        nums = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', part)]
        if not nums:
            continue
        if re.search(r'\d\s*mm\b', part):
            k = 0.1
        elif re.search(r'(?<![a-zA-Z])m\b', part):
            k = 100
        else:
            k = 1
        out += [n * k for n in nums]
    return out


def canvas_m2(text):
    """A painting's area in square metres, or None if the size is not given.
    Bill's diagonal squares are measured corner to corner, and a square with
    diagonal d has area d²/2."""
    t = re.sub(r'(\d),(\d)', r'\1.\2', (text or '').split(';')[0]).lower()
    nums = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', t)]
    if not nums:
        return None
    if 'diagonal' in t:
        return nums[0] ** 2 / 2 / 1e4
    if 'ø' in t or 'durchm' in t:
        return 3.1416 * (nums[0] / 2) ** 2 / 1e4
    return nums[0] * nums[1] / 1e4 if len(nums) > 1 else None


def year_range(text, start):
    """The year a work was finished, where the catalogue dates it as a range
    begun in `start`: '1983-1986' ends in 1986, '1935–38' in 1938 and
    '1958–59–60' in 1960. A range has to open the entry -- '1937 / 1958–59' is a
    work and a later version of it, not twenty years of work -- and an open one
    ('1955–') gives no end. Anything else ends the year it began."""
    m = re.match(r'\D*?(\d{4})((?:\s*[–-]\s*\d{2,4}\b)+)', text or '')
    if not m or int(m.group(1)) != start:
        return start
    last = re.findall(r'\d{2,4}', m.group(2))[-1]
    end = int(m.group(1)[:4 - len(last)] + last)
    return end if end > start else start


def art_tier(domain, row, start):
    field = (row.get('Field') or '').strip()
    title = (row.get('Title') or '').strip()
    text = (title + ' ' + (row.get('Material') or '')).lower()
    if domain == 'architecture':
        # A building went from drawing board to site: years. A temporary
        # exhibition pavilion, and a project that was never built, took months.
        return YEARS if 'built work' in (row.get('Description') or '').lower() else MONTHS
    if domain == 'sculpture':
        size = measures_cm(row.get('Dimension'))
        if not size and re.search(r'\d\s*x', (row.get('Material') or '')):
            size = measures_cm(row.get('Material'))   # one row keeps its size there
        span = year_range(row.get('Year'), start) - start
        if size:
            top = max(size)
            if top >= 1000 or (top >= 400 and span >= 2):
                return YEARS                 # Kontinuität: 4.5 m, 1983-1986
            if top >= 300:
                return A_YEAR
            return MONTHS if top >= 100 else WEEKS
        # No size given. The rows without one are mostly the commissions that
        # stand in a square, a park or a courtyard, which is why a site is
        # named and a measurement is not.
        site = (row.get('Location') or '').strip()
        return A_YEAR if site and site not in ('—', '-', '?') else MONTHS
    if domain == 'painting':
        a = canvas_m2(row.get('Dimension'))
        if a is None:
            return WEEKS
        return DAYS if a < 0.1 else WEEKS if a < 1.5 else MONTHS
    if domain == 'books':
        if field == 'Lithograph':
            many = 'portfolio' in text or 'series' in text or title.startswith('Posters')
            return MONTHS if many else WEEKS
        # A whole book against a catalogue, a brochure or a score.
        return WEEKS if any(k in text for k in ('catalog', 'brochure', 'score')) else MONTHS
    if domain == 'product':
        return WEEKS if 'wallpaper' in text else MONTHS
    if domain == 'drawing':
        # The art set's "Other" is vessels, a glass picture, mounted design
        # panels: made things, where a drawing is a sitting or two.
        return WEEKS if field == 'Other' else DAYS
    return DAYS



def clean(s, n=96):
    s = re.sub(r'\s+', ' ', (s or '').strip()).strip(' .,;')
    return s[:n - 1] + '…' if len(s) > n else s


def read_xlsx(path):
    """The first sheet of an .xlsx, as a list of rows of {column letter: text}.

    Read straight out of the zip, since this Mac's python has no openpyxl. A
    number comes back as Excel stores it, so a whole one is written without the
    '.0' a float would carry -- the consolidated export keeps its years, and one
    sculpture's title ('22'), as numbers.
    """
    book = zipfile.ZipFile(path)
    ns = {'m': NS[1:-1]}
    rel = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    first = ET.fromstring(book.read('xl/workbook.xml')).find('.//m:sheets/m:sheet', ns)
    target = next(r.get('Target') for r in ET.fromstring(book.read('xl/_rels/workbook.xml.rels'))
                  if r.get('Id') == first.get(rel))
    target = target.lstrip('/')
    target = target if target.startswith('xl/') else 'xl/' + target
    strings = [''.join(t.text or '' for t in si.iter(NS + 't'))
               for si in ET.fromstring(book.read('xl/sharedStrings.xml'))
                            .findall('m:si', ns)]

    def cell(c):
        t, v = c.get('t'), c.find('m:v', ns)
        if t == 'inlineStr':
            return ''.join(x.text or '' for x in c.iter(NS + 't'))
        if v is None:
            return ''
        if t == 's':
            return strings[int(v.text)]
        if t in (None, 'n') and re.fullmatch(r'-?\d+\.0+', v.text):
            return v.text.split('.')[0]
        return v.text

    return [{re.match(r'[A-Z]+', c.get('r')).group(): cell(c) for c in row.findall('m:c', ns)}
            for row in ET.fromstring(book.read(target)).findall('.//m:sheetData/m:row', ns)]


def art_rows(path):
    """The art data set's rows as dicts keyed by header: from the local
    workbook when there is one, and from the Google Sheet otherwise."""
    if path:
        rows = read_xlsx(path)
        head = rows[0]
        return [{head[k]: v for k, v in r.items() if k in head} for r in rows[1:]
                if any((v or '').strip() for v in r.values())]
    # Fetched with curl rather than urllib: this Mac's python carries its own
    # certificate bundle, which does not trust the system roots, so urllib
    # cannot open a Google URL while curl can.
    csv_text = subprocess.run(['curl', '-sSLf', ART_URL],
                              capture_output=True, text=True, check=True).stdout
    return list(csv.DictReader(io.StringIO(csv_text)))


def main():
    args = sys.argv[1:]
    art_path = None
    if '--art' in args:
        i = args.index('--art')
        art_path = os.path.expanduser(args[i + 1])
        del args[i:i + 2]
    typo_path = args[0] if args else TYPO_DEFAULT
    works, dropped = [], collections.Counter()

    # --- the art data set -------------------------------------------------
    for row in art_rows(art_path):
        field = (row.get('Field') or '').strip()
        # An unknown field is a work all the same; it lands in the last cluster.
        domain = FIELD_TO_DOMAIN.get(field, 'drawing')
        if domain is None:
            dropped['graphic design (already in the typographic catalogue)'] += 1
            continue
        year = (row.get('Beginning') or '').strip()
        if not re.fullmatch(r'\d{4}', year):
            dropped['no year'] += 1
            continue
        works.append([int(year), IDX[domain], clean(row.get('Title')), art_tier(domain, row, int(year)),
                      year_range(row.get('Year'), int(year))])

    # --- the typographic catalogue ---------------------------------------
    for col in read_xlsx(typo_path)[1:]:
        year = (col.get('A') or '').strip()
        if not re.fullmatch(r'\d{4}', year):
            dropped['no year'] += 1
            continue
        raw = (col.get('C') or '').strip()
        kind = KIND.get(raw, raw.lower())
        client = clean(col.get('B'), 60)
        works.append([int(year), IDX['typography'],
                      clean(f'{kind} — {client}' if client else kind),
                      TYPO_TIER.get(raw, DAYS), int(year)])

    # By year, then domain -- the order a column stacks in -- and within a
    # domain the heaviest first, so each run of dots stands on its largest.
    works.sort(key=lambda w: (w[0], w[1], -w[3]))
    per_domain = collections.Counter(w[1] for w in works)

    payload = {
        'domains': [{'key': k, 'label': label, 'color': colour, 'n': per_domain[i]}
                    for i, (k, label, colour) in enumerate(DOMAINS)],
        'tiers': TIERS,
        'works': works,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))

    years = [w[0] for w in works]
    print(f'{len(works)} works, {min(years)}-{max(years)} -> {OUT}')
    tiered = collections.Counter((w[1], w[3]) for w in works)
    print(f'  {"":32s}' + ''.join(f'{t:>8s}' for t in TIERS))
    for i, (_, label, _) in enumerate(DOMAINS):
        print(f'  {per_domain[i]:4d}  {label:26s}' +
              ''.join(f'{tiered[(i, t)] or "":>8}' for t in range(len(TIERS))))
    for reason, n in dropped.items():
        print(f'  dropped {n}: {reason}')


if __name__ == '__main__':
    main()
