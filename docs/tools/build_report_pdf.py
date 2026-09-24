"""
Print docs/REPORT.md (or docs/REPORT-FA.md) to a PDF with Chrome, driven by Playwright, in the
page layout of the Farabi Campus format for B.Sc. project reports:

  * a title page, a بسم‌الله page, a page for the evaluation minutes and the abstract with its
    keywords, each followed by a blank page in the --print layout (the format asks for blank
    backs);
  * the contents and the lists of figures and tables, with page numbers filled in by further
    print passes (invisible letter markers are located by text extraction);
  * with --print, every chapter, the references, the first appendix and the closing pages
    start on an odd page, a blank page being inserted where needed (the bound copy); without
    it, the copy sent for review, chapters start on a new page and no page is blank. Chapter
    opening pages carry no header and have the page number at the bottom centre;
  * every other page carries a header rule with the section title (odd pages) or the chapter
    title (even pages) and the page number on the outer edge. The headers and numbers are
    printed by Chrome as a second, overlay PDF and drawn onto the pages as form XObjects, so
    Persian text is shaped properly and Chrome's compressed streams stay untouched;
  * mirrored margins: 2.5 cm on the binding edge, 2 cm outside, 3.5 cm at the top (2.5 cm to
    the rule), 2 cm at the bottom. The pages are printed with symmetric margins and their
    content is shifted 2.5 mm towards the outer edge;
  * the abstract in the other language and the title page in the other language at the end.

The mermaid diagrams are rendered (wide ones on landscape pages) and also saved as PNG files
for the Word build; the PDF gets bookmarks, and Persian page numbers for --rtl.

    pip install markdown playwright pypdf                 # Google Chrome must be installed
    cd docs/tools && npm install                          # mermaid (for the diagrams)
    python docs/tools/build_report_pdf.py docs/REPORT.md docs/Guya-Report-EN.pdf --figdir out/mermaid-en
    python docs/tools/build_report_pdf.py docs/REPORT-FA.md docs/Guya-Report-FA.pdf --rtl --figdir out/mermaid-fa
"""

import io
import json
import os
import re
import sys

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, StreamObject
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_report_html import convert  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FONT_DIR = os.path.join(REPO, "guya", "assets", "fonts")
ASSETS = os.path.join(HERE, "assets")
EXTRA_FONT_DIR = os.path.join(ASSETS, "fonts")     # B Nazanin, B Titr (proprietary, not committed): see README
FA_TEXT = '"B Nazanin", "XB Zar", "Vazirmatn", Tahoma, sans-serif'
FA_HEAD = '"B Titr", "B Nazanin", "XB Zar", "Vazirmatn", sans-serif'
EN_TEXT = '"Times New Roman", Times, serif'
MERMAID_JS = os.path.join(HERE, "node_modules", "mermaid", "dist", "mermaid.min.js")
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
MM = 72 / 25.4
SHIFT = 2.5 * MM            # symmetric 22.5 mm side margins become 25 mm inside and 20 mm outside

STRINGS = {
    "en": {"contents": "Contents", "figures": "List of Figures", "tables": "List of Tables",
           "inst": ["University of Tehran", "Farabi Campus", "Faculty of Engineering", "Department of Computer Engineering"],
           "kind": "B.Sc. Final-Year Project Report in Computer Engineering", "date": "September 2026",
           "jury": "Evaluation Committee Minutes",
           "jury_note": "The signed minutes of the evaluation session are inserted here after the defence.",
           "abstract": "Abstract"},
    "fa": {"contents": "فهرست مطالب", "figures": "فهرست شکل‌ها", "tables": "فهرست جدول‌ها",
           "inst": ["دانشگاه تهران", "دانشکدگان فارابی", "دانشکدهٔ مهندسی", "گروه مهندسی کامپیوتر"],
           "kind": "گزارش پروژهٔ پایانی دورهٔ کارشناسی مهندسی کامپیوتر", "date": "شهریور ۱۴۰۵",
           "jury": "صورت‌جلسهٔ داوری",
           "jury_note": "صورت‌جلسهٔ امضاشدهٔ داوری پس از جلسهٔ داوری در این صفحه قرار می‌گیرد.",
           "abstract": "چکیده"},
}

CSS_TEMPLATE = """
@page { size: A4; margin: 35mm 22.5mm 20mm 22.5mm; }
@page wide { size: A4 landscape; margin: 20mm 22mm 20mm 22mm; }
* { box-sizing: border-box; }
html { font-size: 13pt; }
body { margin: 0; color: #111; background: #fff; font-family: EN_TEXT; line-height: 1.5; }
body.rtl { font-family: FA_TEXT; font-size: 14pt; line-height: 1.7; }
h1, h2, h3, .hd { font-family: EN_TEXT; font-weight: bold; }
body.rtl h1, body.rtl h2, body.rtl h3, body.rtl .hd { font-family: FA_HEAD; }
body.rtl h3 { font-family: FA_TEXT; font-weight: bold; }
/* the closing title page is in the other language: give it that language's faces (the B fonts draw Latin digits as Persian ones) */
body.rtl section.cover.end, body.rtl section.cover.end .hd, body.rtl section.cover.end h1 { font-family: EN_TEXT; }
body:not(.rtl) section.cover.end, body:not(.rtl) section.cover.end .hd { font-family: FA_TEXT; }
body:not(.rtl) section.cover.end h1, body:not(.rtl) section.cover.end .kind { font-family: FA_HEAD; }
body:not(.rtl) h2#abstract-end { font-family: FA_HEAD; }
body.rtl h2#abstract-end { font-family: EN_TEXT; }
body.rtl .lat { font-family: EN_TEXT; font-size: 12.5pt; }
body.rtl h2 .lat, body.rtl h3 .lat, body.rtl h1 .lat { font-family: EN_TEXT; font-size: 0.9em; }
body.rtl th .lat, body.rtl td .lat, body.rtl p.cap .lat, body.rtl .toc-entry .lat { font-size: 0.92em; }
h2 { break-before: page; break-after: avoid; font-size: 20pt; line-height: 1.35; margin: 12mm 0 16pt; padding-bottom: 6pt; border-bottom: 1.5pt solid #0f766e; }
h2.front-title { break-before: auto; }
h3 { break-after: avoid; font-size: 18pt; line-height: 1.35; margin: 20pt 0 8pt; }
p { margin: 0 0 9pt; text-align: justify; orphans: 2; widows: 2; }
strong { font-weight: 600; }
a { color: inherit; text-decoration: none; }
hr { display: none; }
ul, ol { margin: 0 0 9pt; padding-left: 1.5em; } body.rtl ul, body.rtl ol { padding-left: 0; padding-right: 1.5em; }
li { margin: 2pt 0; text-align: justify; }
code { font-family: "IBM Plex Mono", Menlo, Consolas, monospace; font-size: 0.86em; background: #f1f3f3; padding: 0 2pt; direction: ltr; unicode-bidi: embed; }
pre { font-family: "IBM Plex Mono", Menlo, Consolas, monospace; font-size: 9pt; line-height: 1.45; background: #f4f6f6; border: 0.5pt solid #d0d6d6; padding: 6pt 8pt; margin: 4pt 0 10pt; white-space: pre-wrap; word-break: break-all; direction: ltr; text-align: left; orphans: 4; widows: 4; }
pre code { background: none; padding: 0; font-size: inherit; }
pre.mermaid { background: #fff; border: 0; text-align: center; padding: 6pt 0; break-inside: avoid; }
pre.mermaid svg { max-width: 100%; height: auto; max-height: 185mm; }
pre.mermaid .nodeLabel, pre.mermaid .label foreignObject div, pre.mermaid .edgeLabel { white-space: normal !important; overflow-wrap: normal !important; word-break: keep-all !important; max-width: 210px !important; }
.wide { page: wide; }
pre.mermaid.wide { break-before: page; break-after: avoid; margin: 0; }
pre.mermaid.wide svg { max-height: 150mm; }
.tw { margin: 6pt 0 2pt; }
thead { display: table-header-group; }          /* long tables split across pages with the header row repeated */
tr { break-inside: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 10.5pt; line-height: 1.35; }
body.rtl table { font-size: 12.5pt; line-height: 1.5; }
th, td { border: 0.5pt solid #b9c2c2; padding: 3pt 5pt; vertical-align: top; text-align: left; }
body.rtl th, body.rtl td { text-align: right; }
th { background: #e8f1f0; font-weight: bold; font-size: 10pt; }
body.rtl th { font-size: 12.5pt; }
td[align=right], th[align=right] { text-align: right; }
p.cap { font-size: 11pt; color: #222; text-align: center; margin: 4pt 0 14pt; break-before: avoid; }
body.rtl p.cap { font-size: 12.5pt; }
figure { margin: 8pt 0 4pt; text-align: center; break-inside: avoid; }
.figrow { display: flex; gap: 6mm; justify-content: center; align-items: flex-start; break-inside: avoid; margin: 8pt 0 4pt; }
.figrow figure { flex: 0 1 47%; margin: 0; }
.figrow figure img { width: 100%; height: auto; max-height: 130mm; object-fit: contain; }
p.kw { margin-top: 2pt; }
figure img { max-width: 100%; max-height: 160mm; height: auto; }
figcaption { display: none; }
p.fa { direction: rtl; font-family: FA_TEXT; font-size: 14pt; line-height: 1.7; text-align: justify; }
p.en { direction: ltr; font-family: EN_TEXT; font-size: 13pt; line-height: 1.5; text-align: justify; }
body.rtl h2#abstract-end { direction: ltr; text-align: left; }
body:not(.rtl) h2#abstract-end { direction: rtl; text-align: right; }
ol.refs, body.rtl ol.refs { direction: ltr; text-align: left; font-family: EN_TEXT; font-size: 12pt; line-height: 1.4; padding-left: 1.5em; padding-right: 0; list-style: decimal outside; }
h2, h3, p.cap, section.fp, section.cover { position: relative; }
.pm { position: absolute; left: 0; top: 0; font-size: 1pt; color: #fff; direction: ltr; unicode-bidi: isolate; }
.blank { break-before: page; height: 1pt; }
section.fp { break-before: page; }
section.cover { display: flex; flex-direction: column; align-items: center; text-align: center; height: 238mm; }
.cover .logo { width: 30mm; height: auto; margin-bottom: 3mm; }
.cover .inst { font-size: 13pt; line-height: 1.65; font-weight: 500; }
.cover .kind { font-size: 13.5pt; color: #0f766e; font-weight: 600; margin-top: 16mm; }
.cover h1 { font-size: 22pt; line-height: 1.5; margin: 10mm 2mm 0; font-weight: 700; }
.cover .meta { font-size: 13pt; line-height: 2; margin-top: auto; }
.cover .meta b { font-weight: 600; margin: 0 4pt; }
.cover .date { font-size: 13pt; margin-top: 8mm; }
section.bismillah { height: 242mm; display: flex; align-items: center; justify-content: center; }
.bismillah img { width: 62mm; height: auto; }
.jury .t { font-size: 20pt; font-weight: 700; text-align: center; margin-top: 30mm; }
.jury .note { text-align: center; color: #555; font-size: 12pt; margin-top: 8mm; }
section.front { break-before: page; }
section.abstract h2 { margin-top: 4mm; }
section.abstract p { font-size: 14pt; line-height: 1.6; }
body:not(.rtl) section.abstract p { font-size: 12.5pt; line-height: 1.45; }
.toc-entry { display: flex; align-items: baseline; font-size: 12pt; margin: 2pt 0; break-inside: avoid; }
body.rtl .toc-entry { font-size: 14pt; }
.toc-entry.l2 { font-weight: 600; margin-top: 7pt; }
.toc-entry.l3 { padding-left: 16pt; font-size: 11pt; font-weight: normal; } body.rtl .toc-entry.l3 { font-size: 13pt; } body.rtl .toc-entry.l3 { padding-left: 0; padding-right: 16pt; }
.toc-entry .t { flex: 0 1 auto; }
.toc-entry .dots { flex: 1 1 auto; border-bottom: 1px dotted #999; margin: 0 4pt; min-width: 10pt; transform: translateY(-3pt); }
.toc-entry .n { flex: 0 0 auto; font-variant-numeric: tabular-nums; }
.lof .toc-entry { font-size: 11pt; margin: 3pt 0; } body.rtl .lof .toc-entry { font-size: 13pt; }
"""

OVERLAY_CSS_TEMPLATE = """
@page { size: A4; margin: 0; }
@page land { size: A4 landscape; margin: 0; }
html, body { margin: 0; padding: 0; }
body { font-family: EN_TEXT; color: #111; }
body.rtl { font-family: FA_TEXT; }
.pg { position: relative; width: 210mm; height: 296mm; overflow: hidden; break-after: page; }
.pg.land { page: land; width: 297mm; height: 209mm; }
.pg:last-child { break-after: auto; }
.hdr { position: absolute; top: 0; height: 25mm; border-bottom: 0.6pt solid #000; }
.hdr span { position: absolute; bottom: 1.6mm; font-size: 11pt; white-space: nowrap; max-width: 130mm; overflow: hidden; text-overflow: ellipsis; }
.hdr .l { left: 0; } .hdr .r { right: 0; }
.bn { position: absolute; left: 0; right: 0; bottom: 12mm; text-align: center; font-size: 12pt; }
"""

def _css(t):
    return t.replace("FA_TEXT", FA_TEXT).replace("FA_HEAD", FA_HEAD).replace("EN_TEXT", EN_TEXT)


CSS = _css(CSS_TEMPLATE)
OVERLAY_CSS = _css(OVERLAY_CSS_TEMPLATE)

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400'
         '&family=IBM+Plex+Mono:wght@400;500&display=swap">')


def font_faces():
    faces = []
    if os.path.isdir(EXTRA_FONT_DIR):
        for fn in sorted(os.listdir(EXTRA_FONT_DIR)):
            low = fn.lower()
            if not low.endswith((".ttf", ".otf")):
                continue
            # Borna's file names: BNazanin.ttf, BNaznnBd.ttf (bold), BTitrBd.ttf
            family = "B Titr" if "titr" in low else "B Nazanin" if low.startswith("bnaz") or "nazanin" in low else "XB Zar" if "zar" in low else None
            if family is None or "outline" in low or low.startswith("bnazanno"):
                continue
            weight = "bold" if ("bold" in low or "bd." in low or family == "B Titr") else "normal"
            faces.append(f'@font-face {{ font-family: "{family}"; font-weight: {weight}; src: url("file://{os.path.join(EXTRA_FONT_DIR, fn)}"); }}')
    for weight, name in ((400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")):
        path = os.path.join(FONT_DIR, f"Vazirmatn-{name}.ttf")
        if os.path.exists(path):
            faces.append(f'@font-face {{ font-family: "Vazirmatn"; font-weight: {weight}; src: url("file://{path}") format("truetype"); }}')
    return "\n".join(faces)


def split_front(body):
    """Take the H1, the subtitle line and the metadata table off the body; return (title, subtitle, rows, body)."""
    m = re.search(r"<h1[^>]*>(.*?)</h1>\s*", body, re.S)
    title = re.sub(r"<[^>]+>", "", m.group(1)); body = body[:m.start()] + body[m.end():]
    m = re.match(r"\s*<p><strong>(.*?)</strong></p>\s*", body, re.S)
    subtitle = re.sub(r"<[^>]+>", "", m.group(1)); body = body[m.end():]
    m = re.match(r'\s*<div class="tw"><table>(.*?)</table></div>\s*', body, re.S)
    rows = [[re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)] for r in re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S)]
    rows = [r for r in rows if len(r) == 2 and r[0].strip()]
    body = body[m.end():]
    body = re.sub(r"^\s*<hr\s*/?>\s*", "", body)
    return title, subtitle, rows, body


class Marks:
    """Invisible letter markers (digits would merge with Persian digits in the extracted text)."""

    def __init__(self):
        self.n = 0

    def next(self):
        self.n += 1
        n, letters = self.n, ""
        for _ in range(4):
            n, r = divmod(n, 26); letters = chr(65 + r) + letters
        return "GYM" + letters


def odd_start(level, text):
    """Headings that must open an odd page: chapters, references, the first appendix, the abstracts."""
    return level == 2 and (re.match(r"^[0-9۰-۹]", text) is not None
                           or text in ("References", "مراجع", "Abstract", "چکیده")
                           or text.startswith(("Appendix A", "پیوست الف")))


def mark(body, marks):
    """Put a marker at the start of every h2, h3 and caption; return (body, headings, captions)."""
    headings, captions = [], []

    def head(m):
        k = marks.next(); level = int(m.group(1)); text = re.sub(r"<[^>]+>", "", m.group(3))
        headings.append((level, m.group(2), text, k))
        odd = f' data-odd="{k}"' if odd_start(level, text) else ""
        return f'<h{level} id="{m.group(2)}"{odd}><span class="pm">{k}</span>{m.group(3)}</h{level}>'

    def cap(m):
        k = marks.next(); text = re.sub(r"<[^>]+>", "", m.group(1))
        captions.append((text, k))
        return f'<p class="cap"><span class="pm">{k}</span>{m.group(1)}</p>'

    body = re.sub(r'<h([23]) id="([^"]+)">(.*?)</h\1>', head, body, flags=re.S)
    body = re.sub(r'<p class="cap">(.*?)</p>', cap, body, flags=re.S)
    return body, headings, captions


def caption_entry(text):
    m = re.match(r"^(Table|Figure|جدول|شکل)\s+(\S+?)\.\s+(.*)$", text, re.S)
    if not m:
        return None, text
    kind, num, desc = m.group(1), m.group(2), m.group(3).strip()
    first = re.split(r"(?<=[^0-9])\.\s", desc, 1)[0].rstrip(".") + "."
    return ("table" if kind in ("Table", "جدول") else "figure"), f"{kind} {num}. {first}"


def print_variant(m):
    """Narrower layouts for paper: the wide-screen web layouts do not fit a page."""
    inner = m.group(1)
    if "subgraph L1" in inner:                          # architecture: infrastructure as two columns
        inner = inner.rstrip() + "\n    CFG ~~~ LOG\n    RT ~~~ BENCH\n    LOG ~~~ LAUNCH\n"
    if inner.lstrip().startswith("flowchart LR"):     # process and pipeline diagrams: top to bottom
        inner = inner.replace("flowchart LR", "flowchart TB", 1)
    if "stateDiagram-v2" in inner and "AwaitYesNo" in inner:
        inner = inner.replace("stateDiagram-v2\n", "stateDiagram-v2\n    direction LR\n", 1)
    return '<pre class="mermaid">' + inner + "</pre>"


LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9._+/\\-]*(?:\s[A-Za-z0-9._+/\\-]+)*")
PROTECTED = re.compile(r"<(pre|code|script|style)\b.*?</\1>|<span class=\"pm\">[^<]*</span>|&[A-Za-z#0-9]+;", re.S)


def wrap_latin(html):
    """Wrap Latin words in the Persian text in <span class=\"lat\"> so they take the Latin face."""
    out, pos = [], 0
    for m in PROTECTED.finditer(html):                 # code, markers and entities stay untouched
        out.append(_wrap_text(html[pos:m.start()])); out.append(m.group(0)); pos = m.end()
    out.append(_wrap_text(html[pos:]))
    return "".join(out)


# B Nazanin has no combining hamza, Arabic decimal/thousands separators or Arabic percent sign;
# Chrome would take those from the fallback font (and, in a heading pushed to the next page, has
# been seen to paint the fallback cluster on the wrong page). Use the glyphs the font does have:
# the precomposed ۀ, the classic slash decimal, the comma thousands separator and ASCII %.
FA_SUBS = (("\u0647\u0654", "\u06c0"), ("\u066b", "/"), ("\u066a", "%"), ("\u066c", "\u060c"), ("\u2026", "..."))


def normalize_fa(html):
    """Apply FA_SUBS to the text nodes of the page (code, markers and entities untouched)."""
    out, pos = [], 0
    for m in PROTECTED.finditer(html):
        out.append(_sub_text(html[pos:m.start()])); out.append(m.group(0)); pos = m.end()
    out.append(_sub_text(html[pos:]))
    return "".join(out)


def _sub_text(html):
    parts = re.split(r"(<[^>]+>)", html)
    for i in range(0, len(parts), 2):
        for a, b in FA_SUBS:
            parts[i] = parts[i].replace(a, b)
    return "".join(parts)


def _wrap_text(html):
    parts = re.split(r"(<[^>]+>)", html)
    for i in range(0, len(parts), 2):                  # even indexes are text nodes
        if parts[i].strip():
            parts[i] = LATIN_RUN.sub(lambda m: f'<span class="lat">{m.group(0)}</span>', parts[i])
    return "".join(parts)


def cover_page(cls, S, title, rows, direction, k):
    meta = "".join(f"<div><b>{a}</b> {b}</div>" for a, b in rows
                   if not a.startswith(("Code", "کد", "Institution", "دانشگاه")))
    return (f'<section class="cover {cls}" dir="{direction}" data-odd="{k}"><span class="pm">{k}</span>'
            f'<img class="logo" src="file://{ASSETS}/ut-logo.png" alt="">'
            f'<div class="inst hd">{"<br>".join(S["inst"])}</div><div class="kind hd">{S["kind"]}</div>'
            f'<h1>{title}</h1><div class="meta hd">{meta}</div><div class="date hd">{S["date"]}</div></section>')


def build_html(md_path, rtl):
    lang, other = ("fa", "en") if rtl else ("en", "fa")
    S, O = STRINGS[lang], STRINGS[other]
    body, _, _ = convert(md_path, rtl)
    title, subtitle, rows, body = split_front(body)
    other_md = os.path.join(os.path.dirname(os.path.abspath(md_path)), "REPORT.md" if rtl else "REPORT-FA.md")
    obody, _, _ = convert(other_md, not rtl)
    otitle, _, orows, _ = split_front(obody)

    # the abstract moves in front of the contents; its other-language paragraph closes the report
    m = re.search(r'<h2 id="([^"]+)">(چکیده|Abstract)</h2>(.*?)(?=<h2 )', body, re.S)
    abstract = m.group(3); body = body[:m.start()] + body[m.end():]
    f = re.search(r'(?:<p class="(?:en|fa)[^"]*"[^>]*>.*?</p>\s*)+', abstract, re.S)
    foreign = re.sub(r"^(<p[^>]*>)(Abstract|چکیده):\s*", r"\1", f.group(0)); abstract = abstract[:f.start()] + abstract[f.end():]
    front_abstract = f'<section class="abstract"><h2 id="{m.group(1)}">{m.group(2)}</h2>{abstract}</section>'
    end_abstract = f'<h2 id="abstract-end">{O["abstract"]}</h2>{foreign}'

    marks = Marks()
    marked, headings, captions = mark(front_abstract + "<!--SPLIT-->" + body + end_abstract, marks)
    front_abstract, body = marked.split("<!--SPLIT-->")
    body = re.sub(r'<pre class="mermaid">(.*?)</pre>', print_variant, body, flags=re.S)
    if rtl:
        body = wrap_latin(body); front_abstract = wrap_latin(front_abstract)
    keys = {name: marks.next() for name in ("title", "bismillah", "jury", "contents", "figures", "tables", "end_title")}

    title_page = cover_page("", S, title, rows, "rtl" if rtl else "ltr", keys["title"])
    end_title = cover_page("end fp", O, otitle, orows, "ltr" if rtl else "rtl", keys["end_title"])
    bism = (f'<section class="fp bismillah" data-odd="{keys["bismillah"]}"><span class="pm">{keys["bismillah"]}</span>'
            f'<img src="file://{ASSETS}/bismillah.png" alt=""></section>')
    jury = (f'<section class="fp jury" data-odd="{keys["jury"]}"><span class="pm">{keys["jury"]}</span>'
            f'<div class="t hd">{S["jury"]}</div><div class="note">{S["jury_note"]}</div></section>')

    def entry(level, target, text, k):
        return (f'<div class="toc-entry l{level}" data-pm="{k}"><a href="#{target}"><span class="t">{text}</span></a>'
                f'<span class="dots"></span><span class="n">000</span></div>')

    toc = (f'<section class="front" data-odd="{keys["contents"]}"><h2 class="front-title"><span class="pm">{keys["contents"]}</span>{S["contents"]}</h2>'
           + "".join(entry(lvl, tid, text, k) for lvl, tid, text, k in headings) + "</section>")
    figs, tabs = [], []
    for text, k in captions:
        kind, short = caption_entry(text)
        (tabs if kind == "table" else figs).append(entry(3, "", short, k).replace('class="toc-entry l3"', 'class="toc-entry"'))
    lists = (f'<section class="front lof"><h2 class="front-title"><span class="pm">{keys["figures"]}</span>{S["figures"]}</h2>{"".join(figs)}'
             f'<h2 class="front-title" style="margin-top:18pt"><span class="pm">{keys["tables"]}</span>{S["tables"]}</h2>{"".join(tabs)}</section>')

    mermaid = (f'<script src="file://{MERMAID_JS}"></script><script>window.__ready = false;'
               f'mermaid.initialize({{startOnLoad: false, theme: "neutral", fontFamily: "Vazirmatn, Helvetica Neue, Arial, sans-serif", fontSize: 13}});'
               f'Promise.all(["13px Vazirmatn", "bold 13px Vazirmatn", "500 13px Vazirmatn", "600 13px Vazirmatn"].map(f => document.fonts.load(f))).then(() => mermaid.run({{querySelector: "pre.mermaid"}})).then(() => {{ window.__ready = true; }});</script>')
    page = (f'<!doctype html><html lang="{lang}" dir="{"rtl" if rtl else "ltr"}"><head><meta charset="utf-8"><title>{title}</title>'
            f"{FONTS}<style>{font_faces()}{CSS}</style></head><body class=\"{'rtl' if rtl else ''}\">"
            f"{title_page}{bism}{jury}{front_abstract}{toc}{lists}<main>{body}</main>{end_title}{mermaid}</body></html>")
    if rtl:
        page = normalize_fa(page)

    odd_body = [k for lvl, _, text, k in headings if odd_start(lvl, text)]      # abstract first, other abstract last
    odd_keys = [keys["title"], keys["bismillah"], keys["jury"], odd_body[0], keys["contents"]] + odd_body[1:] + [keys["end_title"]]
    order = ([(2, headings[0][2], headings[0][3]), (2, S["contents"], keys["contents"]),
              (2, S["figures"], keys["figures"]), (3, S["tables"], keys["tables"])]
             + [(lvl, text, k) for lvl, _, text, k in headings[1:]])          # reading order, for the running headers
    return page, title, headings, captions, keys, odd_keys, order


def marker_pages(pdf_bytes):
    found = {}
    for i, pg in enumerate(PdfReader(io.BytesIO(pdf_bytes)).pages, start=1):
        for m in re.finditer(r"GYM([A-Z]{4})", pg.extract_text() or ""):
            found.setdefault("GYM" + m.group(1), i)
    return found


def plan_blanks(mapping, odd_keys, current):
    """Which odd-start elements need a blank page before them, given where they land now."""
    blanks, offset, seen = [], 0, 0
    for k in odd_keys:
        if k in current:
            seen += 1                             # a blank already in the document before (or at) this element
        p = mapping.get(k)
        if p is None:
            continue
        if (p - seen + offset) % 2 == 0:
            blanks.append(k); offset += 1
    return blanks


def page_plan(sizes, mapping, order, keys, blank_pages):
    """Per page: none | number | header, plus the chapter and section titles current on it."""
    first_numbered = mapping[keys["contents"]]
    end_title = mapping[keys["end_title"]]
    starts = {mapping[k] for lvl, _, k in order if lvl == 2 and k in mapping}
    plan = []
    for i, (w, h) in enumerate(sizes, start=1):
        land = w > h
        if i < first_numbered or i >= end_title or i in blank_pages:
            kind = "none"
        elif i in starts or land:
            kind = "number"
        else:
            kind = "header"
        chap = sec = None
        for lvl, text, k in order:
            p = mapping.get(k)
            if p is None or p > i:
                continue
            if lvl == 2:
                chap, sec = text, None
            else:
                sec = text
        plan.append({"kind": kind, "land": land, "chapter": chap or "", "section": sec or chap or ""})
    return plan


def overlay_html(plan, rtl):
    pages = []
    for i, pg in enumerate(plan, start=1):
        num = str(i).translate(FA_DIGITS) if rtl else str(i)
        inner = ""
        if pg["kind"] == "number":
            inner = f'<div class="bn">{num}</div>'
        elif pg["kind"] == "header":
            odd = i % 2 == 1
            inner_right = (odd and rtl) or (not odd and not rtl)      # the binding edge of this page
            left, right = ("20mm", "25mm") if inner_right else ("25mm", "20mm")
            text = pg["section"] if odd else pg["chapter"]           # odd pages: section title; even: chapter title
            l, r = (num, text) if inner_right else (text, num)         # the number sits on the outer edge
            d = "rtl" if rtl else "ltr"
            inner = (f'<div class="hdr" style="left:{left};right:{right}">'
                     f'<span class="l" dir="{d}">{l}</span><span class="r" dir="{d}">{r}</span></div>')
        pages.append(f'<div class="pg{" land" if pg["land"] else ""}">{inner}</div>')
    html = (f'<!doctype html><html><head><meta charset="utf-8"><style>{font_faces()}{OVERLAY_CSS}</style></head>'
            f'<body class="{"rtl" if rtl else ""}">{"".join(pages)}</body></html>')
    return normalize_fa(html) if rtl else html


def form_xobject(writer, src):
    """Turn an overlay page into a form XObject registered in the writer."""
    cont = src.raw_get("/Contents")
    parts = list(cont) if isinstance(cont, ArrayObject) else [cont]
    data = b"\n".join(p.get_object().get_data() for p in parts)
    x = StreamObject(); x.set_data(data); x = x.flate_encode()
    x[NameObject("/Type")] = NameObject("/XObject"); x[NameObject("/Subtype")] = NameObject("/Form")
    x[NameObject("/BBox")] = ArrayObject([FloatObject(0), FloatObject(0), FloatObject(src.mediabox.width), FloatObject(src.mediabox.height)])
    res = src["/Resources"].clone(writer)
    x[NameObject("/Resources")] = res.indirect_reference if getattr(res, "indirect_reference", None) else res
    return writer._add_object(x)


def stamp(pdf_bytes, overlay_bytes, rtl, title, author, headings, mapping, plan):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter(clone_from=reader)
    overlay = PdfReader(io.BytesIO(overlay_bytes))
    if len(overlay.pages) != len(writer.pages):
        raise SystemExit(f"overlay has {len(overlay.pages)} pages, the report {len(writer.pages)}")
    for i, page in enumerate(writer.pages, start=1):
        info = plan[i - 1]
        dx = 0.0
        if not info["land"]:
            recto = i % 2 == 1
            inner_right = (recto and rtl) or (not recto and not rtl)
            dx = -SHIFT if inner_right else SHIFT                      # move the text block towards the outer edge
        xobjects = page["/Resources"].get("/XObject")
        if xobjects is None:
            xobjects = DictionaryObject(); page["/Resources"][NameObject("/XObject")] = xobjects
        name = f"/GYOv{i}"
        xobjects[NameObject(name)] = form_xobject(writer, overlay.pages[i - 1])
        contents = page.raw_get("/Contents")
        originals = list(contents) if isinstance(contents, ArrayObject) else [contents]
        head = StreamObject(); head.set_data(f"q 1 0 0 1 {dx:.3f} 0 cm\n".encode())
        tail = StreamObject(); tail.set_data(f"\nQ\nq {name} Do Q\n".encode())
        page[NameObject("/Contents")] = ArrayObject([writer._add_object(head)] + originals + [writer._add_object(tail)])
        if dx and "/Annots" in page:
            for a in page["/Annots"]:
                a = a.get_object()
                if "/Rect" in a:
                    r = a["/Rect"]
                    a[NameObject("/Rect")] = ArrayObject([FloatObject(float(r[0]) + dx), r[1], FloatObject(float(r[2]) + dx), r[3]])
    parent = None
    for level, _, text, k in headings:          # bookmarks: chapters, with their sections nested
        if k not in mapping:
            continue
        item = writer.add_outline_item(text, mapping[k] - 1, parent=parent if level == 3 else None)
        if level == 2:
            parent = item
    writer.add_metadata({"/Title": title, "/Author": author, "/Creator": "Guya report build (Chrome + pypdf)",
                         "/Subject": "B.Sc. final-year project report, University of Tehran, Farabi Campus"})
    out = io.BytesIO(); writer.write(out)
    return out.getvalue()


def build(md_path, out_path, rtl=False, figdir=None, author="MohammadReza Ganji", print_layout=False):
    html, title, headings, captions, keys, odd_keys, order = build_html(md_path, rtl)
    html_path = os.path.abspath(out_path) + ".print.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(device_scale_factor=2, viewport={"width": 2400, "height": 1400})
        page.goto("file://" + html_path, wait_until="networkidle")
        page.wait_for_function("window.__ready === true", timeout=120_000)
        page.wait_for_function("document.fonts.status === 'loaded'", timeout=60_000)
        wide = page.evaluate("""() => { const wide = []; document.querySelectorAll('pre.mermaid').forEach((pre, i) => {
            const svg = pre.querySelector('svg'); const w = svg ? svg.viewBox.baseVal.width : 0;
            if (w > 900) { pre.classList.add('wide'); const n = pre.nextElementSibling; if (n && n.matches('p.cap')) n.classList.add('wide'); wide.push(i); } });
            return wide; }""")
        if figdir:
            os.makedirs(figdir, exist_ok=True)
            # screenshots at the diagram's own size (the print CSS scales the SVGs to the page)
            page.evaluate("() => document.querySelectorAll('pre.mermaid svg').forEach(s => { const v = s.viewBox.baseVal; s.style.cssText += `;width:${v.width}px;height:${v.height}px;max-width:none;max-height:none`; })")
            for i, el in enumerate(page.query_selector_all("pre.mermaid svg")):
                el.screenshot(path=os.path.join(figdir, f"fig-{i}.png"))
            page.evaluate("() => document.querySelectorAll('pre.mermaid svg').forEach(s => { s.style.width = ''; s.style.height = ''; s.style.maxWidth = ''; s.style.maxHeight = ''; })")
            with open(os.path.join(figdir, "wide.json"), "w") as f:
                json.dump(wide, f)
        pdf_opts = dict(format="A4", print_background=True, prefer_css_page_size=True, outline=True,
                        display_header_footer=False)
        pdf = page.pdf(**pdf_opts)
        mapping = marker_pages(pdf)
        if not print_layout:               # screen copy: no blank pages, chapters just start on a new page
            odd_keys = []
        blanks = plan_blanks(mapping, odd_keys, set())
        for _ in range(6):
            shown = {k: (str(v).translate(FA_DIGITS) if rtl else str(v)) for k, v in mapping.items()}
            page.evaluate("(m) => { for (const [k, v] of Object.entries(m)) { const el = document.querySelector(`[data-pm='${k}'] .n`); if (el) el.textContent = v; } }", shown)
            page.evaluate("""(blanks) => { document.querySelectorAll('.blank').forEach(b => b.remove());
                for (const k of blanks) { const el = document.querySelector(`[data-odd='${k}']`);
                    if (el) { const d = document.createElement('div'); d.className = 'blank'; el.parentNode.insertBefore(d, el); } } }""", blanks)
            pdf = page.pdf(**pdf_opts)
            new = marker_pages(pdf)
            new_blanks = plan_blanks(new, odd_keys, set(blanks))
            if new == mapping and new_blanks == blanks:
                break
            mapping, blanks = new, new_blanks
        sizes = [(float(pg.mediabox.width), float(pg.mediabox.height)) for pg in PdfReader(io.BytesIO(pdf)).pages]
        blank_pages = {mapping[k] - 1 for k in blanks if k in mapping}
        plan = page_plan(sizes, mapping, order, keys, blank_pages)
        ov_path = os.path.abspath(out_path) + ".overlay.html"
        with open(ov_path, "w", encoding="utf-8") as f:
            f.write(overlay_html(plan, rtl))
        ov_page = browser.new_page()
        ov_page.goto("file://" + ov_path, wait_until="load")
        ov_page.wait_for_function("document.fonts.status === 'loaded'", timeout=60_000)
        overlay = ov_page.pdf(format="A4", prefer_css_page_size=True, print_background=False, display_header_footer=False)
        browser.close()
    missing = [k for _, _, _, k in headings if k not in mapping] + [k for _, k in captions if k not in mapping]
    raw_size = len(pdf)
    final = stamp(pdf, overlay, rtl, title, author, headings, mapping, plan)
    with open(out_path, "wb") as f:
        f.write(final)
    os.remove(html_path); os.remove(ov_path)
    n_pages = len(PdfReader(io.BytesIO(final)).pages)
    print(f"  chrome output {raw_size/1e6:.1f} MB, final {len(final)/1e6:.1f} MB; {len(blank_pages)} blank pages inserted before "
          + ", ".join(str(mapping[k]) for k in blanks if k in mapping))
    return n_pages, len(headings), len(captions), missing


if __name__ == "__main__":
    argv = sys.argv[1:]
    figdir = None
    if "--figdir" in argv:
        i = argv.index("--figdir"); figdir = argv[i + 1]; del argv[i:i + 2]
    rtl = "--rtl" in argv
    args = [a for a in argv if not a.startswith("--")]
    pages, nh, nc, missing = build(args[0], args[1], rtl=rtl, figdir=figdir, print_layout="--print" in argv)
    print(f"wrote {args[1]}: {pages} pages, {nh} headings and {nc} captions in the front lists"
          + (f"; NOT LOCATED: {missing}" if missing else ""))
