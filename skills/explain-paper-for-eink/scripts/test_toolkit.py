"""Behavioral fixtures: prove that corruption is rejected, not merely that a PDF builds."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from reading_profile import DEFAULT_PROFILE, load_profile, reportlab_styles, check_glyphs, sha256
from pdf_tools import verify, package, write_json, render_review


class ToolkitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = load_profile()
        reportlab_styles(self.profile)
        self.guide = self.root / "guide.json"
        self.guide.write_text(json.dumps(["Alpha − 3", "Beta", "7", "19"]), encoding="utf-8")
        self.manifest = {"schema": 1, "profile_sha256": sha256(DEFAULT_PROFILE), "page_count": 1,
            "inputs": [{"path": "guide.json", "sha256": sha256(self.guide)}],
            "flow_order": ["first", "second", "a", "b"],
            "blocks": [
                {"id": "first", "kind": "text", "text": "Alpha − 3", "style": "body", "regions": [{"page": 1, "bbox": [36, 35, 380, 65]}]},
                {"id": "second", "kind": "text", "text": "Beta", "style": "body", "regions": [{"page": 1, "bbox": [36, 75, 380, 105]}]},
                {"id": "a", "kind": "table-cell", "table": "t", "row": 1, "column": 0, "text": "7", "regions": [{"page": 1, "bbox": [36, 115, 100, 145]}]},
                {"id": "b", "kind": "table-cell", "table": "t", "row": 1, "column": 1, "text": "19", "regions": [{"page": 1, "bbox": [110, 115, 200, 145]}]}
            ], "links": [{"page": 1, "target_page": 1, "bbox": [36, 35, 380, 65]}],
            "bookmarks": [[1, "Start", 1]]}

    def build(self, change=None):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.colors import HexColor
        pdf = self.root / "fixture.pdf"
        canvas = Canvas(str(pdf), pagesize=(432,576), initialFontName="Eink_regular")
        canvas.setFillColor(HexColor("#222222"))
        canvas.rect(0,0,432,576,fill=1,stroke=0)
        canvas.setFont("Eink_regular", 11.2)
        canvas.setFillColor(HexColor("#E6E6E6"))
        texts = ["Alpha − 3", "Beta", "7", "19"]
        if change == "case": texts[0] = "alpha − 3"
        if change == "minus": texts[0] = "Alpha - 3"
        if change == "swap": texts[2:] = ["19", "7"]
        if change == "reorder": texts[:2] = ["Beta", "Alpha − 3"]
        if change == "style": canvas.setFillColor(HexColor("#000000"))
        if change == "size": canvas.setFont("Eink_regular", 9)
        if change == "font": canvas.setFont("Eink_mono", 11.2)
        for i, (x, y) in enumerate([(36,526),(36,486),(36,446),(110,446)]):
            if change == "drop" and i == 1: continue
            canvas.drawString(x, y, texts[i])
        if change == "duplicate":
            canvas.drawString(36,526,texts[0])
        if change == "extra":
            canvas.drawString(36,300,"Unexpected hidden transcript")
        canvas.bookmarkPage("start")
        canvas.addOutlineEntry("Start", "start", 0)
        if change != "link":
            canvas.linkRect("", "start", (36,511,380,541), relative=0, thickness=0)
        canvas.save()
        manifest_path = self.root / "manifest.json"
        write_json(manifest_path, self.manifest)
        return pdf, manifest_path

    def test_valid_content_fonts_styles_and_navigation(self):
        pdf, manifest = self.build()
        report = verify(pdf, manifest)
        self.assertTrue(report["ok"], report["errors"])

    def test_corruptions_fail(self):
        for change in ["drop", "duplicate", "extra", "swap", "reorder", "case", "minus", "style", "size", "font", "link"]:
            with self.subTest(change=change):
                pdf, manifest = self.build(change)
                self.assertFalse(verify(pdf, manifest)["ok"], change)

    def test_mapped_order_cannot_silently_follow_reordered_guide(self):
        pdf, manifest = self.build("reorder")
        self.manifest["blocks"][0]["regions"], self.manifest["blocks"][1]["regions"] = self.manifest["blocks"][1]["regions"], self.manifest["blocks"][0]["regions"]
        write_json(manifest, self.manifest)
        report = verify(pdf, manifest)
        self.assertIn("Source block/cell order differs from mapped reading order", report["errors"])

    def test_missing_script_font_fails_before_rendering(self):
        from reportlab.platypus import Paragraph
        paragraph = Paragraph("日本語", reportlab_styles(self.profile)["body"])
        with self.assertRaisesRegex(ValueError, "Missing glyphs"):
            check_glyphs(paragraph)

    def test_stale_source_rejected(self):
        pdf, manifest = self.build()
        self.guide.write_text("changed", encoding="utf-8")
        self.assertFalse(verify(pdf, manifest)["ok"])

    def test_page_images_and_package_exact_bytes(self):
        pdf, manifest = self.build()
        review_dir = self.root / "pages"
        render_review(pdf, review_dir, dpi=72)
        self.assertTrue((review_dir / "page-0001.png").exists())
        self.assertTrue((review_dir / "contact-001.png").exists())
        review = self.root / "review.json"
        # This is a synthetic test record, not a claim that an agent inspected a paper.
        write_json(review, {"pdf_sha256": sha256(pdf), "pages_reviewed": [1], "unresolved": [], "notes": "Synthetic unit-test fixture"})
        output = self.root / "delivery.zip"
        package(pdf, manifest, review, output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read(pdf.name), pdf.read_bytes())
        with self.assertRaisesRegex(ValueError, "already exists"):
            package(pdf, manifest, review, output)

    def test_stale_or_incomplete_visual_review_rejected(self):
        pdf, manifest = self.build()
        review = self.root / "review.json"
        for data in [
            {"pdf_sha256": "stale", "pages_reviewed": [1], "unresolved": [], "notes": "Synthetic"},
            {"pdf_sha256": sha256(pdf), "pages_reviewed": [], "unresolved": [], "notes": "Synthetic"},
            {"pdf_sha256": sha256(pdf), "pages_reviewed": [1], "unresolved": ["clipped text"], "notes": "Synthetic"}]:
            write_json(review, data)
            with self.assertRaisesRegex(ValueError, "Visual review"):
                package(pdf, manifest, review, self.root / "no.zip")

    def test_damaged_pdf_cannot_be_packaged(self):
        pdf, manifest = self.build("drop")
        review = self.root / "review.json"
        write_json(review, {"pdf_sha256": sha256(pdf), "pages_reviewed": [1], "unresolved": [], "notes": "Synthetic"})
        with self.assertRaisesRegex(ValueError, "Automated checks failed"):
            package(pdf, manifest, review, self.root / "no.zip")


if __name__ == "__main__":
    unittest.main()
