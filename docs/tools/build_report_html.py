"""
Render docs/REPORT.md (or docs/REPORT-FA.md) to a single self-contained HTML
page: the project's Calm Teal palette, light and dark themes, screenshots
embedded, mermaid diagrams left as <pre class="mermaid"> blocks.

    pip install markdown            # the only dependency
    python docs/tools/build_report_html.py docs/REPORT.md out/guya-report.html
    python docs/tools/build_report_html.py docs/REPORT-FA.md out/guya-report-fa.html --rtl
"""

import base64
import os
import re
import sys

import markdown

CSS = """
:root {
  --bg:#f4f7f7; --card:#ffffff; --card2:#eaf0f0; --text:#111a1b; --text2:#3f5254; --dim:#6b7f81;
  --rule:#d5e0df; --accent:#0f766e; --accent2:#0d9488; --on-accent:#fff;
  --f-head:"Vazirmatn",ui-sans-serif,system-ui,sans-serif; --f-body:"Source Serif 4",Georgia,"Times New Roman",serif;
  --f-fa:"Vazirmatn",Tahoma,sans-serif; --f-mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#0c1014; --card:#141a1f; --card2:#1b2329; --text:#eef2f4; --text2:#b9c6c8; --dim:#8a9b9e;
  --rule:#283038; --accent:#2dd4bf; --accent2:#5eead4; --on-accent:#04211d; } }
:root[data-theme="dark"] {
  --bg:#0c1014; --card:#141a1f; --card2:#1b2329; --text:#eef2f4; --text2:#b9c6c8; --dim:#8a9b9e;
  --rule:#283038; --accent:#2dd4bf; --accent2:#5eead4; --on-accent:#04211d; }
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--f-body);font-size:17px;line-height:1.62;-webkit-font-smoothing:antialiased}
body.rtl{font-family:var(--f-fa);line-height:1.9;font-size:16.5px}
.shell{max-width:1180px;margin:0 auto;padding:40px 24px 96px;display:grid;grid-template-columns:230px minmax(0,1fr);gap:56px}
body.rtl .shell{grid-template-columns:minmax(0,1fr) 230px}
nav.rail{position:sticky;top:24px;align-self:start;font-family:var(--f-head);font-size:13px;line-height:1.45}
body.rtl nav.rail{order:2}
nav.rail .k{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin:0 0 10px}
nav.rail ul{list-style:none;margin:0;padding:0}
nav.rail a{display:block;padding:3px 0;color:var(--text2);text-decoration:none;border-left:2px solid transparent;padding-left:10px;margin-left:-12px}
body.rtl nav.rail a{border-left:0;border-right:2px solid transparent;padding-left:0;padding-right:10px;margin-left:0;margin-right:-12px}
nav.rail a:hover,nav.rail a:focus-visible{color:var(--accent);border-color:var(--accent);outline:none}
main{min-width:0;max-width:72ch}
h1{font-family:var(--f-head);font-size:2.05rem;line-height:1.25;font-weight:700;letter-spacing:-.01em;text-wrap:balance;margin:0 0 18px}
h2{font-family:var(--f-head);font-size:1.45rem;font-weight:700;letter-spacing:-.01em;text-wrap:balance;margin:56px 0 14px;padding-top:18px;border-top:1px solid var(--rule)}
h3{font-family:var(--f-head);font-size:1.08rem;font-weight:600;margin:32px 0 10px}
p{margin:0 0 16px}
p.fa{font-family:var(--f-fa);font-size:16px;line-height:1.9;text-align:right;background:var(--card2);padding:16px 20px;border-radius:8px}
p.en{font-family:var(--f-body);font-size:16px;line-height:1.62;text-align:left;direction:ltr;background:var(--card2);padding:16px 20px;border-radius:8px}
a{color:var(--accent)}
strong{font-weight:600}
hr{border:0;border-top:1px solid var(--rule);margin:40px 0}
ul,ol{padding-left:1.3em;margin:0 0 16px} body.rtl ul,body.rtl ol{padding-left:0;padding-right:1.3em} li{margin:4px 0}
code{font-family:var(--f-mono);font-size:.84em;background:var(--card2);padding:.1em .35em;border-radius:4px;direction:ltr;unicode-bidi:embed}
pre{background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:14px 16px;overflow-x:auto;font-family:var(--f-mono);font-size:13px;line-height:1.6;margin:0 0 20px;direction:ltr;text-align:left}
pre code{background:none;padding:0;font-size:inherit}
pre.mermaid{background:var(--card);text-align:center;padding:18px 10px}
.tw{overflow-x:auto;border:1px solid var(--rule);border-radius:8px;background:var(--card);margin:0 0 8px}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{padding:9px 12px;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}
body.rtl th,body.rtl td{text-align:right}
th{font-family:var(--f-head);font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);background:var(--card2);white-space:nowrap}
td{font-variant-numeric:tabular-nums} tbody tr:last-child td{border-bottom:0}
td[align=right],th[align=right]{text-align:right}
p.cap{font-family:var(--f-head);font-size:13px;color:var(--dim);margin:6px 0 26px}
figure{margin:0 0 22px;background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:10px}
figure img{display:block;max-width:100%;height:auto;margin:0 auto;border-radius:4px}
figcaption{font-family:var(--f-head);font-size:12.5px;color:var(--dim);text-align:center;margin-top:8px}
@media (max-width:900px){.shell,body.rtl .shell{grid-template-columns:minmax(0,1fr);gap:0;padding:24px 16px 64px} nav.rail{display:none} body{font-size:16px}}
@media (prefers-reduced-motion: reduce){*{scroll-behavior:auto}}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;700'
         '&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400'
         '&family=IBM+Plex+Mono:wght@400;500&display=swap">')


def build(md_path, out_path, rtl=False, title=None):
    docs_dir = os.path.dirname(os.path.abspath(md_path))
    src = open(md_path, encoding="utf-8").read()

    def embed(m):
        alt, path = m.group(1), m.group(2)
        full = os.path.join(docs_dir, path)
        if not os.path.exists(full):
            return m.group(0)
        data = base64.b64encode(open(full, "rb").read()).decode()
        return f'<figure><img src="data:image/png;base64,{data}" alt="{alt}"><figcaption>{alt}</figcaption></figure>'

    src = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", embed, src)
    body = markdown.markdown(src, extensions=["tables", "fenced_code", "toc"],
                             extension_configs={"toc": {"toc_depth": "2-3"}})
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: '<pre class="mermaid">' + m.group(1) + '</pre>', body, flags=re.S)
    body = body.replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")
    body = re.sub(r'</div>\s*<p><em>((?:Table|جدول) [^<]*?)</em></p>', r'</div><p class="cap">\1</p>', body, flags=re.S)
    body = body.replace("<p>چکیده:", '<p class="fa" dir="rtl" lang="fa">چکیده:')
    body = body.replace("<p>Abstract:", '<p class="en" dir="ltr" lang="en">Abstract:')
    # the markdown Contents section is replaced by the rail
    body = re.sub(r'<h2 id="[^"]*">(?:Contents|فهرست)</h2>.*?(?=<hr\s*/?>)', '', body, flags=re.S)
    items = [(m.group(1), re.sub(r"<[^>]+>", "", m.group(2))) for m in re.finditer(r'<h2 id="([^"]+)">(.*?)</h2>', body)]
    rail = "<ul>" + "".join(f'<li><a href="#{i}">{t}</a></li>' for i, t in items) + "</ul>"
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    title = title or (re.sub(r"<[^>]+>", "", h1.group(1)) if h1 else os.path.basename(md_path))
    page = (f"<title>{title}</title>\n{FONTS}\n<style>{CSS}</style>\n"
            f'<body class="{"rtl" if rtl else ""}" dir="{"rtl" if rtl else "ltr"}" lang="{"fa" if rtl else "en"}">\n'
            f'<div class="shell"><nav class="rail" aria-label="Contents"><p class="k">{"فهرست" if rtl else "Contents"}</p>{rail}</nav>\n'
            f"<main>\n{body}\n</main></div></body>\n")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(page)
    return len(page), len(items)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rtl = "--rtl" in sys.argv
    size, n = build(args[0], args[1], rtl=rtl)
    print(f"wrote {args[1]}: {size} bytes, {n} chapters")
