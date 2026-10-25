"""Build a small ReportLab profile trial and its independent expected-text manifest.

The trial is also an example of tracking source blocks across pagination. Adapt it
to include a real difficult equation/table/figure and each script in the next paper.
"""
import argparse
import html
import io
from pathlib import Path

from reading_profile import ROOT, DEFAULT_PROFILE, load_profile, reportlab_styles, check_glyphs, sha256
from pdf_tools import write_json


def build_probe(out_dir, profile_path=DEFAULT_PROFILE, sample_text=None, sample_font=None):
    import pymupdf
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, PageBreak, Table, TableStyle, Image, KeepTogether

    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_path = Path(profile_path).resolve()
    profile = load_profile(profile_path)
    styles = reportlab_styles(profile)
    width, height = profile["page_pt"]
    colors, margins = profile["colors"], profile["margins_pt"]
    content_width = width-margins["left"]-margins["right"]
    expected, bookmarks, links = {}, [], []

    class TrackedParagraph(Paragraph):
        audit_id = None

        def split(self, aw, ah):
            parts = super().split(aw, ah)
            for part in parts:
                part.audit_id = self.audit_id
            return parts

        def drawOn(self, canvas, x, y, _sW=0):
            ax, ay = canvas.absolutePosition(x, y)
            expected[self.audit_id]["regions"].append({"page": canvas.getPageNumber(),
                "bbox": [ax, height-ay-self.height-2, ax+self.width, height-ay+3]})
            return super().drawOn(canvas, x, y, _sW)

    def para(ident, text, style="body", **metadata):
        p = TrackedParagraph(text, styles[style])
        p.audit_id = ident
        check_glyphs(p)
        expected[ident] = {"id": ident, "kind": "text", "text": p.getPlainText(), "regions": [], **metadata}
        return p

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor(colors["background"]))
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        spec = profile["styles"]["footer"]
        text = f"Profile trial • {profile['id']} • {doc.page}"
        canvas.setFont("Eink_regular", spec["size_pt"])
        canvas.setFillColor(HexColor(colors["muted"]))
        canvas.drawString(margins["left"], 18, text)
        expected[f"footer-{doc.page}"] = {"id": f"footer-{doc.page}", "kind": "navigation", "text": text,
            "style": "footer", "regions": [{"page": doc.page, "bbox": [margins["left"], height-32, width-margins["right"], height-6]}]}
        canvas.restoreState()

    class ProbeDoc(BaseDocTemplate):
        def afterFlowable(self, flowable):
            if getattr(flowable, "audit_id", "") == "title":
                self.canv.bookmarkPage("trial")
                self.canv.addOutlineEntry("Profile trial", "trial", 0)
                bookmarks.append([1, "Profile trial", self.page])

    class EmbeddedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            kwargs["initialFontName"] = "Eink_regular"
            super().__init__(*args, **kwargs)

    # Use explicit expected style metadata, including the actual bold/italic font.
    story = [para("title", "Profile trial", "h1")]
    expected["title"]["style"] = "h1"
    for role, markup in [("regular", "Regular: readable reasoning, one step at a time."),
                         ("bold", "<b>Bold: important conditions remain visible.</b>"),
                         ("italic", "<i>Italic: scientific names and qualifications.</i>"),
                         ("bold_italic", "<b><i>Bold italic: a real embedded face.</i></b>")]:
        story.append(para(role, markup))
        expected[role].update(style="body", fonts=[Path(profile["fonts"][role]).stem])
    for name, text in [("h2", "Section heading"), ("h3", "Subsection heading"),
                       ("label", "Original model response"), ("body", "The example label stays with these opening lines."),
                       ("caption", "Figure 1. Captions use the shared size and color."),
                       ("reference", "Reference entry, with complete publication information."),
                       ("code", "score = value - baseline"),
                       ("equation", "y = αx − β; Δ = 0.25 × 4 = 1")]:
        story.append(para("sample-"+name, html.escape(text), name))
        expected["sample-"+name]["style"] = name
    story.append(para("math-limit", "This symbol sample tests glyphs. Also trial the paper’s actual fractions, indices and multiline equations before drafting." , "caption"))
    story.append(PageBreak())
    story.append(para("table-title", "Table continuation", "h2"))
    data = []
    for row in range(35):
        values = ["Item", "A", "B"] if row == 0 else [f"Row {row:02}", str(row*3), str(row*7)]
        cells = []
        for col, value in enumerate(values):
            ident = f"table-r{row}c{col}"
            cells.append(para(ident, value, "table_header" if row == 0 else "table",
                              kind="table-cell", table="trial", row=row, column=col))
            expected[ident]["style"] = "table_header" if row == 0 else "table"
        data.append(cells)
    table = Table(data, colWidths=[content_width*.5, content_width*.25, content_width*.25], repeatRows=1)
    table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Eink_regular"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(colors["panel"])),
        ("LINEBELOW", (0, 0), (-1, -1), .4, HexColor(colors["rule"]))]))
    story.extend([table, PageBreak(), para("art-title", "Artwork and light panel", "h2")])
    with pymupdf.open(ROOT / "assets/probe-figure.svg") as svg:
        with pymupdf.open("pdf", svg.convert_to_pdf()) as vector:
            image_bytes = vector[0].get_pixmap(dpi=300, alpha=False).tobytes("png")
    story.append(KeepTogether([Image(io.BytesIO(image_bytes), width=content_width, height=content_width*140/360),
        para("art-caption", "The whole SVG canvas, both corner markers, and both colored curves must remain visible. This trial uses a 300-DPI raster fallback.", "caption")]))
    light = styles["body"].clone("light")
    light.textColor = HexColor(colors["light_text"])
    styles["light"] = light
    light_para = para("light-panel", "<b>Bold</b>, <i>italic</i> and regular text on white.", "light")
    expected["light-panel"].update(style="body", color="light_text",
                                  fonts=["DejaVuSans", "DejaVuSans-Bold", "DejaVuSans-Oblique"])
    light_box = Table([[light_para]], colWidths=[content_width])
    light_box.setStyle(TableStyle([("FONTNAME", (0,0), (-1,-1), "Eink_regular"), ("BACKGROUND", (0,0), (-1,-1), HexColor(colors["light_panel"])),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8)]))
    story.append(light_box)
    if sample_text:
        if sample_font:
            pdfmetrics.registerFont(TTFont("ScriptSample", str(sample_font)))
            styles["script"] = styles["body"].clone("script", fontName="ScriptSample", wordWrap="CJK")
        story.append(para("script-sample", html.escape(Path(sample_text).read_text(encoding="utf-8")), "script" if sample_font else "body"))
    doc = ProbeDoc(str(out_dir / "probe.pdf"), pagesize=(width,height), title="E-ink profile trial")
    doc.addPageTemplates(PageTemplate(id="reading", onPage=footer, frames=[Frame(
        margins["left"], margins["bottom"], width-margins["left"]-margins["right"], height-margins["top"]-margins["bottom"],
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)]))
    flow_order = list(expected)
    doc.build(story, canvasmaker=EmbeddedCanvas)
    # Repeated headers are independent expected occurrences; normal split paragraphs
    # keep one source text and ordered fragments. Never infer expected text from PDF.
    for col in range(3):
        original = expected[f"table-r0c{col}"]
        for index, region in enumerate(original["regions"][1:], 1):
            ident = f"{original['id']}-repeat-{index}"
            expected[ident] = {**original, "id": ident, "repeat_of": original["id"], "regions": [region]}
        original["regions"] = original["regions"][:1]
    inputs = [Path(__file__), ROOT / "scripts/reading_profile.py", ROOT / "scripts/requirements.txt",
              ROOT / "assets/fonts/manifest.json", ROOT / "assets/probe-figure.svg"]
    inputs.extend(Path(p).resolve() for p in (sample_text, sample_font) if p)
    write_json(out_dir / "manifest.json", {"schema": 1, "profile_sha256": sha256(profile_path),
        "page_count": doc.page, "inputs": [{"path": str(p), "sha256": sha256(p)} for p in inputs],
        "blocks": list(expected.values()), "flow_order": flow_order, "links": links, "bookmarks": bookmarks, "exclusions": []})
    return out_dir / "probe.pdf", out_dir / "manifest.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--sample-text", type=Path, help="UTF-8 excerpt containing the paper's required scripts")
    parser.add_argument("--sample-font", type=Path, help="Explicit TrueType script font; record its license and hash")
    args = parser.parse_args()
    build_probe(args.out_dir, args.profile, args.sample_text, args.sample_font)
    print(args.out_dir / "probe.pdf")
