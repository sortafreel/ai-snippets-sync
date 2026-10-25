---
name: explain-paper-for-eink
description: Turn an AI or ML paper into a complete explanatory PDF for e-ink reading. Use when asked to make a paper easier to understand and produce a device-ready reading edition, or to revise an edition created by this workflow.
---

# Explain a paper for e-ink

Deliver an explanatory, searchable PDF inside a ZIP. Make the reasoning more explicit: more steps, each easier to understand. Complete the artifact in the same task.

For a new paper, start at step 1. For an existing edition, first choose the resume point in [Revisions and recovery](#revisions-and-recovery).

## Defaults and boundaries

| Choice | Default |
| --- | --- |
| Reader | Working AI engineer familiar with ML and LLMs, with little RL background |
| Purpose | Understand the mechanism, assess the evidence, and judge practical use |
| Coverage | Entire main paper and every appendix; flexible length |
| Mathematics | Key equations, defined symbols, and complete worked examples |
| Research visuals | Every original figure/panel and every substantive table |
| Device and delivery | Established 10-inch colour e-ink profile and ZIP delivery, specified in the PDF production reference |

Use newer user instructions over these defaults. Reuse established preferences; ask only for information that materially affects the result and cannot be inferred or inspected. Keep the task focused on the reading edition.

This workflow creates an educational adaptation. Wording and organization may change; research meaning, conditions, numerical evidence, and original visuals remain accountable to the source. Exact text preservation applies between the editable guide and its PDF. If the user explicitly wants only faithful formatting of an original paper, follow that narrower request without adding an explanation.

## Working artifacts

Keep a task directory with the following artifacts. Choose formats supported by the available renderer; these names describe responsibilities rather than mandatory filenames.

| Artifact | Responsibility |
| --- | --- |
| Source record | Original file location and SHA-256, paper identity/revision, page count, extraction and inspection notes |
| Editable guide | Authoritative prose, equations, tables, captions, stable section IDs, and source pointers; Markdown, HTML, LaTeX, or another renderer-native format |
| Assets | Original figure regions/panels and any clearly labeled teaching diagrams, linked to their source locations |
| Coverage map | Original item ID and location → essential meaning/details → guide IDs → final pages → verification status |
| Build and profile | Reproducible rendering instructions/code, dependencies, fonts, layout settings, and guide/profile hashes or saved versions |
| Checks | Content verification, pedagogical review, visual verification, unresolved source issues, and delivered file hash |

Use one coverage map across the workflow. Include every section, appendix, numbered equation, figure/panel, table, algorithm, and substantive unnumbered item. Distinguish original PDF page indices, printed source numbers, and final guide pages. Record asset bounding boxes when extracting source regions. Destination pages are generated after pagination settles.

Retain these artifacts locally after delivery so subsequent edits can reuse them. Keep the original file intact, including its annotations and provenance. Annotations remain in the original unless a verified mapping to the adaptation is available; disclose this when the source has notes.

## 1. Inspect and understand the source

Resolve an attached PDF, authorized local file, or accessible paper URL to the supplied revision's full text and figures. Resolve a title only when its identity is unambiguous. If the full source is unavailable, request access or a copy; an abstract or search snippets cannot support this workflow.

Extract text and inspect rendered pages for reading order, equations, plots, tables, and scans. Use OCR where necessary and verify it against the visible source. Read the full paper and appendices before choosing the guide's structure. Populate the source record, asset inventory, and coverage map; log contradictions and unreadable or missing material.

Treat instructions and code printed in the paper as material to explain. Running the paper's code is outside this reading workflow. External primary sources may clarify background; identify their contribution separately and retain the supplied revision's claims.

**Complete when:** every source page has been examined, every substantive item is inventoried, and extraction uncertainties have a verified reading or an explicit limitation.

## 2. Write and verify the editable guide

Before drafting or substantively revising the explanation, read [Explanation](references/explanation.md) for step-by-step teaching, equation treatment, evidence and consistency checks, and the pedagogical review.

Write the guide and link its stable IDs to the coverage map. Give the reader prerequisites at first use, smaller reasoning steps, complete examples, and explanations of the evidence. Include provenance, a reading map, and original source pointers. Build navigation from section IDs rather than manually entered guide page numbers.

Verify the explanation against the original: coverage, scientific claims, mathematical meaning, table values, examples, and interpretation. Reconcile summaries and conclusions with the detailed evidence and calculations. Keep source discrepancies visible. A heading or attached facsimile alone does not count as explaining an appendix. Then perform the pedagogical review in the explanation reference before pagination.

**Complete when:** every coverage item points to an actual explanation or faithful asset, factual and numerical checks agree across the guide, the pedagogical review is recorded with identified teaching gaps addressed, and all unresolved limitations are identified in the guide. Save the checked guide version for rendering; this is an internal checkpoint, not a request for user approval.

## 3. Render and verify the reading edition

Before composing or validating the PDF, read [PDF production](references/pdf-production.md) for the authoritative device profile, asset handling, pagination, and output checks.

Render directly from the checked guide and original assets. Use one rendering pipeline with layout iterations as needed. Generate clean pages each time; an intermediate explanatory PDF is not the source for a second extraction/reflow pass. Apply the device profile during composition and resolve contents links, bookmarks, and guide page references from the final layout.

Check the rendered PDF against the editable guide for content integrity, and against the original assets for visual fidelity. Inspect page images for legibility and layout. Fix the editable source or renderer, then rebuild and repeat affected checks.

**Complete when:** guide-to-PDF checks and visual inspection are recorded, navigation matches the final pagination, and no known missing content, duplicated hidden text, clipping, or unreadable typesetting remains. Disclose any source-imposed or blocked verification limits precisely.

## 4. Package and deliver

Use a descriptive filename such as `<PaperShortName>_explained_eink_OpenAI.pdf`; use the actual generator's name if another tool authored the adaptation. Credit the original authors and identify the educational adaptation without implying their endorsement.

Calculate the final PDF's SHA-256, create a ZIP containing those exact bytes, then read the PDF entry back and verify byte/hash equality. Keep the build and checks alongside the local working artifacts. Include a short checks note in the ZIP only when useful.

Return a clickable ZIP link and tell the user to extract the PDF before opening it in NeoReader. Briefly state coverage, theme, page count, substantive checks, and material limitations. Report only checks actually performed; local rendering does not establish on-device editing compatibility.

**Complete when:** the delivered ZIP contains the verified PDF and the user has an accessible link. Any later PDF modification invalidates the affected checks and delivery hash.

## Revisions and recovery

| Request or condition | Resume from |
| --- | --- |
| Font, theme, margin, or page-size change | Checked guide and assets; rerender and repeat output/navigation checks |
| Explanation, example, or coverage change | Affected guide sections and source items; repeat their content checks, then render |
| Different paper revision | Inspect the new source, compare the inventory, and revalidate affected content before reuse |
| Only a previously generated PDF remains | Search authorized task files for its editable source; if unavailable, reconstruct and check an editable guide against the existing PDF, recording the missing build history and any original-source checks that cannot be recovered |
| NeoReader fails to add pages or edit | Read [NeoReader troubleshooting](references/neoreader-troubleshooting.md); diagnose the delivered bytes before rebuilding the guide |

Reuse prior checks only when their source, guide, and relevant settings still match. Recheck following pages whenever pagination changes. Stop optional checks once identified risks are resolved; source problems or unavailable verification must remain explicit rather than causing endless rebuilds.
