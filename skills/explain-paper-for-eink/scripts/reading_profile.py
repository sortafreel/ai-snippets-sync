"""Shared fonts and styles. Python 3.11+; paths resolve relative to this package."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "assets/reading-profile.json"
FONT_DIR = ROOT / "assets/fonts"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_profile(path=DEFAULT_PROFILE):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    manifest = json.loads((FONT_DIR / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files"].items():
        if sha256(FONT_DIR / name) != digest:
            raise ValueError(f"Bundled font/license changed: {name}")
    for name in profile["fonts"].values():
        if name not in manifest["files"]:
            raise ValueError(f"Unpinned base font: {name}")
    return profile


def reportlab_styles(profile):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for role, filename in profile["fonts"].items():
        pdfmetrics.registerFont(TTFont("Eink_" + role, str(FONT_DIR / filename)))
    for prefix, role in [("", "regular"), ("mono_", "mono")]:
        pdfmetrics.registerFontFamily(
            "Eink_" + role, normal="Eink_" + role,
            bold="Eink_" + prefix + "bold", italic="Eink_" + prefix + "italic",
            boldItalic="Eink_" + prefix + "bold_italic")
    styles = {}
    for name, spec in profile["styles"].items():
        styles[name] = ParagraphStyle(
            name, fontName="Eink_" + spec["font"], fontSize=spec["size_pt"],
            leading=spec["leading_pt"], textColor=HexColor(profile["colors"][spec["color"]]),
            spaceBefore=spec.get("space_before_pt", 0),
            spaceAfter=0 if name.startswith("table") else 8,
            keepWithNext=name in {"h1", "h2", "h3", "label", "equation"},
            allowWidows=0, allowOrphans=0, splitLongWords=False)
    return styles


def check_glyphs(paragraph):
    """Call before rendering every ReportLab paragraph, including table cells."""
    from reportlab.pdfbase import pdfmetrics
    for fragment in paragraph.frags:
        if not hasattr(fragment, "text"):
            continue
        font = pdfmetrics.getFont(fragment.fontName)
        cmap = getattr(font.face, "charToGlyph", {})
        missing = {c for c in fragment.text if not c.isspace() and c not in "\u200c\u200d" and ord(c) not in cmap}
        if missing:
            codes = ", ".join(f"{c!r} U+{ord(c):04X}" for c in sorted(missing))
            raise ValueError(f"Missing glyphs in {fragment.fontName}: {codes}; add an explicit script-specific font")


def css(profile):
    """Generate CSS from the same tokens; use an adjacent saved copy of the profile."""
    c, m = profile["colors"], profile["margins_pt"]
    rules = []
    for role, filename in profile["fonts"].items():
        family = "EinkMono" if role.startswith("mono") else "EinkSans"
        weight = 700 if "bold" in role else 400
        style = "italic" if "italic" in role else "normal"
        rules.append(f'@font-face {{ font-family: "{family}"; src: url("{(FONT_DIR / filename).as_uri()}"); font-weight: {weight}; font-style: {style}; }}')
    width, height = profile["page_pt"]
    rules.append(f'@page {{ size: {width}pt {height}pt; margin: {m["top"]}pt {m["right"]}pt {m["bottom"]}pt {m["left"]}pt; background: {c["background"]}; }}')
    rules.append(f'html, body {{ background: {c["background"]}; color: {c["text"]}; print-color-adjust: exact; -webkit-print-color-adjust: exact; font-synthesis: none; }}')
    selectors = {"body": "body", "h1": "h1", "h2": "h2", "h3": "h3", "caption": "figcaption, caption", "table": "td", "table_header": "th", "label": ".example-label", "reference": ".reference", "code": "pre, code", "equation": ".equation", "footer": ".footer"}
    for name, s in profile["styles"].items():
        family = "EinkMono" if s["font"].startswith("mono") else "EinkSans"
        rules.append(f'{selectors[name]} {{ font-family: "{family}"; font-size: {s["size_pt"]}pt; line-height: {s["leading_pt"]}pt; color: {c[s["color"]]}; font-weight: {700 if "bold" in s["font"] else 400}; margin-top: {s.get("space_before_pt", 0)}pt; }}')
    rules.extend([
        'body { margin: 0; } p { margin: 0 0 8pt; orphans: 2; widows: 2; }',
        'h1, h2, h3, .example-label, .equation { break-after: avoid; }',
        'a { color: inherit; text-decoration: underline; } strong { color: inherit; }',
        f'.light {{ background: {c["light_panel"]}; color: {c["light_text"]}; padding: 8pt; }}',
        '.light :is(p, h1, h2, h3, th, td, caption, figcaption, .example-label, .reference, .equation, pre, code) { color: inherit; }',
        'table { border-collapse: collapse; width: 100%; } thead { display: table-header-group; }',
        f'th, td {{ padding: 5pt; border-bottom: 0.4pt solid {c["rule"]}; vertical-align: top; text-align: left; }}',
        'tr, figure, .keep { break-inside: avoid; } figure { margin: 8pt 0; } img { max-width: 100%; height: auto; }',
        'pre { white-space: pre-wrap; }'
    ])
    return "\n".join(rules) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--css", type=Path, required=True)
    args = parser.parse_args()
    args.css.write_text(css(load_profile(args.profile)), encoding="utf-8")
