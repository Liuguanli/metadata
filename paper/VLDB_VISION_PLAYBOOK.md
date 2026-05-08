# VLDB Vision Playbook (MetaMirror)

This playbook defines how we continuously co-evolve code and paper for a VLDB Vision submission.

## Target Track Alignment

Primary fit:
- Metadata management
- Data discovery and search
- Data lakes and data governance

Secondary fit:
- Data management for ML/AI
- New data system infrastructures and tools for applied ML
- Data engineering and model management for ML
- Runtime strategies and data access in ML systems
- Embeddings and vector databases
- Data cleaning, data quality, and data preparation
- Schema matching and mapping
- Heterogeneous and federated DBMS

## Vision-Paper Standard (VLDB)

For each paper revision, ensure:
1. Novel architecture and principled direction are explicit.
2. High-impact motivation is concrete and urgent.
3. Claims are scoped as vision + preliminary evidence, not over-claimed as full validation.
4. Prototype evidence supports feasibility and value signals.
5. Future research agenda is specific and testable.

## Three Review Roles

### Reader

Goal: clarity, flow, and accessibility.

Checks:
- Problem statement is understandable in first 1-2 pages.
- Core idea is easy to restate in 2-3 sentences.
- Section transitions are natural.
- Figures/tables are interpretable without deep context.

Output:
- 3 strongest points
- 3 confusion points
- 3 edits for clarity

### Reviewer (Technical)

Goal: novelty, technical soundness, and evidence quality.

Checks:
- Novelty over related work is explicit and defensible.
- System model and threat/safety boundaries are precise.
- Evaluation claims match available evidence.
- Limitations and failure modes are acknowledged.
- Contribution-to-track fit is explicit.

Output:
- Major concerns
- Minor concerns
- Must-fix before submission

### Meta-Reviewer

Goal: decision quality and final prioritization.

Checks:
- Reader/Reviewer comments are synthesized into a ranked action list.
- High-risk gaps are identified (novelty risk, scope risk, evidence risk).
- Revision plan is realistic for next cycle.

Output:
- Decision: `accept-cycle` or `revise-again`
- Top 5 prioritized actions
- Final narrative framing for next revision

## One Iteration Cycle (Mandatory)

Each cycle must produce all 4 artifacts:
1. Code delta in this repository
2. Updated experiment outputs if claims changed
3. Overleaf updates in `/Users/guanlil1/Dropbox/应用/Overleaf/Metadata-management`
4. Review record in `paper/reviews/`

Cycle steps:
1. Pick one focused thesis improvement goal.
2. Implement code/experiment changes.
3. Update paper text/figures/tables in Overleaf workspace.
4. Run Reader review.
5. Run Reviewer review.
6. Run Meta-review synthesis.
7. Close cycle only when must-fix items are addressed or explicitly deferred.

## Upgraded Round Requirements (Strict)

For each round, the cycle file must include:
1. Three independent reviewer blocks (Reviewer A/B/C).
2. For each reviewer: `Strong Points`, `Weak Points`, `Detailed Evaluation`, and provisional decision.
3. A weakness-to-edit mapping table: each weakness must map to at least one concrete manuscript change.
4. A compact scorecard (Novelty, Soundness, Evidence, Clarity, Overall; 1-5 scale).
5. Explicit user-review gate: do not advance to next round until user approves.

Hard rule:
- Revision focus is weakness-driven. Strong points are recorded but edits must primarily target weak points.

## Vision Framing Guardrails

- Do not present the work as only an engineering wrapper.
- Emphasize architecture-level shift: metadata as control plane for agent-file interaction.
- Separate clearly:
  - What is demonstrated now (prototype + preliminary results)
  - What is projected (longer-term research agenda)
- Keep claims falsifiable and measurable.

## Definition of Done (Per Cycle)

A cycle is complete only if:
1. `paper/reviews/<cycle-id>.md` is filled.
2. Paper-impact log entry is appended in `paper/README.md`.
3. Open high-severity review items are either fixed or explicitly scheduled in `TASKS.md`.
