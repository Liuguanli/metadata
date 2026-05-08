# R1 Author Response and Action Tracker

## Weakness Tracker
1. CMU-C1: Threat model too permissive.
- Status: Open
- Planned fix: Add minimum secure deployment profile with explicit required controls and out-of-scope bypasses.
- Target section: Open Challenges and Roadmap -> Threat Model and Trust Assumptions.
- Diff evidence: Pending.

2. MIT-C1: Missing explicit architectural invariants.
- Status: Open
- Planned fix: Add 4 invariants plus one non-goals paragraph.
- Target section: MetaMirror Architecture (new subsection).
- Diff evidence: Pending.

3. UCB-C1: Benchmark/workload taxonomy not explicit enough.
- Status: Open
- Planned fix: Add workload schema and run-card protocol table, include task counts and risk levels.
- Target section: Preliminary Evaluation.
- Diff evidence: Pending.

4. CMU-M2: Baseline comparability underspecified.
- Status: Open
- Planned fix: Add baseline configuration paragraph (permission envelope, approval policy, tool surface).
- Target section: Preliminary Evaluation -> Baselines.
- Diff evidence: Pending.

5. UCB-M2: Reproducibility auditability incomplete.
- Status: Open
- Planned fix: Add artifact reporting checklist (seed, policy profile ID, generated artifact hash summary).
- Target section: Preliminary Evaluation -> Reproducibility Protocol.
- Diff evidence: Pending.

## Immediate Edit Bundle for R2
1. Add subsection: `Design Invariants and Non-Goals`.
2. Add table: `Minimum Secure Deployment Profile`.
3. Add table: `Workload Schema and Run-Card Fields`.
4. Update baselines with configuration fairness details.
5. Update utility metrics to report metadata-only vs escalation-required split.

## Pass Criteria for R2
- At least 3 of 5 top items marked `Mitigated` with concrete line-level diff evidence.
- No page overflow and no table-column overlap.
