# Explanation

Use this reference while writing or reviewing the editable guide. Its checks compare the guide's meaning with the paper; rendering checks are in the PDF production reference.

## Organize around understanding

Choose the order that reduces prerequisite burden while keeping coverage traceable. A useful progression is:

1. Research provenance and a map between the guide and original sections.
2. The problem, proposed change, and main evidence in a small set of simple points.
3. Foundations introduced where the method needs them.
4. A walkthrough of the method's inputs, state, operations, and outputs.
5. Experiments, comparisons, ablations, and limitations.
6. Appendix explanations, integrated earlier or given dedicated sections.
7. Practical interpretation, reproduction gaps, glossary, source issues, and references.

Adapt this structure to the paper. Expand reasoning where the reader needs an intermediate step; use page count as a consequence of coverage and legibility. For RL, establish policy, observation, action, environment, trajectory, reward, and advantage before using them in a training objective.

Give each paragraph or list item one main idea and explain how adjacent ideas connect. Use numbered steps for sequences. Introduce jargon and acronyms before use, and keep terminology consistent. Carry a small running example through related concepts when it reduces repeated setup. Supply worked answers rather than exercises the reader must solve to follow the explanation.

## Separate evidence from teaching

Label these categories at the relevant passage, example, or table:

| Label | Meaning |
| --- | --- |
| Reported | The paper's setup, definition, result, or claim, with a source pointer |
| Teaching example | Invented numbers or scenarios used to explain a mechanism |
| Engineering interpretation | Added inference, recommendation, or implementation choice |

Preserve assumptions, uncertainty, scope, and comparison conditions. Attribute reported results to the paper's revision and evaluation date. Distinguish measured evidence from the authors' interpretation, and both from the guide's advice.

For each mechanism, explain the problem, inputs/outputs, sequence, reason it might help, and a concrete example. For algorithms and prompts, preserve the behavioral contract: state, control flow, stopping conditions, verification rules, and any exact syntax on which behavior depends. Explain what pseudocode leaves unspecified.

For proofs and derivations, state assumptions and the claim, explain intermediate reasoning, and connect the result to its purpose. Give less central details an appendix treatment rather than silently dropping their conditions.

## Equations

For each key equation:

1. Explain the quantity it computes or behavior it encourages.
2. Show readable mathematical notation and define every symbol, operator, index, distribution, and constant; add units or dimensions where relevant.
3. State what is fixed, learned, sampled, averaged, or conditioned on.
4. Give a small numerical example, or a symbolic/concrete scenario when numbers would obscure the idea.
5. Interpret the result and explain a relevant assumption or edge case.

Map simplified notation explicitly to the original and keep distinct quantities distinct. Explain the purpose and assumptions of every other numbered equation in the coverage map, even when it does not need a full worked example. Repeat notation reminders after long gaps.

Check example arithmetic in code. Record conventions that affect the answer: sum versus mean, population versus sample standard deviation, smoothing, rounding, and denominator membership. Identify an unspecified convention as a source limitation; label any chosen value as a teaching or engineering choice.

When explaining probability ratios and clipping objectives, cover both signs of advantage where relevant and distinguish an objective's clipped incentive from a hard probability constraint. For equal-reward groups, distinguish the missing group-relative signal from updates due to other loss terms.

## Figures, tables, and references

Give every original figure and panel a destination, original identifier, source location, and explanation of how to read it. Explain what it supports and what it cannot establish. Mark any added teaching diagram as a simplified explanation. Asset extraction and display rules live in the PDF production reference.

Include every substantive table, preserving all cells, row/column associations, units, uncertainties, footnotes, and meaningful emphasis. Check transcribed numbers against the source. A new comparison or selected-results table is additional teaching material, not a substitute for the complete original data.

Preserve the full bibliography and keep in-text citations traceable to its entries. Retain substantive acknowledgements, disclosures, and appendix details in appropriate locations. Exact original wording is necessary for quotations and behavior-sensitive prompt/code fragments; other prose may be explained and reorganized.

## Results and practical interpretation

For each main experiment, establish its question, task/dataset, protocol, baselines, what changes between methods, metric, denominator, direction of improvement, and result. Explain the strength and limits of the inference.

- Distinguish percentage points from relative improvement, and pass rate from reward or similarity.
- Preserve whether averages are over tasks, seeds, runs, or tokens. Distinguish decoding variability from independent training runs.
- Keep trainable, stored, and active parameters distinct. Separate rollout count, tokens, wall time, and total compute; include other costs when the source reports them.
- Explain what transfer crosses: environments, tasks, domains, or random seeds.
- Record missing reproduction details. Label proposed defaults as engineering choices.

When text, figures, or tables disagree, show both values and their source locations. Preserve the discrepancy instead of silently selecting a preferred value.

## Content checkpoint

Reconcile the coverage map against the actual guide, including appendices, panels, table data, and bibliography. Check key equations and conditions against the source; verify arithmetic, units, and denominators. Confirm that added examples and advice are labeled locally, source pointers resolve, and every unresolved source issue is visible.

Record which items were checked and which remain limited by the source. A sampled comparison supports claims about that sample; it does not establish complete semantic fidelity.
