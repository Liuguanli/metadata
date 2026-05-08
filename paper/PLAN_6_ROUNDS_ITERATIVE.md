# Iterative Plan: 6 Rounds x N Cycles (VLDB Vision)

This plan is designed for continuous code-paper co-evolution.
Each round can be repeated multiple cycles until you approve quality.

## Global Rule (Every Cycle)

For each cycle, we must produce:
1. Code update in this repository.
2. Experiment rerun (with fixed seed and reproducibility manifest).
3. Figure sync to Overleaf figures directory and paper update.
4. Reader + Reviewer + Meta-Reviewer record.
5. Your personal review before moving to next cycle/round.

## Section Template (Following the Demo Style)

Target manuscript should stay within 7-8 top-level sections.
Current preferred 8-section template:

1. Introduction
2. Problem Model and Design Principles
3. Related Work
4. MetaMirror Architecture
5. Proof-of-Concept Implementation
6. Preliminary Evaluation
7. Open Challenges and Roadmap
8. Conclusion

## Round 1: Thesis and Vision Story

Goal:
- Lock one-sentence problem, one-sentence solution, one-sentence novelty.

Exit criteria:
- Abstract + Introduction can be restated clearly by Reader.
- Reviewer confirms novelty claim is explicit.

## Round 2: Architecture and Safety Model

Goal:
- Make architecture and control-plane framing precise and defensible.

Exit criteria:
- System boundaries and trust model are unambiguous.
- Reviewer has no major ambiguity on mechanism.

## Round 3: Positioning and Related Work

Goal:
- Clearly separate MetaMirror from existing agent safety, metadata, and RAG systems.

Exit criteria:
- Related-work comparison table is complete.
- Meta-reviewer marks novelty risk as controlled.

## Round 4: Preliminary Evidence (Vision-Style)

Goal:
- Keep experiments minimal but convincing for feasibility and impact signals.

Exit criteria:
- Each major claim maps to one concrete evidence item.
- Figures are synced to Overleaf and referenced in text.

## Round 5: Limitations, Risks, and Future Agenda

Goal:
- Strengthen credibility with explicit boundaries and failure modes.

Exit criteria:
- Limitations section is concrete.
- Future agenda is measurable and testable.

## Round 6: Submission Polish

Goal:
- Converge to reviewer-ready quality (clarity, consistency, framing).

Exit criteria:
- No unresolved high-severity reviewer concerns.
- Full internal review passes with your approval.

## Self-Evolution Loop (How We Improve Across Cycles)

1. Use previous cycle's top reviewer concern as next cycle's primary objective.
2. Change only one major narrative axis per cycle to keep causality clear.
3. Keep seed/config fixed for comparability unless a change is intentional and logged.
4. Track improvement in:
   - clarity deltas (reader confusion points down),
   - risk deltas (major concerns down),
   - evidence deltas (claim-evidence links up).
5. Gate every cycle by your review before proceeding.
