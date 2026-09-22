"""
Print docs/REPORT.md (or docs/REPORT-FA.md) to a PDF with Chrome, driven by Playwright:
a cover page, a table of contents and lists of figures and tables with page numbers
(filled in by a second print pass), every chapter on a new page, the mermaid diagrams
rendered, PDF bookmarks, and page numbers stamped on every page but the cover
(Persian digits for --rtl). The diagrams are also saved as PNG files for the Word build.

    pip install markdown playwright pypdf reportlab      # Google Chrome must be installed
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
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, StreamObject
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_report_html import convert  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FONT_DIR = os.path.join(REPO, "guya", "assets", "fonts")
MERMAID_JS = os.path.join(HERE, "node_modules", "mermaid", "dist", "mermaid.min.js")
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

STRINGS = {
    "en": {"contents": "Contents", "figures": "List of Figures", "tables": "List of Tables",
           "institution": "University of Tehran · Farabi Campus · Faculty of Engineering",
           "kind": "B.Sc. Final-Year Project Report in Computer Engineering", "date": "September 2026"},
    "fa": {"contents": "فهرست مطالب", "figures": "فهرست شکل‌ها", "tables": "فهرست جدول‌ها",
           "institution": "دانشگاه تهران · دانشکدگان فارابی · دانشکدهٔ مهندسی",
           "kind": "گزارش پروژهٔ پایانی دورهٔ کارشناسی مهندسی کامپیوتر", "date": "شهریور ۱۴۰۵"},
}

CSS = """
@page { size: A4; margin: 22mm 20mm 24mm 20mm; }
* { box-sizing: border-box; }
html { font-size: 11pt; }
body { margin: 0; color: #111; background: #fff; font-family: "Source Serif 4", Georgia, "Times New Roman", serif; line-height: 1.5; }
body.rtl { font-family: "Vazirmatn", Tahoma, sans-serif; font-size: 11.5pt; line-height: 1.85; }
h1, h2, h3, .hd { font-family: "Vazirmatn", "Helvetica Neue", Arial, sans-serif; }
h2 { break-before: page; break-after: avoid; font-size: 20pt; line-height: 1.3; margin: 0 0 14pt; padding-bottom: 6pt; border-bottom: 1.5pt solid #0f766e; }
h2.front-title { break-before: auto; }
h3 { break-after: avoid; font-size: 13.5pt; margin: 18pt 0 6pt; }
p { margin: 0 0 8pt; text-align: justify; orphans: 2; widows: 2; }
strong { font-weight: 600; }
a { color: inherit; text-decoration: none; }
hr { display: none; }
ul, ol { margin: 0 0 8pt; padding-left: 1.5em; } body.rtl ul, body.rtl ol { padding-left: 0; padding-right: 1.5em; }
li { margin: 2pt 0; text-align: justify; }
code { font-family: "IBM Plex Mono", Menlo, Consolas, monospace; font-size: 0.86em; background: #f1f3f3; padding: 0 2pt; direction: ltr; unicode-bidi: embed; }
pre { font-family: "IBM Plex Mono", Menlo, Consolas, monospace; font-size: 8.5pt; line-height: 1.45; background: #f4f6f6; border: 0.5pt solid #d0d6d6; padding: 6pt 8pt; margin: 4pt 0 10pt; white-space: pre-wrap; word-break: break-all; direction: ltr; text-align: left; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
pre.mermaid { background: #fff; border: 0; text-align: center; padding: 6pt 0; break-inside: avoid; }
pre.mermaid svg { max-width: 100%; height: auto; max-height: 190mm; }
pre.mermaid .nodeLabel, pre.mermaid .label foreignObject div, pre.mermaid .edgeLabel { white-space: normal !important; overflow-wrap: normal !important; word-break: keep-all !important; max-width: 210px !important; }
@page wide { size: A4 landscape; margin: 20mm 22mm 24mm 22mm; }
.wide { page: wide; }
pre.mermaid.wide { break-before: page; break-after: avoid; margin: 0; }
pre.mermaid.wide svg { max-height: 150mm; }
.tw { margin: 6pt 0 2pt; break-inside: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; line-height: 1.35; }
body.rtl table { font-size: 9.5pt; line-height: 1.6; }
th, td { border: 0.5pt solid #b9c2c2; padding: 3pt 5pt; vertical-align: top; text-align: left; }
body.rtl th, body.rtl td { text-align: right; }
th { background: #e8f1f0; font-family: "Vazirmatn", "Helvetica Neue", Arial, sans-serif; font-weight: 600; font-size: 8.5pt; }
thead { display: table-header-group; } tr { break-inside: avoid; }
td[align=right], th[align=right] { text-align: right; font-variant-numeric: tabular-nums; }
p.cap { font-family: "Vazirmatn", "Helvetica Neue", Arial, sans-serif; font-size: 9.5pt; color: #333; text-align: center; margin: 4pt 0 14pt; break-before: avoid; }
figure { margin: 8pt 0 4pt; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 180mm; }
figure.wide img { max-width: 100%; } figure.half img { max-width: 62%; } figure.tall img { max-height: 150mm; }
figcaption { display: none; }
p.fa { direction: rtl; font-family: "Vazirmatn", Tahoma, sans-serif; text-align: justify; line-height: 1.85; background: #f4f6f6; padding: 8pt 10pt; border-radius: 3pt; }
p.en { direction: ltr; font-family: "Source Serif 4", Georgia, serif; text-align: justify; line-height: 1.5; background: #f4f6f6; padding: 8pt 10pt; border-radius: 3pt; }
ol.refs { direction: ltr; text-align: left; font-family: "Source Serif 4", Georgia, serif; font-size: 10pt; line-height: 1.45; padding-left: 1.5em; padding-right: 0; }
ol.refs li { text-align: left; }
h2, h3, p.cap { position: relative; }
.pm { position: absolute; left: 0; top: 0; font-size: 1pt; color: #fff; direction: ltr; unicode-bidi: isolate; }
.cover { height: 236mm; display: flex; flex-direction: column; justify-content: space-between; align-items: center; text-align: center; break-after: page; }
.cover .inst { font-size: 11pt; color: #333; letter-spacing: .02em; }
.cover .kind { font-size: 12.5pt; color: #0f766e; font-weight: 600; margin-top: 10mm; }
.cover h1 { font-size: 23pt; line-height: 1.4; margin: 0 6mm; font-weight: 700; }
.cover .meta { font-size: 11.5pt; line-height: 1.9; }
.cover .meta b { font-weight: 600; color: #333; margin: 0 4pt; }
.cover .date { font-size: 11pt; color: #333; }
.front { break-after: page; }
.toc-entry { display: flex; align-items: baseline; font-family: "Vazirmatn", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; margin: 2pt 0; break-inside: avoid; }
.toc-entry.l2 { margin-top: 8pt; font-weight: 600; }
.toc-entry.l3 { padding-left: 16pt; font-size: 10pt; font-weight: 400; } body.rtl .toc-entry.l3 { padding-left: 0; padding-right: 16pt; }
.toc-entry .t { flex: 0 1 auto; }
.toc-entry .dots { flex: 1 1 auto; border-bottom: 1px dotted #999; margin: 0 4pt; min-width: 10pt; transform: translateY(-3pt); }
.toc-entry .n { flex: 0 0 auto; min-width: 2.6em; text-align: right; font-variant-numeric: tabular-nums; font-weight: 400; } body.rtl .toc-entry .n { text-align: left; }
.lof .toc-entry { font-size: 10pt; margin: 3pt 0; }
"""

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400'
         '&family=IBM+Plex+Mono:wght@400;500&display=swap">')


def font_faces():
    faces = []
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


def mark(body):
    """Put an invisible marker at the start of every h2, h3 and caption; return (body, headings, captions)."""
    counter = [0]; headings = []; captions = []

    def next_marker():
        counter[0] += 1
        n, letters = counter[0], ""
        for _ in range(4):                     # letters only: digits would merge with Persian digits in the bidi text
            n, r = divmod(n, 26); letters = chr(65 + r) + letters
        return "GYM" + letters

    def head(m):
        k = next_marker(); text = re.sub(r"<[^>]+>", "", m.group(3))
        headings.append((int(m.group(1)), m.group(2), text, k))
        return f'<h{m.group(1)} id="{m.group(2)}"><span class="pm">{k}</span>{m.group(3)}</h{m.group(1)}>'

    def cap(m):
        k = next_marker(); text = re.sub(r"<[^>]+>", "", m.group(1))
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


def build_html(md_path, rtl, figdir_note=None):
    lang = "fa" if rtl else "en"
    S = STRINGS[lang]
    body, items, _ = convert(md_path, rtl)
    title, subtitle, rows, body = split_front(body)
    body, headings, captions = mark(body)
    body = re.sub(r'<pre class="mermaid">(.*?)</pre>', print_variant, body, flags=re.S)

    meta = "".join(f"<div><b>{k}</b> {v}</div>" for k, v in rows if not k.startswith(("Code", "کد")))
    cover = (f'<section class="cover"><div class="inst hd">{S["institution"]}</div>'
             f'<div><div class="kind hd">{S["kind"]}</div></div><h1>{title}</h1>'
             f'<div class="meta hd">{meta}</div><div class="date hd">{S["date"]}</div></section>')

    def entry(level, target, text, k):
        return (f'<div class="toc-entry l{level}" data-pm="{k}"><a href="#{target}"><span class="t">{text}</span></a>'
                f'<span class="dots"></span><span class="n">000</span></div>')

    toc = f'<section class="front"><h2 class="front-title">{S["contents"]}</h2>' + "".join(
        entry(lvl, tid, text, k) for lvl, tid, text, k in headings) + "</section>"
    figs, tabs = [], []
    for text, k in captions:
        kind, short = caption_entry(text)
        (tabs if kind == "table" else figs).append(entry(3, "", short, k).replace('class="toc-entry l3"', 'class="toc-entry"'))
    lists = (f'<section class="front lof"><h2 class="front-title">{S["figures"]}</h2>{"".join(figs)}'
             f'<h2 class="front-title" style="margin-top:18pt">{S["tables"]}</h2>{"".join(tabs)}</section>')

    mermaid = (f'<script src="file://{MERMAID_JS}"></script><script>window.__ready = false;'
               f'mermaid.initialize({{startOnLoad: false, theme: "neutral", fontFamily: "Vazirmatn, Helvetica Neue, Arial, sans-serif", fontSize: 13}});'
               f'Promise.all(["13px Vazirmatn", "bold 13px Vazirmatn", "500 13px Vazirmatn", "600 13px Vazirmatn"].map(f => document.fonts.load(f))).then(() => mermaid.run({{querySelector: "pre.mermaid"}})).then(() => {{ window.__ready = true; }});</script>')
    page = (f'<!doctype html><html lang="{lang}" dir="{"rtl" if rtl else "ltr"}"><head><meta charset="utf-8"><title>{title}</title>'
            f"{FONTS}<style>{font_faces()}{CSS}</style></head><body class=\"{'rtl' if rtl else ''}\">"
            f"{cover}{toc}{lists}<main>{body}</main>{mermaid}</body></html>")
    return page, title, headings, captions


def marker_pages(pdf_bytes):
    found = {}
    for i, pg in enumerate(PdfReader(io.BytesIO(pdf_bytes)).pages, start=1):
        for m in re.finditer(r"GYM([A-Z]{4})", pg.extract_text() or ""):
            found.setdefault("GYM" + m.group(1), i)
    return found


def stamp(pdf_bytes, rtl, title, author, headings=(), mapping=None):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter(clone_from=reader)
    pdfmetrics.registerFont(TTFont("Vazirmatn", os.path.join(FONT_DIR, "Vazirmatn-Regular.ttf")))
    for i, page in enumerate(writer.pages, start=1):
        if i == 1:
            continue
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFont("Vazirmatn", 9.5); c.setFillColorRGB(0.2, 0.2, 0.2)
        label = str(i).translate(FA_DIGITS) if rtl else str(i)
        c.drawCentredString(w / 2, 13 * mm, label); c.save()
        overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
        # append the number as its own content stream, so Chrome's compressed streams stay untouched
        fonts = page["/Resources"].get("/Font")
        if fonts is None:
            fonts = DictionaryObject(); page["/Resources"][NameObject("/Font")] = fonts
        for name, ref in overlay["/Resources"]["/Font"].items():
            fonts[NameObject("/GYStamp")] = writer._add_object(ref.get_object().clone(writer))
            ops = overlay.get_contents().get_data().replace(name.encode(), b"/GYStamp")
        contents = page.raw_get("/Contents")
        originals = list(contents) if isinstance(contents, ArrayObject) else [contents]
        head = StreamObject(); head.set_data(b"q\n")
        tail = StreamObject(); tail.set_data(b"\nQ\nq\n" + ops + b"\nQ\n")
        page[NameObject("/Contents")] = ArrayObject([writer._add_object(head)] + originals + [writer._add_object(tail)])
    parent = None
    for level, _, text, k in headings:          # bookmarks: chapters, with their sections nested
        if mapping is None or k not in mapping:
            continue
        item = writer.add_outline_item(text, mapping[k] - 1, parent=parent if level == 3 else None)
        if level == 2:
            parent = item
    writer.add_metadata({"/Title": title, "/Author": author, "/Creator": "Guya report build (Chrome + pypdf)",
                         "/Subject": "B.Sc. final-year project report, University of Tehran, Farabi Campus"})
    out = io.BytesIO(); writer.write(out)
    return out.getvalue()


def build(md_path, out_path, rtl=False, figdir=None, author="MohammadReza Ganji"):
    html, title, headings, captions = build_html(md_path, rtl)
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
        for _ in range(4):
            shown = {k: (str(v).translate(FA_DIGITS) if rtl else str(v)) for k, v in mapping.items()}
            page.evaluate("(m) => { for (const [k, v] of Object.entries(m)) { const el = document.querySelector(`[data-pm='${k}'] .n`); if (el) el.textContent = v; } }", shown)
            pdf = page.pdf(**pdf_opts)
            new = marker_pages(pdf)
            if new == mapping:
                break
            mapping = new
        browser.close()
    missing = [k for _, _, _, k in headings if k not in mapping] + [k for _, k in captions if k not in mapping]
    raw_size = len(pdf)
    final = stamp(pdf, rtl, title, author, headings, mapping)
    with open(out_path, "wb") as f:
        f.write(final)
    os.remove(html_path)
    n_pages = len(PdfReader(io.BytesIO(final)).pages)
    print(f"  chrome output {raw_size/1e6:.1f} MB, final {len(final)/1e6:.1f} MB")
    return n_pages, len(headings), len(captions), missing


if __name__ == "__main__":
    argv = sys.argv[1:]
    figdir = None
    if "--figdir" in argv:
        i = argv.index("--figdir"); figdir = argv[i + 1]; del argv[i:i + 2]
    rtl = "--rtl" in argv
    args = [a for a in argv if not a.startswith("--")]
    pages, nh, nc, missing = build(args[0], args[1], rtl=rtl, figdir=figdir)
    print(f"wrote {args[1]}: {pages} pages, {nh} headings and {nc} captions in the front lists"
          + (f"; NOT LOCATED: {missing}" if missing else ""))
