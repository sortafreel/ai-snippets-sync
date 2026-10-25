# PDF production

Use this reference when building or validating the PDF. The input is the checked editable guide and its assets. The rendering stage preserves that guide's content while adapting presentation.

## Reading profile

These are the user's established defaults. Newer instructions override the affected settings.

| Setting | Default |
| --- | --- |
| Device | 10-inch colour e-ink, portrait |
| Page | 432 × 576 pt (6 × 8 inches) |
| Side margins | 36 pt each, including room for stylus notes |
| Body text | About 11.2 pt with 15.8 pt leading |
| Typeface | Embedded, legible fonts covering all required glyphs |
| Background, including margins | Charcoal `#222222` |
| Ordinary text | Light grey `#E6E6E6` |
| Decorative rules | Grey `#A5A5A5`, where colour carries no meaning |
| Figures | Original colours, transparency, and visual backing, often a white panel |
| Numbering | Continuous final guide pages, consistent with viewer navigation; original source pages labeled separately |
| Delivery | ZIP containing the verified PDF |

The dark palette is a personal preference. Check readability at the intended display size and in grayscale; this does not substitute for an on-device test. Give newly authored meaning text labels or patterns as well as colour.

## Compose from the guide

Choose an available renderer that handles the paper's mathematics and pagination reliably. For example, use a document renderer with math support, or ReportLab for prose with PyMuPDF for source-region placement and Poppler for an independent render. Discover installed tools before adding dependencies. Keep the build reproducible from the saved guide, assets, fonts, and profile.

Use one column, comfortable paragraph spacing, and restrained hierarchy. Treat a heading and its opening text, an equation and its nearby definitions, and a figure and its caption/reading instructions as related layout units. Keep each together where practical; split long units at a meaningful boundary. Rebalance short continuations that otherwise occupy nearly empty pages. Use flow-based pagination; if positioning manually, measure blocks and enforce overflow checks.

Use a math-capable renderer to typeset verified notation with consistent mathematical fonts, fractions, indices, and alignment. Keep symbol definitions close to the equation and separate worked inputs, calculation steps, and interpretation visually. Check minus signs, Greek letters, operators, subscripts, and superscripts at the final reading size. When reliable typesetting of source notation is unavailable, preserve the original vector region and explain it nearby. Keep prose selectable and searchable.

Apply the profile through the renderer's styles. This pipeline authors the dark layout directly from structured content, so a separate neutral PDF and PDF-stream recolouring pass are unnecessary. If a neutral preview helps diagnosis, render it from the same guide and settings, changing only the palette.

Give substantive subsections, worked examples, and major tables stable navigation targets. Add descriptive bookmarks where they help the reader return to a concept or comparison; keep the opening contents concise. Rebuild contents, bookmarks, cross-references, and any page-count language after pagination settles. Keep the original-paper references separate from guide navigation. Use actual final page numbers rather than retaining an earlier edition's footers.

## Preserve scientific assets

Determine figure boundaries from rendered pages, including vector paths, legends, axes, annotations, and every panel. Raster image extraction alone may miss most of a diagram. Prefer complete vector regions or original raster assets. A high-resolution crop, usually 250–300 DPI or higher, is a fallback when faithful vector placement is unavailable; inspect it at final size.

Preserve aspect ratio, colours, labels, internal geometry, transparency, and backing. Crop only outside the content boundary. If a figure is too wide, use a dedicated page or clearly labeled enlarged panels while preserving every panel and its context. Use an original-layout facsimile when a safe reconstruction is unavailable, and state any remaining legibility limit. Research evidence must come from the original assets; generated illustrations are appropriate only for separately labeled teaching diagrams.

Keep protected artwork on its original backing when its colours or transparency would change on charcoal. Apply dark styles to ordinary guide text and decoration; preserve meaningful colour in tables, equations, and code. Source scans may need light panels. Verify OCR against the scan before using it as editable content.

For tables, split at logical row boundaries or into labeled column groups with stable row identities. Choose groups around the comparisons the reader needs, keeping compared values together where practical. Repeat headers across page breaks and preserve cell/header associations, notes, and meaningful emphasis. Move or split oversized material rather than shrinking it below a comfortable reading size. Record repeated navigation headers as intentional duplicates.

When placing a clipped source region, ensure the output contains only the intended region's content. Clipping or covering old material may leave invisible selectable text. Use isolated assets or sanitized placements and verify both rendering and extraction.

## Output checks

Record results in the task's checks file and update final destinations in the coverage map.

### Guide content and navigation

- Compare ordered guide blocks with extracted PDF text, accounting for deliberate navigation repeats. Normalize only verified layout whitespace and line-wrap changes; preserve signs, punctuation, accents, ligatures, and symbol distinctions.
- Inspect reading order, missing text, duplicated or hidden text, stale references, and placeholder content. Character counts alone cannot establish correct order or completeness.
- Check every table cell's value and row/column association, including units and notes. Verify code tokens, indentation, and line breaks when code is included.
- Check all equations visually against the checked notation. PDF text extraction cannot establish mathematical equivalence.
- Confirm font embedding and glyph coverage, contents links, bookmarks, page labels, and original-source pointers. Investigate extraction-order anomalies before altering visibly correct mathematics.

### Artwork fidelity

- Account for every figure and panel against the asset inventory. Compare placed artwork with its source at the same effective scale and region.
- For original raster assets, compare decoded pixels, dimensions, masks, and colour handling; lossless re-encoding may change file bytes. For vector regions, check geometry, embedded text, and rendered appearance.
- For rasterized fallbacks, compare the source-region render to the placed result and record the rasterization. Inspect labels at final size.
- Repeat anomalous image comparisons using fresh document handles and symmetric rendering conditions before diagnosing changed artwork; renderer caches can affect comparisons.

### Visual inspection

Render every final page. Use contact sheets for an overview, then inspect each page at readable resolution, with closer checks of equations, tables, code, and multi-panel figures. Check clipping, overlap, orphan headings, missing glyphs, tiny labels, blurred assets, excessive whitespace, and unintended blank pages.

Inspect every authored text style against its actual background: body text, headings, captions, table headers/cells, callouts, equations, links, and footers. Include bold and italic variants and styles used on both dark and light panels. Verify legibility in grayscale and at the intended display size; inherited styles can leave black caption text on charcoal even when ordinary prose is correct. Preserve original scientific artwork's colours and backing when fixing authored styles.

Check that page breaks preserve the relationships defined under composition. Keep credits and source-page pointers with substantive content, and rebalance pages containing only attribution or a short stranded continuation. Preserve intentional full-page artwork and useful whitespace rather than maximizing page fill.

Fix failures in the guide, asset preparation, or renderer. Rebuild cleanly and rerun the affected checks, including later pages when pagination changes. A clean screenshot does not establish clean selectable text; both checks are required.
