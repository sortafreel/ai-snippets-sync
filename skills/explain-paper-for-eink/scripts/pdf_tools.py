"""Verify a PDF against source-derived regions, render review sheets, package checked bytes."""
import argparse
import difflib
import hashlib
import json
import re
import zipfile
from pathlib import Path

from reading_profile import DEFAULT_PROFILE, load_profile, sha256


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalized(text):
    # No case folding, Unicode normalization, punctuation deletion or dehyphenation.
    return " ".join(text.split())


def in_box(point, box):
    x, y = point
    return box[0] <= x < box[2] and box[1] <= y < box[3]


def first_difference(expected, actual):
    for op, a, b, c, d in difflib.SequenceMatcher(None, expected, actual, autojunk=False).get_opcodes():
        if op != "equal":
            return {"operation": op, "expected": expected[max(0, a-35):b+35], "actual": actual[max(0, c-35):d+35]}
    return None


def verify(pdf_path, manifest_path, profile_path=DEFAULT_PROFILE):
    import pymupdf
    pdf_path, manifest_path, profile_path = map(Path, (pdf_path, manifest_path, profile_path))
    manifest, profile = read_json(manifest_path), load_profile(profile_path)
    errors, notes = [], []
    if manifest.get("schema") != 1 or not manifest.get("blocks"):
        raise ValueError("Manifest needs schema: 1 and nonempty source-derived blocks")
    if manifest.get("profile_sha256") != sha256(profile_path):
        errors.append("Profile hash differs from manifest")
    inputs = manifest.get("inputs", [])
    if not inputs:
        errors.append("Manifest must bind its authoritative guide/build inputs by hash")
    for item in inputs:
        path = manifest_path.parent / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            errors.append(f"Input changed or missing: {item['path']}")
    blocks = manifest["blocks"]
    ids = [b["id"] for b in blocks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate block IDs; intentional repeats need separate IDs")
    flow_order = manifest.get("flow_order", [])
    flow_blocks = {b["id"]: b for b in blocks if b.get("kind") != "navigation" and not b.get("repeat_of")}
    if len(flow_order) != len(set(flow_order)) or set(flow_order) != set(flow_blocks):
        raise ValueError("flow_order must list each source block/cell once; omit navigation and declared repeats")
    regions = []
    for b in blocks:
        if not b.get("regions") or not isinstance(b.get("text"), str):
            raise ValueError(f"Missing expected text or regions: {b['id']}")
        positions = [(r["page"], r["bbox"][1], r["bbox"][0]) for r in b["regions"]]
        if positions != sorted(positions):
            raise ValueError(f"Unordered fragments: {b['id']}")
        if b.get("repeat_of"):
            original = next((other for other in blocks if other["id"] == b["repeat_of"]), None)
            if original is None or original["text"] != b["text"]:
                raise ValueError(f"Invalid intentional repeat: {b['id']}")
        if b.get("kind") == "table-cell" and not all(k in b for k in ("table", "row", "column")):
            raise ValueError(f"Cell lacks table/row/column identity: {b['id']}")
        for r in b["regions"]:
            regions.append({**r, "block": b, "lines": [], "chars": []})
    exclusions = manifest.get("exclusions", [])
    for e in exclusions:
        if not e.get("reason") or e.get("kind") not in {"artwork", "math"}:
            raise ValueError("Only original artwork or visually checked math may be excluded, with a reason")
    with pymupdf.open(pdf_path) as doc:
        if manifest.get("page_count") != len(doc):
            errors.append("Page count differs from manifest")
        for r in [*regions, *exclusions]:
            box = r["bbox"]
            if (not isinstance(r["page"], int) or not 1 <= r["page"] <= len(doc)
                    or len(box) != 4 or box[0] >= box[2] or box[1] >= box[3]
                    or box[0] < 0 or box[1] < 0
                    or box[2] > profile["page_pt"][0] or box[3] > profile["page_pt"][1]):
                raise ValueError(f"Invalid page/rectangle: {r['page']} {box}")
        fonts, links = set(), []
        for pno, page in enumerate(doc, 1):
            if page.rotation or any(abs(a-b) > .1 for a, b in zip((page.rect.width, page.rect.height), profile["page_pt"])):
                errors.append(f"Page {pno}: unexpected size or page rotation")
            active = [r for r in regions if r["page"] == pno]
            excluded = [r for r in exclusions if r["page"] == pno]
            unclaimed = []
            raw = page.get_text("rawdict", sort=False)
            for block in raw["blocks"]:
                for line in block.get("lines", []):
                    line_chars = {id(r): [] for r in active}
                    for span in line["spans"]:
                        for ch in span["chars"]:
                            box = ch["bbox"]
                            point = ((box[0]+box[2])/2, (box[1]+box[3])/2)
                            hits = [r for r in active if in_box(point, r["bbox"])]
                            excluded_hits = [e for e in excluded if in_box(point, e["bbox"])]
                            if not ch["c"].isspace() and (box[0] < -.5 or box[1] < -.5 or box[2] > page.rect.width+.5 or box[3] > page.rect.height+.5):
                                errors.append(f"Page {pno}: off-page glyph {ch['c']!r}")
                            if len(hits) + len(excluded_hits) > 1 and not ch["c"].isspace():
                                errors.append(f"Page {pno}: overlapping regions at {point}")
                            if len(hits) == 1:
                                r = hits[0]
                                line_chars[id(r)].append(ch["c"])
                                r["chars"].append({"c": ch["c"], "font": span["font"], "size": span["size"], "color": span["color"]})
                            elif not excluded_hits and not ch["c"].isspace():
                                unclaimed.append(ch["c"])
                    for r in active:
                        if line_chars[id(r)]:
                            r["lines"].append("".join(line_chars[id(r)]))
            if unclaimed:
                errors.append(f"Page {pno}: unaccounted text (possibly extra/hidden): {''.join(unclaimed)[:160]}")
            for font in page.get_fonts(full=True):
                xref, ext, kind, name = font[:4]
                fonts.add((name, kind))
                if kind == "Type3":
                    notes.append(f"Page {pno}: Type 3 font {name}; inspect glyph rendering and extraction")
                elif not xref or not doc.extract_font(xref)[3]:
                    errors.append(f"Page {pno}: unembedded font {name}")
            for link in page.get_links():
                # PyMuPDF 1.26 represents resolved /Fit destinations as LINK_NAMED
                # with a 1-based page string; XYZ/GOTO destinations use 0-based ints.
                fit_page = link.get("page")
                resolved_fit = (link["kind"] == pymupdf.LINK_NAMED
                                and isinstance(fit_page, str) and fit_page.isdigit())
                if link["kind"] == pymupdf.LINK_GOTO or resolved_fit:
                    target = int(fit_page)-1 if resolved_fit else link.get("page", -1)
                    links.append({"page": pno, "target_page": target+1, "bbox": list(link["from"])})
                    if not 0 <= target < len(doc):
                        errors.append(f"Page {pno}: broken internal link")
                elif link["kind"] in {pymupdf.LINK_NAMED, pymupdf.LINK_NONE}:
                    errors.append(f"Page {pno}: unresolved link; resolve or inspect explicitly")
            for needed in [n for n in manifest.get("links", []) if n["page"] == pno]:
                found = any(l["page"] == pno and l["target_page"] == needed["target_page"]
                            and max(abs(a-b) for a, b in zip(l["bbox"], needed["bbox"])) < 2 for l in links)
                if not found:
                    errors.append(f"Page {pno}: expected link missing or wrong target")
        toc = doc.get_toc()
        for entry in toc:
            if not 1 <= entry[2] <= len(doc):
                errors.append(f"Invalid bookmark target: {entry}")
        if "bookmarks" in manifest and manifest["bookmarks"] != toc:
            errors.append("Bookmarks differ from expected titles/order/pages")
        page_count = len(doc)
    checked = []
    physical_order = sorted(flow_order, key=lambda ident: (
        flow_blocks[ident]["regions"][0]["page"],
        round(flow_blocks[ident]["regions"][0]["bbox"][1], 1),
        flow_blocks[ident]["regions"][0]["bbox"][0]))
    if physical_order != flow_order:
        errors.append("Source block/cell order differs from mapped reading order")
    for b in blocks:
        rs = [r for r in regions if r["block"] is b]
        actual = "\n".join("\n".join(r["lines"]) for r in rs)
        # A verified local extraction replacement must name the exact affected block.
        for replacement in b.get("extraction_fixes", []):
            if not replacement.get("reason") or not replacement.get("from"):
                raise ValueError(f"Undocumented extraction fix: {b['id']}")
            if replacement["from"] not in actual:
                errors.append(f"{b['id']}: stale extraction fix")
            actual = actual.replace(replacement["from"], replacement["to"])
        if b.get("kind") == "code":
            expected, observed = b["text"].strip("\n"), actual.strip("\n")
        else:
            expected, observed = normalized(b["text"]), normalized(actual)
        difference = first_difference(expected, observed)
        if difference:
            errors.append({"block": b["id"], "text_difference": difference})
        if b.get("style"):
            spec = profile["styles"][b["style"]]
            color = int(profile["colors"][b.get("color", spec["color"])].lstrip("#"), 16)
            allowed_fonts = b.get("fonts", [Path(profile["fonts"][spec["font"]]).stem])
            def font_key(s):
                return re.sub(r"[^a-z0-9]", "", s.split("+")[-1].lower())
            for ch in (ch for r in rs for ch in r["chars"] if not ch["c"].isspace()):
                if abs(ch["size"]-spec["size_pt"]) > .2 or ch["color"] != color or font_key(ch["font"]) not in {font_key(f) for f in allowed_fonts}:
                    errors.append(f"{b['id']}: font, size or color differs from profile")
                    break
        checked.append(b["id"])
    return {"schema": 1, "ok": not errors, "pdf_sha256": sha256(pdf_path),
            "manifest_sha256": sha256(manifest_path), "profile_sha256": sha256(profile_path),
            "page_count": page_count, "checked_blocks": checked,
            "fonts": sorted(fonts), "errors": errors, "notes": sorted(set(notes)),
            "exclusions": exclusions, "limits": "Checks mapped text, declared styles and navigation; visual/scientific/artwork review remains separate."}


def render_review(pdf_path, out_dir, dpi=140):
    import pymupdf
    from PIL import Image, ImageDraw
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    review_pages = []
    with pymupdf.open(pdf_path) as doc:
        sheet = None
        for index, page in enumerate(doc):
            if index % 12 == 0:
                sheet = Image.new("RGB", (3*240, 4*340), "white")
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            name = f"page-{index+1:04}.png"
            pix.save(out_dir / name)
            review_pages.append({"page": index+1, "file": name, "sha256": sha256(out_dir/name)})
            thumb = Image.open(out_dir / name).convert("RGB")
            thumb.thumbnail((228, 310))
            x, y = (index%3)*240, ((index%12)//3)*340
            sheet.paste(thumb, (x+6, y+22))
            ImageDraw.Draw(sheet).text((x+8, y+4), str(index+1), fill="black")
            if index % 12 == 11 or index == len(doc)-1:
                sheet.save(out_dir / f"contact-{index//12+1:03}.png")
    write_json(out_dir / "render-index.json", {"pdf_sha256": sha256(pdf_path), "dpi": dpi, "pages": review_pages})


def package(pdf_path, manifest_path, review_path, zip_path, profile_path=DEFAULT_PROFILE):
    # Recheck now: a saved green report alone is not authority for changed bytes.
    report = verify(pdf_path, manifest_path, profile_path)
    if not report["ok"]:
        raise ValueError(f"Automated checks failed: {report['errors'][:3]}")
    review = read_json(review_path)
    if (review.get("pdf_sha256") != report["pdf_sha256"] or review.get("unresolved") != []
            or sorted(set(review.get("pages_reviewed", []))) != list(range(1, report["page_count"]+1))
            or not review.get("notes")):
        raise ValueError("Visual review must cover every current page, document inspection and have no unresolved failures")
    pdf_path, zip_path = Path(pdf_path), Path(zip_path)
    if zip_path.exists():
        raise ValueError("Output ZIP already exists; choose a new delivery filename")
    pdf_bytes = pdf_path.read_bytes()
    if hashlib.sha256(pdf_bytes).hexdigest() != report["pdf_sha256"]:
        raise ValueError("PDF changed during packaging; recheck it")
    with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(pdf_path.name, pdf_bytes)
    with zipfile.ZipFile(zip_path) as archive:
        if archive.namelist() != [pdf_path.name] or archive.read(pdf_path.name) != pdf_bytes:
            raise ValueError("ZIP read-back mismatch")
    return {"pdf_sha256": report["pdf_sha256"], "zip_sha256": sha256(zip_path), "entry": pdf_path.name}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("pdf", type=Path)
    check.add_argument("manifest", type=Path)
    check.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    check.add_argument("--out", type=Path, required=True)
    render = sub.add_parser("render")
    render.add_argument("pdf", type=Path)
    render.add_argument("out_dir", type=Path)
    render.add_argument("--dpi", type=int, default=140)
    pack = sub.add_parser("package")
    for name in ("pdf", "manifest", "review", "zip"):
        pack.add_argument(name, type=Path)
    pack.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args()
    if args.command == "check":
        report = verify(args.pdf, args.manifest, args.profile)
        write_json(args.out, report)
        print(f"{'PASS' if report['ok'] else 'FAIL'}: {len(report['checked_blocks'])} blocks, {len(report['errors'])} failures")
        return 0 if report["ok"] else 1
    if args.command == "render":
        render_review(args.pdf, args.out_dir, args.dpi)
        return 0
    print(json.dumps(package(args.pdf, args.manifest, args.review, args.zip, args.profile), indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
