# Explanation

Use this reference while writing or reviewing the editable guide. Its checks compare the guide's meaning with the paper; rendering checks are in the PDF production reference.

## Organize around understanding

Begin with research provenance and a short numbered overview of the problem, proposed mechanism, main evidence, and limitations. Organize the rest to reduce prerequisite burden while keeping coverage traceable. A useful progression is:

1. A reading map between the guide and original sections.
2. Foundations introduced where the method needs them.
3. A walkthrough of the method's inputs, state, operations, and outputs.
4. Experiments, comparisons, ablations, and limitations.
5. Appendix explanations, integrated earlier or given dedicated sections.
6. Practical interpretation, reproduction gaps, glossary, source issues, and references.

Use compact front matter: provenance, a one-sentence idea, a few bullets describing the assumed starting knowledge, the numbered overview, and a reading map. Generate the map’s guide-page ranges only after pagination settles. A separate decorative cover is optional.

Adapt this structure to the paper. Expand reasoning where the reader needs an intermediate step; use page count as a consequence of coverage and legibility. For RL, establish policy, observation, action, environment, trajectory, reward, and advantage before using them in a training objective.

## Make the reasoning explicit

Give each paragraph or list item one main idea and explain how adjacent ideas connect. Use numbered steps for procedures and bullets for parallel ideas. Turn dense inline sequences into separate steps, and split paragraphs that combine several claims or operations. Introduce jargon and acronyms before use, and keep terminology consistent.

For each major mechanism, establish its purpose and inputs, walk through its operations, and interpret its output. Follow one small running example through related operations where it helps: show what each step receives, what it changes, and why that change matters. Supply worked answers rather than exercises the reader must solve to follow the explanation.

Present a worked example's inputs and assumptions, intermediate calculations, and interpretation as distinct parts. Use the smallest example that exposes the mechanism; state invented choices locally. Keep explanations connected so the reader can follow the reasoning without reconstructing missing links between bullet points.

## Separate evidence from teaching

Label these categories at the relevant passage, example, or table:

| Label | Meaning |
| --- | --- |
| Reported | The paper's setup, definition, result, or claim, with a source pointer |
| Teaching example | Invented numbers or scenarios used to explain a mechanism |
| Engineering interpretation | Added inference, recommendation, or implementation choice |

Preserve assumptions, uncertainty, scope, and comparison conditions at the point of use, including in the opening overview and final takeaways. Attribute reported results to the paper's revision and evaluation date. Distinguish measured evidence from the authors' interpretation, and both from the guide's advice.

Describe absent information as unreported. Missing seeds or repetition counts do not establish that each experiment used a single run. Keep plausible mechanisms labeled as interpretations: a connector being small relative to the whole model, for example, does not rule out its increased capacity as a contributor to an observed gain.

For algorithms and prompts, preserve the behavioral contract: state, control flow, stopping conditions, verification rules, and any exact syntax on which behavior depends. Explain what pseudocode leaves unspecified.

For proofs and derivations, state assumptions and the claim, explain intermediate reasoning, and connect the result to its purpose. Give less central details an appendix treatment rather than silently dropping their conditions.

## Equations

For each key equation:

1. Explain the quantity it computes or behavior it encourages.
2. Show readable mathematical notation and define every symbol, operator, index, distribution, and constant; add units or dimensions where relevant.
3. State what is fixed, learned, sampled, averaged, or conditioned on.
4. Work through intermediate values in a small numerical example, or use a symbolic/concrete scenario when numbers would obscure the idea.
5. Interpret the result and explain a relevant assumption or edge case.

Map simplified notation explicitly to the original and keep distinct quantities distinct. Explain the purpose and assumptions of every other numbered equation in the coverage map, even when it does not need a full worked example. Repeat notation reminders after long gaps.

Record conventions that affect the answer: sum versus mean, population versus sample standard deviation, smoothing, rounding, and denominator membership. Identify an unspecified convention as a source limitation; label any chosen value as a teaching or engineering choice. Verify arithmetic using [Derived quantities and consistency](#derived-quantities-and-consistency).

When explaining probability ratios and clipping objectives, cover both signs of advantage where relevant and distinguish an objective's clipped incentive from a hard probability constraint. For equal-reward groups, distinguish the missing group-relative signal from updates due to other loss terms.

## Figures, tables, and references

Give every original figure and panel a destination, original identifier, source location, and explanation of how to read it. Explain what it supports and what it cannot establish. Mark any added teaching diagram as a simplified explanation. Asset extraction and display rules live in the PDF production reference.

Include every substantive table, preserving all cells, row/column associations, units, uncertainties, footnotes, and meaningful emphasis. Check transcribed numbers against the source. A new comparison or selected-results table is additional teaching material, not a substitute for the complete original data.

For image-and-dialogue examples, retain the original image asset and transcribe the dialogue exactly, including speaker labels, meaningful formatting, errors, and behavior-sensitive syntax. Explain the example separately. Each representation should help the reader: use a facsimile for visual evidence, a transcript for legible exact text, and commentary for interpretation. Put lengthy supporting transcripts in a linked appendix within the same PDF, with return links; keep text needed to understand the immediate claim nearby. Do not remove content to meet a page-count target.

Before a dense results table, explain the comparison, metrics, and reading direction. After it, identify the important changes and what they imply. For cumulative experiments, add a compact table of differences when it makes the steps easier to compare; retain the original results and identify the baseline for each difference. Explain that sequential additions measure changes along that particular sequence, not each intervention's isolated effect in every setting.

Preserve the full bibliography and keep in-text citations traceable to its entries. Retain substantive acknowledgements, disclosures, and appendix details in appropriate locations. Generated bibliography back-reference lists identifying pages that cite an entry may be omitted with disclosure. Keep citation identifiers, publication page ranges and substantive reference text. Exact original wording is necessary for quotations and behavior-sensitive prompt/code fragments; other prose may be explained and reorganized.

## Results and practical interpretation

For each main experiment, establish its question, task/dataset, protocol, baselines, what changes between methods, metric, denominator, direction of improvement, and result. Explain the strength and limits of the inference.

- Distinguish percentage points from relative improvement, and pass rate from reward or similarity.
- Preserve whether averages are over tasks, seeds, runs, or tokens. Distinguish decoding variability from independent training runs.
- Keep trainable, stored, and active parameters distinct. Separate rollout count, tokens, wall time, and total compute; include other costs when the source reports them.
- Explain what transfer crosses: environments, tasks, domains, or random seeds.
- Record missing reproduction details. Label proposed defaults as engineering choices.

When text, figures, or tables disagree, show both values and their source locations. Preserve the discrepancy instead of silently selecting a preferred value.

## Derived quantities and consistency

Calculate derived quantities in code and retain their source inputs, formula, units, comparison configuration, and rounding convention with the guide's working checks. Reuse these checked values wherever the same calculation appears. For every multiplier, make the numerator, denominator, and model variant explicit. For a claimed range, verify both endpoints against the stated baseline.

Reconcile the overview, worked examples, table commentary, and conclusions. Check comparative wording such as "largest improvement", "best", and "on all benchmarks" against the actual results and the stated comparison set. When prose conflicts with a table, carry the discrepancy through summaries instead of repeating the disputed attribution as a settled conclusion. Recheck all affected occurrences when a calculation or interpretation changes.

## Review before rendering

### Fidelity and consistency

Reconcile the coverage map against the actual guide, including appendices, panels, table data, and bibliography. Check key equations and conditions against the source; verify arithmetic, units, and denominators. Confirm that added examples and advice are labeled locally, source pointers resolve, and every unresolved source issue is visible.

Record which items were checked and which remain limited by the source. A sampled comparison supports claims about that sample; it does not establish complete semantic fidelity.

### Pedagogy

Review each major section from the intended reader's starting knowledge:

- Are prerequisites and unfamiliar terms explained before use?
- Can the reader follow each mechanism from inputs through intermediate operations to its result without opening the source to fill a reasoning gap?
- Do procedures appear as separate, connected steps, and does each paragraph have one main point?
- Does each worked example clarify the mechanism with explicit assumptions and intermediate values?
- Can the reader tell what the evidence establishes and where interpretation begins?

Expand missing reasoning steps, simplify examples that introduce unnecessary complexity, and remove repeated background or full-length restatements of caveats. Retain brief local qualifiers where they affect a claim's meaning. Record the sections reviewed and any remaining source-imposed limits after fixing the teaching gaps. Let length follow the explanation's needs; adding pages or bullet points alone does not satisfy this review.
