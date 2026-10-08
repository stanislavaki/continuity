#!/usr/bin/env python3
"""Build assets/bill-works.json — the data behind the graph in #billReveal.

One source: the Max Bill works dataset the data team handed over on
2026-10-08 (Eugene Yukechev and Sofia Chernykh), one row to a work, 1,017
rows, 1925-1996, under stable IDs:

  * the works table, the art data set earlier builds read -- the paintings,
    sculptures, buildings, drawings, books and objects (MB-001 to MB-427);
  * Fleischmann's catalogue of Bill's typography, advertising and book
    design, 570 printed pieces for clients (MB-428 to MB-997);
  * eight works added by hand and twelve from Wikipedia, not yet checked
    against a source (MB-998 to MB-1017).

The graph takes the table whole: every row with a year it was begun is a
mark, filed under the table's own Field. The table flags what its makers
still doubt in its Check column -- among it two dozen of Fleischmann's pieces
that may repeat a work the works table already holds -- and those doubts are
settled there, so that a correction made in the workbook reaches the graph on
the next build rather than being made a second time here.

    python3 scripts/build_bill_works.py [path/to/Max_Bill_Works_dataset.xlsx|.csv]

Without a path it reads the workbook where the handover left it.
"""
import collections
import csv
import json
import os
import re
import statistics
import sys
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, 'assets', 'bill-works.json')
DATASET = os.path.expanduser('~/Downloads/Max_Bill_dataset_handover/Max_Bill_Works_dataset.xlsx')

# The six fields of the table, in its own words, and their colours: the
# handover's primaries and secondaries of Bill's paintings, with red kept back
# for the endless ribbon alone -- the line the page draws through the field
# (LOOP_RED there) -- but dealt out differently: sculpture takes the orange
# the handover gave product design, product design a dark magenta,
# painting a darker green than the handover's, and graphic design, the
# largest body of work, a dark grey that stands back from the rest; book
# design keeps the handover's white. Measured against the panel's #050505:
#
#     sculpture      #f07c1a  orange   7.9:1
#     graphic design #343434  grey     1.6:1
#     product design #8f1d8f  magenta  2.7:1
#     painting       #11703a  green    3.3:1
#     book design    #ffffff  white   20.6:1
#     architecture   #2f5fd0  blue     3.6:1
#
# Where the page sets type in a domain's colour it lifts a colour too dark to
# be read on the black, so the marks keep the colours as they are.
DOMAINS = [
    ('graphic',      'graphic design', '#343434'),
    ('book',         'book design',    '#ffffff'),
    ('painting',     'painting',       '#11703a'),
    ('sculpture',    'sculpture',      '#f07c1a'),
    ('architecture', 'architecture',   '#2f5fd0'),
    ('product',      'product design', '#8f1d8f'),
]
IDX = {k: i for i, (k, _, _) in enumerate(DOMAINS)}
FIELD = {
    'Graphic Design': 'graphic', 'Book Design': 'book', 'Painting': 'painting',
    'Sculpture': 'sculpture', 'Architecture': 'architecture', 'Product Design': 'product',
}

# The domains go out in the order LEAD gives, and the rest in the order Bill
# took them up. Sculpture leads because the page is about a sculpture: its key
# opens the domains' row, after the page's own key for the endless ribbon, and
# its marks are the layer along the foot of the field, so the practice the page
# follows is read first and against the ground. Architecture, the other
# practice of monuments and sites, comes next, then product design, the
# objects, then graphic design with book design beside it, the two kinds of
# printed work. The others follow by the year of each one's first work, and
# where two began the same year, the one whose works cluster earlier -- the
# earlier median year -- first. That is the order the layers stack in on the
# page, each laid on those before it, and the order the keys stand in, left to
# right. main() sorts them.
LEAD = ['sculpture', 'architecture', 'product', 'graphic', 'book']

# Graphic design's grey is dark enough to stand back while anything else is
# lit, and too dark to read the field by when it is the one domain lit -- its
# key under the pointer or pressed -- so then it turns white: its marks, its
# key and the readout. The page reads this as a domain's `lit` colour.
LIT = {'graphic': '#ffffff'}
# And its key's name, at rest, is set in a grey of its own rather than its
# marks' grey lifted until it reads: a little darker than that, so the key
# stands back with its marks. The page reads this as a domain's `ink`.
INK = {'graphic': '#666666'}

# The works the figure points to, drawn taller than any other mark and the
# only ones in the field that answer the pointer. Listed by the table's IDs,
# which stay put whatever the row order, each with the name the page gives it.
# This is the page's own selection: the table's Highlight column holds an
# earlier, longer one, and is not read.
HIGHLIGHTS = {
    'MB-008': 'Krug',
    'MB-031': 'Wellrelief',
    'MB-057': 'Quinze variations sur un même thème',
    'MB-060': 'Die unendliche schleife (Version I)',
    'MB-419': 'Pavillon Die gute Form',
    'MB-409': 'Ulm School of Design',
    'MB-179': 'Ulmer hocker',
    'MB-196': 'Junghans hand-wound kitchen clock',
    'MB-416': 'Haus Bill Zumikon',
    'MB-368': 'Pavillon-skulptur',
    'MB-380': 'Kontinuität',
}

# Titles the table gets wrong, by ID, and what they should say. The Endless
# Ribbon shown in 1942 is version III -- version II of 1937, sawn apart,
# shortened to 150 cm and given a lenticular cross-section -- where the table
# repeats "Version II".
RETITLED = {
    'MB-099': '«Die unendliche schleife» Version III',
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
# otherwise by one of five tiers estimated here. Nothing in the table records
# time or importance -- its "Rank of quotation" and "X-Factor" columns are
# empty -- so the tier is estimated from what each row does say: the kind of print job, the
# canvas, the height of a sculpture, whether a building was built. These are
# rough orders of magnitude, set by rule so they can be argued with and changed
# here, not researched work by work. A work dated to a single year is drawn no
# longer than that year, whatever its tier.
#
# Each work goes out as [year begun, domain, title, tier, year finished,
# weight, highlight] -- the weight, from 1 to 5 in tenths, is set below, and
# the last is 1 for the works in HIGHLIGHTS and 0 for the rest.
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


# ---- weight: how much a work counts ---------------------------------------
# The page draws each mark as thick as the work weighs in Bill's history, on a
# continuous scale from 1, a small printed job, to 5, a monument. Nothing in the
# data measures significance: the table has a column for exactly that,
# "Rank of quotation (1-5)", and it is empty. Until it is filled, a work's weight
# is built up here from what its own row does say:
#
#   * its practice sets where it starts (BASE), and a piece of graphic or book
#     design by what kind of piece it is (PAPER);
#   * its scale moves it within the practice -- a painting by the size of its
#     canvas, a sculpture by its height and whether it stands in public, a
#     building by whether it was built;
#   * a public museum holding it, or a note in the table that it won a Grand
#     Prix or is his principal work, lifts it;
#   * CANON lifts a short list of works whose standing is on record beyond this
#     data set. That list is an editorial call, not a measurement -- argue with
#     it here.
#
# A rank entered in the table's column replaces all of this for its work. The
# works in HIGHLIGHTS are drawn taller than any of it, whatever they weigh.
BASE = {
    'painting': 2.8, 'product': 2.8,
    'sculpture': 3.6, 'architecture': 3.6,
}
# Graphic and book design, by kind: how long it took, and what it weighs. A
# poster, draft or printed, is a public statement; a set of prints is months
# of work, and weighs as a drawing does; a catalogue, a brochure, a magazine,
# a score or a run of advertisements is a piece of work, and a whole book more
# than any of them. The drawings are the unique works on paper the table files
# under graphic design: a sheet is a sitting or two, a worked-up design --
# for a mural, a window, a memorial, a lettering -- weeks.
PAPER = {
    'poster':  (WEEKS, 1.8),
    'prints':  (MONTHS, 1.8),
    'light':   (WEEKS, 1.4),
    'book':    (MONTHS, 2.1),
    'drawing': (DAYS, 1.8),
    'design':  (WEEKS, 1.8),
}
DRAWN = re.compile(r'tusche|aquarell|gouache|bleistift|farbstift|buntstift|tempera|radierung|'
                   r'zeichnung|schnitt in|\bink\b', re.I)


def paper(row):
    """What a piece of graphic or book design is, read off its title and
    material: a poster or a poster draft; a set of prints -- a portfolio of
    lithographs, a run of silkscreens, and the print series the Wikipedia rows
    add, which come with no material; a catalogue, brochure, magazine, score
    or run of advertisements; a drawing or a design on paper; and otherwise a
    whole book."""
    title = (row.get('Title') or '').lower()
    material = (row.get('Material') or '').lower()
    text = title + ' ' + material
    if 'poster' in text or 'plakat' in text:
        return 'poster'
    if ('portfolio' in material or 'silkscreen prints' in material or
            (row.get('Data source') or '').startswith('Wikipedia')):
        return 'prints'
    if any(k in text for k in ('catalog', 'brochure', 'score', 'magazine', 'advertisement')):
        return 'light'
    if DRAWN.search(material):
        return 'design' if re.search(r'entwurf|design|reinzeichnung|schnitt in', text) else 'drawing'
    return 'book'


# Printed matter by kind: a poster is a public statement, a brochure or a
# catalogue a piece of work, an advertisement, a card or a letterhead a small job.
TYPO_WEIGHT = {'Plakat': 0.8, 'Prospekt': 0.4, 'Broschüre': 0.4, 'Katalog': 0.4}
MUSEUM = re.compile(r'museum|kunsthaus|musée|museu|museo|macba|pompidou', re.I)
CANON = [
    (r'dreiteilige einheit', 1.0),        # grand prize for sculpture, first São Paulo Bienal, 1951
    (r'unendliche schleife', 0.6),        # the Endless Ribbon, his best-known form
    (r'^kontinuität$', 0.6),              # the Frankfurt granite this page is about
    (r'large-scale version of the sculpture', 0.4),   # the first large Kontinuität, ZÜKA 1947
    (r'quinze variations', 0.8),          # the portfolio of fifteen variations, 1935-38
    (r'ulmer hocker', 0.8),               # the Ulm stool
    (r'^junghans', 0.6),                  # the Junghans clocks
    (r'kreuzzargenstuhl|cross-frame chair', 0.4),
]


def art_weight(domain, row, tier):
    rank = next((v for k, v in row.items() if k and k.startswith('Rank of quotation')), '')
    if re.fullmatch(r'[1-5](\.\d+)?', (rank or '').strip()):
        return float(rank)
    title = (row.get('Title') or '').strip()
    note = (row.get('Description') or '').lower()
    if domain in ('graphic', 'book'):
        w = PAPER[paper(row)][1]
    else:
        w = BASE[domain]
    if domain == 'painting':
        a = canvas_m2(row.get('Dimension'))
        if a is not None:
            w += -0.6 if a < 0.1 else -0.2 if a < 0.5 else 0 if a < 1.5 else 0.4 if a < 2.5 else 0.7
    elif domain == 'sculpture':
        w += {WEEKS: -0.6, MONTHS: 0, A_YEAR: 0.7, YEARS: 1.2}.get(tier, 0)
    elif domain == 'architecture':
        w += 1.0 if 'built work' in note else -0.4 if 'unrealised' in note else 0
    if MUSEUM.search(row.get('Collection') or ''):
        w += 0.3
    if 'grand prix' in note or 'principal' in note:
        w += 0.6
    for pattern, lift in CANON:
        if re.search(pattern, title.lower()):
            w += lift
            break
    return round(min(5.0, max(1.0, w)), 1)


def typo_weight(kind):
    return round(1.0 + TYPO_WEIGHT.get(kind, 0), 1)


def art_tier(domain, row, start):
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
    if domain in ('graphic', 'book'):
        return PAPER[paper(row)][0]
    if domain == 'product':
        return WEEKS if 'wallpaper' in text or 'diagram' in text else MONTHS
    return DAYS


def clean(s, n=96):
    s = re.sub(r'\s+', ' ', (s or '').strip()).strip(' .,;')
    return s[:n - 1] + '…' if len(s) > n else s


def read_xlsx(path):
    """The first sheet of an .xlsx, as a list of rows of {column letter: text}.

    Read straight out of the zip, since this Mac's python has no openpyxl. A
    number comes back as Excel stores it, so a whole one is written without the
    '.0' a float would carry -- the workbooks keep their years, and one
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
    # The handover's workbook writes its text into the cells themselves and
    # has no table of shared strings.
    strings = [''.join(t.text or '' for t in si.iter(NS + 't'))
               for si in ET.fromstring(book.read('xl/sharedStrings.xml'))
                            .findall('m:si', ns)] if 'xl/sharedStrings.xml' in book.namelist() else []

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


def table_rows(path):
    """The table's rows as dicts keyed by its header, from the workbook or from
    its CSV twin."""
    if path.lower().endswith('.csv'):
        with open(path, encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))
    rows = read_xlsx(path)
    head = rows[0]
    return [{head[k]: v for k, v in r.items() if k in head} for r in rows[1:]
            if any((v or '').strip() for v in r.values())]


def main():
    path = os.path.expanduser(sys.argv[1]) if len(sys.argv) > 1 else DATASET
    works, dropped, found = [], collections.Counter(), set()

    for row in table_rows(path):
        row = {k: (v or '').strip() for k, v in row.items() if k}
        wid, field = row.get('ID', ''), row.get('Field', '')
        if field not in FIELD:
            sys.exit(f'{wid}: no domain for the field {field!r} -- add it to FIELD')
        domain = FIELD[field]
        year = row.get('Beginning', '')
        if not re.fullmatch(r'\d{4}', year):
            dropped['no year'] += 1
            continue
        start = int(year)
        if wid in RETITLED:
            row['Title'] = RETITLED[wid]
        if row.get('Data source', '').startswith('Fleischmann'):
            # Fleischmann's pieces are named by kind and client, the kind given
            # in English so the graph speaks the page's language.
            raw = row.get('Type (source)', '')
            kind = KIND.get(raw, raw.lower() or 'printed matter')
            client = clean(row.get('Client'), 60)
            title = clean(f'{kind} — {client}' if client else kind)
            tier, weight = TYPO_TIER.get(raw, DAYS), typo_weight(raw)
        else:
            title = clean(row.get('Title'))
            tier = art_tier(domain, row, start)
            weight = art_weight(domain, row, tier)
        if wid in HIGHLIGHTS:
            title = HIGHLIGHTS[wid]
            found.add(wid)
        works.append([start, IDX[domain], title, tier, year_range(row.get('Year'), start),
                      weight, int(wid in HIGHLIGHTS)])

    missing = set(HIGHLIGHTS) - found
    if missing:
        sys.exit(f'highlights not in the table, or undated: {", ".join(sorted(missing))}')

    # LEAD first, then the rest by when Bill took each up, and every work
    # renumbered to match.
    counts = collections.Counter(w[1] for w in works)
    years = collections.defaultdict(list)
    for w in works:
        years[w[1]].append(w[0])
    lead = lambda i: LEAD.index(DOMAINS[i][0]) if DOMAINS[i][0] in LEAD else len(LEAD)
    begun = lambda i: (lead(i), min(years[i]), statistics.median(years[i]), -counts[i])
    rank = sorted(range(len(DOMAINS)), key=begun)
    renumber = {old: new for new, old in enumerate(rank)}
    domains = [DOMAINS[i] for i in rank]
    for w in works:
        w[1] = renumber[w[1]]

    # By year, then domain -- the order a column stacks in -- and within a
    # domain the heaviest first, so each run of dots stands on its largest.
    works.sort(key=lambda w: (w[0], w[1], -w[3]))
    per_domain = collections.Counter(w[1] for w in works)

    payload = {
        'domains': [dict({'key': k, 'label': label, 'color': colour, 'n': per_domain[i]},
                         **({'lit': LIT[k]} if k in LIT else {}),
                         **({'ink': INK[k]} if k in INK else {}))
                    for i, (k, label, colour) in enumerate(domains)],
        'tiers': TIERS,
        'works': works,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))

    years = [w[0] for w in works]
    print(f'{len(works)} works, {min(years)}-{max(years)} -> {OUT}')
    tiered = collections.Counter((w[1], w[3]) for w in works)
    print(f'  {"":32s}' + ''.join(f'{t:>8s}' for t in TIERS))
    for i, (_, label, _) in enumerate(domains):
        print(f'  {per_domain[i]:4d}  {label:26s}' +
              ''.join(f'{tiered[(i, t)] or "":>8}' for t in range(len(TIERS))))
    for reason, n in dropped.items():
        print(f'  dropped {n}: {reason}')
    print(f'  {len(found)} highlights')


if __name__ == '__main__':
    main()
