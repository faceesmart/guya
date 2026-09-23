#!/usr/bin/env node
// Build the Word version of docs/REPORT.md or docs/REPORT-FA.md with docx-js.
//
//   cd docs/tools && npm install                     # docx, marked, image-size
//   node docs/tools/build_report_docx.js docs/REPORT.md docs/Guya-Report-EN.docx --figdir out/mermaid-en
//   node docs/tools/build_report_docx.js docs/REPORT-FA.md docs/Guya-Report-FA.docx --rtl --figdir out/mermaid-fa
//
// The diagrams come from the PNG files that build_report_pdf.py saves (one per mermaid block,
// in order of appearance). The table of contents is a Word field: Word fills it in when the
// document is opened (it asks once whether to update fields).

const fs = require("fs");
const path = require("path");
const { marked } = require("marked");
const { imageSize } = require("image-size");
const D = require("docx");

const argv = process.argv.slice(2);
const take = (flag) => { const i = argv.indexOf(flag); if (i < 0) return null; const v = argv[i + 1]; argv.splice(i, 2); return v; };
const FIGDIR = take("--figdir");
const RTL = argv.includes("--rtl");
const [MD_PATH, OUT_PATH] = argv.filter((a) => !a.startsWith("--"));
if (!MD_PATH || !OUT_PATH) { console.error("usage: build_report_docx.js REPORT.md OUT.docx [--rtl] [--figdir DIR]"); process.exit(2); }

const DOCS_DIR = path.dirname(path.resolve(MD_PATH));
const REPO = path.resolve(__dirname, "..", "..");
const LANG = RTL ? "fa" : "en";
const S = {
  en: { contents: "Contents", institution: "University of Tehran · Farabi Campus · Faculty of Engineering",
        kind: "B.Sc. Final-Year Project Report in Computer Engineering", date: "September 2026" },
  fa: { contents: "فهرست مطالب", institution: "دانشگاه تهران · دانشکدگان فارابی · دانشکدهٔ مهندسی",
        kind: "گزارش پروژهٔ پایانی دورهٔ کارشناسی مهندسی کامپیوتر", date: "شهریور ۱۴۰۵" },
}[LANG];

// A4, 2.5 cm margins, in DXA (1440 = 1 inch)
const PAGE = { width: 11906, height: 16838 };
const MARGIN = 1417;
const CONTENT = PAGE.width - 2 * MARGIN;        // 9072 DXA = 6.3 in
const MAX_IMG_PX = 590;                          // a little under the content width at 96 dpi
const MAX_IMG_H_PX = 700;
const LAND = { w: 900, h: 500 };                 // image limits on a landscape page
const WIDE_PX = 900;                             // a diagram wider than this (in CSS px) gets a landscape page

// The university's conventional academic type: B Nazanin for Persian text, B Titr for chapter
// titles, Times New Roman for Latin text. Word picks the Latin face (ascii/hAnsi) for Latin
// characters and the complex-script face (cs) for Persian ones, so one run can carry both.
const BODY_FONT = RTL ? "B Nazanin" : "Times New Roman";
const HEAD_FONT = RTL ? "B Titr" : "Times New Roman";
const MONO_FONT = "Courier New";
const LATIN_FONT = "Times New Roman";
const FONT = (name) => (name === MONO_FONT
  ? { ascii: MONO_FONT, hAnsi: MONO_FONT, cs: MONO_FONT, eastAsia: MONO_FONT }
  : { ascii: RTL ? LATIN_FONT : name, hAnsi: RTL ? LATIN_FONT : name, cs: RTL ? name : "B Nazanin", eastAsia: RTL ? LATIN_FONT : name });
const BODY_SIZE = RTL ? 28 : 26;                 // half-points: 14 pt Persian, 13 pt English
const hasPersian = (t) => /[؀-ۿ]/.test(t);

const unescape = (t) => t.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");

// ---------- inline tokens -> runs ----------
function runs(tokens, ctx = {}) {
  const out = [];
  for (const t of tokens || []) {
    switch (t.type) {
      case "text":
        if (t.tokens) out.push(...runs(t.tokens, ctx));
        else out.push(textRun(unescape(t.text), ctx));
        break;
      case "escape": out.push(textRun(t.text, ctx)); break;
      case "strong": out.push(...runs(t.tokens, { ...ctx, bold: true })); break;
      case "em": out.push(...runs(t.tokens, { ...ctx, italic: true })); break;
      case "del": out.push(...runs(t.tokens, { ...ctx, strike: true })); break;
      case "codespan": out.push(textRun(unescape(t.text), { ...ctx, code: true })); break;
      case "link": {
        const inner = runs(t.tokens, { ...ctx, link: true });
        out.push(new D.ExternalHyperlink({ children: inner, link: t.href }));
        break;
      }
      case "br": out.push(new D.TextRun({ break: 1 })); break;
      case "image": break;                       // handled at block level
      case "html": out.push(textRun(unescape(t.text.replace(/<[^>]+>/g, "")), ctx)); break;
      default: if (t.text) out.push(textRun(unescape(t.text), ctx));
    }
  }
  return out;
}

function textRun(text, ctx) {
  const persian = hasPersian(text);
  const opts = {
    text,
    bold: !!ctx.bold,
    italics: !!ctx.italic,
    strike: !!ctx.strike,
    rightToLeft: (RTL && !ctx.code) ? (persian || !/[A-Za-z]/.test(text)) : persian,
    font: FONT(ctx.code ? MONO_FONT : (ctx.head ? HEAD_FONT : BODY_FONT)),
    size: ctx.size || (ctx.code ? BODY_SIZE - 3 : BODY_SIZE),
    sizeComplexScript: ctx.size || (ctx.code ? BODY_SIZE - 3 : BODY_SIZE),
  };
  if (ctx.code) opts.shading = { type: D.ShadingType.CLEAR, fill: "EEF1F1", color: "auto" };
  if (ctx.link) { opts.color = "0F766E"; }
  if (ctx.color) opts.color = ctx.color;
  return new D.TextRun(opts);
}

// ---------- block helpers ----------
function startsPersian(children) {                // a Persian sentence inside the English report reads right to left
  for (const c of children) {
    const t = c && c.options && c.options.text;
    if (typeof t !== "string" || !t.trim()) continue;
    return hasPersian(t.trim()[0]);
  }
  return false;
}
function para(children, opts = {}) {
  const bidi = opts.bidi !== undefined ? opts.bidi : (RTL || startsPersian(children));
  return new D.Paragraph({
    children,
    bidirectional: bidi,
    alignment: opts.alignment !== undefined ? opts.alignment : (bidi ? D.AlignmentType.JUSTIFIED : D.AlignmentType.JUSTIFIED),
    spacing: opts.spacing || { after: 140, line: RTL ? 380 : 300 },
    keepNext: opts.keepNext, keepLines: opts.keepLines, pageBreakBefore: opts.pageBreakBefore,
    heading: opts.heading, style: opts.style, numbering: opts.numbering, indent: opts.indent,
  });
}

function plainText(tokens) { return (tokens || []).map((t) => t.tokens ? plainText(t.tokens) : (t.text || "")).join(""); }

const numberingConfigs = [{
  reference: "bullets",
  levels: [0, 1].map((lvl) => ({ level: lvl, format: D.LevelFormat.BULLET, text: lvl ? "◦" : "•", alignment: D.AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 640 + lvl * 400, hanging: 320 } } } })),
}];
let orderedCount = 0;
function orderedRef(start) {
  const ref = `ordered-${orderedCount++}`;
  numberingConfigs.push({ reference: ref, levels: [{ level: 0, format: D.LevelFormat.DECIMAL, text: "%1.", alignment: D.AlignmentType.LEFT,
    start: start || 1, style: { paragraph: { indent: { left: 640, hanging: 360 } } } }] });
  return ref;
}

function listBlocks(list, level = 0) {
  const out = [];
  const ref = list.ordered ? orderedRef(list.start) : "bullets";
  for (const item of list.items) {
    let inline = [], nested = [];
    for (const t of item.tokens) {
      if (t.type === "text" || t.type === "paragraph") inline.push(...(t.tokens || [{ type: "text", text: t.text }]));
      else if (t.type === "list") nested.push(t);
      else if (t.type === "space") continue;
      else inline.push({ type: "text", text: t.raw || t.text || "" });
    }
    out.push(para(runs(inline), { numbering: { reference: ref, level: Math.min(level, 1) }, spacing: { after: 80, line: RTL ? 360 : 290 } }));
    for (const n of nested) out.push(...listBlocks(n, level + 1));
  }
  return out;
}

function imageParagraph(file, opts = {}) {
  if (!fs.existsSync(file)) { console.warn("missing image", file); return [para([textRun(`[image missing: ${path.basename(file)}]`, {})])]; }
  const data = fs.readFileSync(file);
  const dim = imageSize(data);
  let w = dim.width, h = dim.height;
  const retina = opts.retina || /\.jpe?g$/i.test(file);
  if (retina) { w /= 2; h /= 2; }
  const limit = opts.landscape ? LAND : { w: MAX_IMG_PX, h: MAX_IMG_H_PX };
  const scale = Math.min(1, limit.w / w, limit.h / h);
  w = Math.round(w * scale); h = Math.round(h * scale);
  const type = /\.jpe?g$/i.test(file) ? "jpg" : "png";
  return [new D.Paragraph({ alignment: D.AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 60 },
    children: [new D.ImageRun({ type, data, transformation: { width: w, height: h }, altText: { title: path.basename(file), description: path.basename(file), name: path.basename(file) } })] })];
}

function codeBlock(text) {
  const lines = text.replace(/\t/g, "    ").split("\n");
  return lines.map((line, i) => new D.Paragraph({
    style: "CodeBlock", bidirectional: false, alignment: D.AlignmentType.LEFT,
    keepNext: i < lines.length - 1, keepLines: true,
    spacing: { before: i === 0 ? 120 : 0, after: i === lines.length - 1 ? 160 : 0, line: 240 },
    children: [new D.TextRun({ text: line || " ", font: FONT(MONO_FONT), size: 18, sizeComplexScript: 18 })],
  }));
}

function tableBlock(tok) {
  const header = tok.header.map((c) => c.tokens);
  const headerText = tok.header.map((c) => c.text.trim()).some(Boolean);
  const rows = tok.rows.map((r) => r.map((c) => c.tokens));
  const ncol = header.length;
  // column widths from the longest text in each column, bounded
  const lens = header.map((c, i) => Math.max(plainText(c).length, ...rows.map((r) => plainText(r[i] || []).length), 4));
  const weights = lens.map((l) => Math.min(Math.max(Math.sqrt(l), 2.2), 9));
  const total = weights.reduce((a, b) => a + b, 0);
  const widths = weights.map((w) => Math.round(CONTENT * w / total));
  widths[widths.length - 1] += CONTENT - widths.reduce((a, b) => a + b, 0);
  const cell = (tokens, i, isHeader) => {
    const numeric = tok.align[i] === "right";
    const alignment = isHeader ? undefined : (numeric ? (RTL ? undefined : D.AlignmentType.RIGHT) : (RTL ? undefined : D.AlignmentType.LEFT));
    return new D.TableCell({
      width: { size: widths[i], type: D.WidthType.DXA },
      shading: isHeader ? { type: D.ShadingType.CLEAR, fill: "E8F1F0", color: "auto" } : undefined,
      margins: { top: 50, bottom: 50, left: 80, right: 80 },
      verticalAlign: D.VerticalAlign.TOP,
      children: [new D.Paragraph({ bidirectional: RTL, alignment, spacing: { after: 0, line: RTL ? 320 : 260 },
        children: runs(tokens, { bold: isHeader, size: RTL ? 19 : 18, head: isHeader }) })],
    });
  };
  const trs = [];
  if (headerText) trs.push(new D.TableRow({ tableHeader: true, cantSplit: true, children: header.map((c, i) => cell(c, i, true)) }));
  for (const r of rows) trs.push(new D.TableRow({ cantSplit: true, children: Array.from({ length: ncol }, (_, i) => cell(r[i] || [], i, false)) }));
  return [new D.Table({ rows: trs, columnWidths: widths, width: { size: CONTENT, type: D.WidthType.DXA }, visuallyRightToLeft: RTL,
    borders: border(), }), new D.Paragraph({ spacing: { after: 60 }, children: [] })];
}
function border() {
  const b = { style: D.BorderStyle.SINGLE, size: 4, color: "B9C2C2" };
  return { top: b, bottom: b, left: b, right: b, insideHorizontal: b, insideVertical: b };
}

// ---------- document assembly ----------
const src = fs.readFileSync(MD_PATH, "utf8");
const tokens = marked.lexer(src, { gfm: true });

let title = "", subtitle = "", metaRows = [];
const front = [];            // Figures / Tables paragraphs from the Contents section
const body = [];
let mermaidIndex = 0;
let pendingLandscape = null; // a wide diagram waiting for its caption
let state = "start";         // start -> contents -> body

for (const tok of tokens) {
  if (tok.type === "space" || tok.type === "hr") continue;
  if (state === "start") {
    if (tok.type === "heading" && tok.depth === 1) { title = plainText(tok.tokens); continue; }
    if (tok.type === "paragraph" && !subtitle) { subtitle = plainText(tok.tokens); continue; }
    if (tok.type === "table") { metaRows = tok.rows.map((r) => r.map((c) => c.tokens)); continue; }
    if (tok.type === "heading" && tok.depth === 2) { state = "contents"; continue; }
  }
  if (state === "contents") {
    if (tok.type === "heading" && tok.depth === 2) { state = "body"; }
    else {
      if (tok.type === "paragraph" && tok.tokens[0] && tok.tokens[0].type === "strong") {
        front.push(para(runs(tok.tokens, { size: BODY_SIZE - 2 }), { spacing: { after: 160, line: RTL ? 360 : 280 } }));
      }
      continue;
    }
  }
  // body
  switch (tok.type) {
    case "heading": {
      const text = runs(tok.tokens, { head: true, size: tok.depth === 2 ? 34 : 26, bold: true, color: tok.depth === 2 ? "0F5F58" : "111111" });
      body.push(para(text, { heading: tok.depth === 2 ? D.HeadingLevel.HEADING_1 : D.HeadingLevel.HEADING_2,
        alignment: RTL ? undefined : D.AlignmentType.LEFT, pageBreakBefore: tok.depth === 2, keepNext: true,
        spacing: tok.depth === 2 ? { before: 0, after: 240, line: 300 } : { before: 300, after: 120, line: 300 } }));
      break;
    }
    case "paragraph": {
      const first = tok.tokens[0];
      if (first && first.type === "image" && tok.tokens.length === 1) { body.push(...imageParagraph(path.join(DOCS_DIR, first.href))); break; }
      const text = plainText(tok.tokens);
      if (first && first.type === "em" && tok.tokens.length === 1 && /^(Table|Figure|جدول|شکل) /.test(text)) {
        const cap = para(runs(first.tokens, { italic: true, size: BODY_SIZE - 3, head: true, color: "333333" }), { alignment: D.AlignmentType.CENTER, spacing: { before: 40, after: 240, line: 280 } });
        if (pendingLandscape) { pendingLandscape.__landscape.push(cap); pendingLandscape = null; } else body.push(cap);
        break;
      }
      if (/^چکیده:/.test(text)) { body.push(para(runs(tok.tokens), { bidi: true, spacing: { after: 200, line: 380 } })); break; }
      if (/^Abstract:/.test(text)) { body.push(para(runs(tok.tokens), { bidi: false, spacing: { after: 200, line: 300 } })); break; }
      body.push(para(runs(tok.tokens)));
      break;
    }
    case "table": body.push(...tableBlock(tok)); break;
    case "list": body.push(...listBlocks(tok)); break;
    case "code": {
      if (tok.lang === "mermaid") {
        const file = FIGDIR ? path.join(FIGDIR, `fig-${mermaidIndex}.png`) : null;
        mermaidIndex += 1;
        if (!file || !fs.existsSync(file)) { body.push(para([textRun("[diagram]", {})])); break; }
        const wide = imageSize(fs.readFileSync(file)).width / 2 > WIDE_PX;
        if (wide) {                                  // its own landscape section, caption included
          const block = { __landscape: imageParagraph(file, { retina: true, landscape: true }) };
          body.push(block); pendingLandscape = block;
        } else body.push(...imageParagraph(file, { retina: true }));
      } else body.push(...codeBlock(tok.text));
      break;
    }
    case "blockquote": body.push(para(runs(tok.tokens.flatMap((t) => t.tokens || []), { italic: true }))); break;
    case "html": break;
    default: if (tok.text) body.push(para([textRun(tok.text, {})]));
  }
}

// cover
const center = (children, spacing) => new D.Paragraph({ alignment: D.AlignmentType.CENTER, bidirectional: RTL, spacing, children });
const cover = [
  center([textRun(S.institution, { head: true, size: 22, color: "333333" })], { before: 0, after: 200 }),
  center([textRun(S.kind, { head: true, size: 25, bold: true, color: "0F766E" })], { before: 600, after: 1800 }),
  center([textRun(title, { head: true, size: 44, bold: true })], { before: 0, after: 1800, line: 340 }),
  ...metaRows.filter((r) => !/^(Code|کد)/.test(plainText(r[0]))).map((r) =>
    center([...runs(r[0], { head: true, bold: true, size: 23, color: "333333" }), textRun("   ", {}), ...runs(r[1], { head: true, size: 23 })], { after: 120, line: 320 })),
  center([textRun(S.date, { head: true, size: 22, color: "333333" })], { before: 1200, after: 0 }),
  new D.Paragraph({ children: [new D.PageBreak()] }),
];

const toc = [
  new D.Paragraph({ bidirectional: RTL, spacing: { after: 240 }, children: [textRun(S.contents, { head: true, size: 34, bold: true, color: "0F5F58" })] }),
  new D.TableOfContents(S.contents, { hyperlink: true, headingStyleRange: "1-2" }),
  new D.Paragraph({ spacing: { before: 240 }, children: [] }),
  ...front,
];

const footer = new D.Footer({ children: [new D.Paragraph({ alignment: D.AlignmentType.CENTER,
  children: [new D.TextRun({ children: [D.PageNumber.CURRENT], font: FONT(HEAD_FONT), size: 18 })] })] });

const docOptions = {
  creator: "MohammadReza Ganji", title, description: subtitle, lastModifiedBy: "MohammadReza Ganji",
  features: { updateFields: true },
  numbering: { config: numberingConfigs },
  styles: {
    default: { document: { run: { font: FONT(BODY_FONT), size: BODY_SIZE, sizeComplexScript: BODY_SIZE } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT(HEAD_FONT), size: 40, bold: true, color: "0F5F58" }, paragraph: { spacing: { before: 0, after: 240 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT(RTL ? BODY_FONT : HEAD_FONT), size: 36, bold: true, color: "111111" }, paragraph: { spacing: { before: 300, after: 120 }, outlineLevel: 1 } },
      { id: "CodeBlock", name: "Code Block", basedOn: "Normal", next: "Normal",
        run: { font: FONT(MONO_FONT), size: 18 }, paragraph: { spacing: { before: 0, after: 0, line: 240 },
          shading: { type: D.ShadingType.CLEAR, fill: "F4F6F6", color: "auto" }, indent: { left: 120, right: 120 } } },
    ],
  },
  sections: [],
};
// portrait sections, interrupted by a landscape section for each wide diagram
const margins = { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN };
const portrait = (children, first) => ({
  properties: { page: { size: PAGE, margin: margins }, titlePage: !!first },
  footers: first ? { default: footer, first: new D.Footer({ children: [] }) } : { default: footer },
  children,
});
const landscape = (children) => ({
  properties: { page: { size: { width: PAGE.width, height: PAGE.height, orientation: D.PageOrientation.LANDSCAPE }, margin: margins } },
  footers: { default: footer },
  children,
});
let cur = [...cover, ...toc, new D.Paragraph({ children: [new D.PageBreak()] })];
let firstSection = true;
for (const block of body) {
  if (block && block.__landscape) {
    if (cur.length) { docOptions.sections.push(portrait(cur, firstSection)); firstSection = false; cur = []; }
    docOptions.sections.push(landscape(block.__landscape));
  } else cur.push(block);
}
if (cur.length) docOptions.sections.push(portrait(cur, firstSection));
// No font is embedded: B Nazanin and B Titr are proprietary and present on the readers' machines.

const doc = new D.Document(docOptions);
D.Packer.toBuffer(doc).then(async (buf) => {
  // docx-js writes the embedded font's GUID in lower case; the schema (and Word) want upper case.
  const JSZip = require("jszip");
  const zip = await JSZip.loadAsync(buf);
  const ft = zip.file("word/fontTable.xml");
  if (ft) {
    const xml = (await ft.async("string")).replace(/w:fontKey="\{([0-9a-f-]+)\}"/g, (m, g) => `w:fontKey="{${g.toUpperCase()}}"`);
    zip.file("word/fontTable.xml", xml);
    buf = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
  }
  fs.writeFileSync(OUT_PATH, buf);
  console.log(`wrote ${OUT_PATH}: ${(buf.length / 1024).toFixed(0)} KB, ${body.length} body blocks, ${mermaidIndex} diagrams`);
}).catch((e) => { console.error(e); process.exit(1); });
