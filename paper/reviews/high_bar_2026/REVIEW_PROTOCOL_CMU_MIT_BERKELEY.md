# MetaMirror High-Bar Review Protocol (CMU / MIT / UC Berkeley)

## Reviewer Roles
- Reviewer A (CMU Systems): aggressive on systems realism, failure modes, and evaluation discipline.
- Reviewer B (MIT Architecture): aggressive on conceptual novelty, principled abstractions, and generality.
- Reviewer C (UC Berkeley Data Systems): aggressive on data-management framing, reproducibility, and benchmark quality.
- Meta Reviewer: merges conflicts, sets acceptance gate, and decides whether another revision round is mandatory.

## Required Output Per Round
Each round must generate five files:
1. `Rk-reviewer-A-CMU.md`
2. `Rk-reviewer-B-MIT.md`
3. `Rk-reviewer-C-UCB.md`
4. `Rk-meta.md`
5. `Rk-author-response.md`

Each reviewer file must contain:
- `Weaknesses` only (no fluff), with severity (`Critical`/`Major`/`Minor`)
- `Detailed Evaluation` with evidence and concrete failure hypotheses
- Scoring table (1-5) over 8 dimensions
- Recommendation (`Reject`/`Weak Reject`/`Weak Accept`/`Accept`)

Author-response file must contain:
- one-to-one response for every weakness
- status for each weakness: `Open` / `Mitigated` / `Closed`
- concrete manuscript diff evidence with file/line anchors

## Scoring Dimensions (1-5)
1. Novelty of Vision
2. Technical Plausibility
3. Evidence Quality
4. Clarity and Structure
5. Reproducibility
6. Risk and Threat Analysis
7. VLDB Track Fit
8. Overall Recommendation Score

## Hard Gates (Fail Any = Round Failed)
1. Any `Critical` weakness left `Open`.
2. Any reviewer Overall < 3.5 after revisions.
3. More than one reviewer gives `Reject`/`Weak Reject`.
4. Missing diff evidence for claimed fixes.
5. Format non-compliance (page overflow, table overflow, broken references).

## Round Roadmap (Reset)
- R1: Problem-Claim Audit (scope, falsifiability, contribution boundary)
- R2: Novelty Attack (closest-work stress comparison)
- R3: Architecture Stress (threat model and bypass analysis)
- R4: Evidence Diversity (safety/utility/overhead/robustness/transfer/ablation)
- R5: Reproducibility (seeds/manifests/cleanup determinism)
- R6: Writing and Figure Clarity (intro, flow, visuals, readability)
- R7: Adversarial PC Simulation (hard committee conversation)
- R8: Acceptance Gate (final pass/fail for submission readiness)

## Success Target
- Final target: three `Accept` decisions from the simulated committee with no unresolved critical weakness.
