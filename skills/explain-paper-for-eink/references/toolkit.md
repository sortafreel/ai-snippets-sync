# Python toolkit

Read this before the initial rendering trial or when connecting a renderer to the shared checks. The tools are portable Python; keep virtual environments and generated files in the paper’s task directory, outside the synced skill. They provide shared styles, a rendering trial, mapped-text checks, page images and ZIP verification. They do not perform the scientific or visual review.

## Environment and shared appearance

Use Python 3.11+ on macOS or Linux. Install [scripts/requirements.txt](../scripts/requirements.txt) in a task-local virtual environment; these are the tested direct dependencies. Save `pip freeze` or the equivalent resolved environment with the build. Existing compatible environments can be reused after the trial and regression tests. Do not copy a Linux virtual environment to macOS.

```sh
eink_skill="$HOME/.config/espanso/skills/explain-paper-for-eink"
python3 -m venv work/.venv
work/.venv/bin/python -B -m pip install -r "$eink_skill/scripts/requirements.txt"
work/.venv/bin/python -B "$eink_skill/scripts/test_toolkit.py" -v
work/.venv/bin/python -B "$eink_skill/scripts/probe.py" work/profile-trial
```

The [reading profile](../assets/reading-profile.json) is the single authority for font roles, sizes, leading, colors and page geometry. [Bundled fonts](../assets/fonts/manifest.json) have pinned hashes and an included redistribution license. Load the actual files; do not resolve them by an operating-system font name. Preserve the same base profile across papers unless the user changes it. Save a copy/hash of the profile and font manifest in each task; record intentional overrides separately.

For ReportLab, import `load_profile`, `reportlab_styles` and `check_glyphs` from [scripts/reading_profile.py](../scripts/reading_profile.py). Use these styles for every paragraph and table cell, including captions and references. Call `check_glyphs()` before layout. [scripts/probe.py](../scripts/probe.py) demonstrates full-page background, embedded fonts, table continuation and source-block tracking. It is a trial and integration example, not a complete paper-authoring engine.

For HTML renderers, generate CSS from the same tokens:

```sh
work/.venv/bin/python -B "$eink_skill/scripts/reading_profile.py" --css work/profile.css
```

Regenerate CSS after moving to another machine: its font URLs resolve to that machine’s skill location. Set print backgrounds and page footers in the chosen renderer; verify page-margin color in the trial. The adapter supplies styles, not browser invocation, math layout or a complete document template. Keep profile styles authoritative when adding renderer-specific CSS. A renderer change can alter line breaks even with identical fonts and sizes; retest pagination.

The base bundle covers ordinary Latin, Greek and Cyrillic text, not every writing system. A missing glyph is an explicit error. Add a licensed script-specific font, pin its bytes/hash, and preserve language-appropriate glyph forms. Do not reuse a previous paper’s CJK subset without checking coverage. To trial a UTF-8 source excerpt with an explicit TrueType font:

```sh
work/.venv/bin/python -B "$eink_skill/scripts/probe.py" work/script-trial \
  --sample-text work/source-excerpt.txt --sample-font work/fonts/script.ttf
```

Record any script font and math font companions with the profile and reuse them in later papers requiring the same script/engine. The base font assets must stay unchanged. The probe includes symbol checks, a long table and an SVG raster fallback; add a real fraction/indexed equation, the widest relevant table, difficult original artwork and all required scripts through the actual production renderer before treating the trial as sufficient.

## Connect a build to text verification

Export one manifest from the editable guide and the renderer’s placement records. Expected text and `flow_order` come from the guide **before layout**. Rectangles come from the final layout. Never populate expected text by reading back the PDF being checked. Hash the guide, profile, build code, assets and other relevant inputs. Export complete table cells in row-major order, with their table, row and column identities.

The checker uses 1-based PDF page numbers and rectangles in points from the unrotated page’s top-left corner. Every selectable character must belong to exactly one declared text region or a documented artwork/math exclusion. Give each block as much room as its glyphs need without overlapping neighboring blocks. A paragraph split across pages keeps one expected text and ordered regions. Use separate IDs with `repeat_of` for repeated table headers; footers and contents entries use `kind: "navigation"` and still need exact expected text. Do not ignore whole top/bottom bands.

Minimal manifest shape (replace these illustrative values with the real build’s values):

```json
{
  "schema": 1,
  "profile_sha256": "actual profile hash",
  "page_count": 1,
  "inputs": [{"path": "guide.json", "sha256": "actual guide hash"}],
  "flow_order": ["intro", "table1-r1c0"],
  "blocks": [
    {"id": "intro", "kind": "text", "text": "Source-derived expected prose.",
     "style": "body",
     "regions": [{"page": 1, "bbox": [36, 40, 396, 82]}]},
    {"id": "table1-r1c0", "kind": "table-cell", "table": "table1", "row": 1, "column": 0,
     "text": "13.2", "style": "table",
     "regions": [{"page": 1, "bbox": [36, 100, 120, 120]}]}
  ],
  "links": [],
  "bookmarks": [],
  "exclusions": []
}
```

Input paths resolve relative to the manifest; prefer relative paths for task portability. The probe uses absolute paths for its own temporary inputs. Link expectations have `page`, `target_page` and `bbox`; bookmarks are `[level, title, page]` entries. Include **all** expected links and bookmarks, derived from the guide’s navigation targets. Geometry checks alone cannot establish that a link points to the intended concept.

Set `style` on ordinary authored text so the checker compares its font, size and color against the profile. Mixed bold/italic spans may specify a `fonts` list of expected PDF font names; light-panel text uses `color: "light_text"`. A mathematical span with different script sizes needs visual checking and appropriate separate regions, rather than a body-font-size assertion. `kind: "code"` preserves line breaks and whitespace in the comparison; use actual spaces for indentation and inspect any extractor discrepancy.

For original artwork or complex math whose text extraction cannot be compared reliably, declare an exclusion with `page`, `bbox`, `kind` (`artwork` or `math`) and a specific `reason`. Those regions remain in the report as explicit limits and need separate fidelity/visual checks. An exclusion must not cover ordinary guide prose or table data. The helper does not compare decoded artwork pixels, establish equation equivalence or prove that a manually supplied manifest faithfully represents the guide; the agent must review those boundaries.

```sh
work/.venv/bin/python -B "$eink_skill/scripts/pdf_tools.py" check \
  work/final.pdf work/manifest.json --out work/checks.json
work/.venv/bin/python -B "$eink_skill/scripts/pdf_tools.py" render \
  work/final.pdf work/page-images
```

`check` exits nonzero on failure and reports the PDF/profile/manifest hashes, inspected blocks, fonts and exclusions. `render` writes every page, numbered contact sheets and a hash-bound image index. Inspect contact sheets for overall layout and every full page for content at reading size. An independent renderer such as Poppler is useful for suspected renderer-specific problems; it is not a required system dependency.

## Diagnose extraction mismatches

Whitespace collapse is the only automatic text normalization; code receives an exact line/space comparison. Case, punctuation, minus signs, accents and Unicode distinctions remain significant. The checker compares occurrences in their mapped regions, not whether a string occurs somewhere in the document.

| Symptom | Investigate before changing expected text |
| --- | --- |
| Header/footer in a split paragraph | Correct region bounds; declare navigation separately |
| Repeated table headers | Separate expected occurrences with `repeat_of` |
| Line-wrap hyphen or ligature mismatch | Compare the visible word and code points; correct only the affected block |
| CSS capitalization | Preserve source capitalization or explicitly author the intended transformed text |
| Joined table cells | Map each cell’s own rectangle and row/column, rather than searching a page-wide string |
| CJK broken by line breaks or radical code points | Verify visible glyphs and language; record local transcription/extraction corrections |
| Duplicate or scrambled math | Inspect hidden HTML/MathML output and visual notation; use an explicit math region if necessary |

A verified local extraction repair can be recorded on the affected block as `extraction_fixes: [{"from": "exact extracted sequence", "to": "verified sequence", "reason": "visible/source evidence"}]`. Keep the raw extraction. Do not lower-case globally, strip all whitespace, remove punctuation or apply global compatibility normalization to make a check pass. A stale local repair is reported as a failure. If evidence does not resolve the mismatch, report the limitation and retain the original region.

## Package verified bytes

After inspecting all final page images, save a visual-review record with `pdf_sha256`, `pages_reviewed` (all final page numbers), `unresolved` (an empty list only when failures are resolved), and `notes` describing the actual inspection and any disclosed source limits. Never generate a successful review record merely because rendering finished.

```sh
work/.venv/bin/python -B "$eink_skill/scripts/pdf_tools.py" package \
  work/final.pdf work/manifest.json work/visual-review.json work/delivery.zip
```

The helper reruns automated checks, requires a matching complete visual-review record, refuses to overwrite an existing ZIP and verifies the PDF bytes after ZIP read-back. It does not certify the agent’s visual judgment or on-device behavior. Keep the printed delivery hashes with the task’s checks.

## Reuse and maintenance

Copy useful pipeline components across papers after removing paper-specific paths, titles, crops, figure maps and numerical assertions. Keep infrastructure in this skill only when it is actually reusable; paper content stays with that paper. New checks must reject a deliberately corrupted fixture before becoming evidence for delivery. Run `test_toolkit.py` and the trial after changing helper behavior or dependency versions.

Keep renderer workarounds conditional. Browser margin backgrounds, SVG canvas cropping, MathML duplication and Type 3 font behavior must be confirmed with the relevant renderer/version. Record fixes with the build instead of imposing them on every future renderer.

Implementation references: [ReportLab paragraphs](https://docs.reportlab.com/reportlab/userguide/ch6_paragraphs/), [PyMuPDF page extraction and rendering](https://pymupdf.readthedocs.io/en/latest/page.html), and [DejaVu font license](https://dejavu-fonts.github.io/License.html).
