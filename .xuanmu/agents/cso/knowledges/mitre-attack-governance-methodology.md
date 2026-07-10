---
name: mitre-attack-governance-methodology
description: ATT&CK-centered governance methodology for matrix scope, risk control, behavior coverage, evidence standards, and reporting.
---

# MITRE ATT&CK Governance Methodology

## Purpose

- Use ATT&CK as the shared language for adversary intent, behavior coverage, validation depth, operational risk, and defensive decision support.
- Treat tactics as the reason a behavior matters, techniques as observed behavior classes, sub-techniques as evidence-backed specificity, and procedures as case-specific implementation detail outside reusable knowledge.
- Use ATT&CK to organize decisions and reports; do not use matrix labels as proof.

## Governance Flow

1. Define objective, authorized scope, success criteria, risk tolerance, decision owner, reporting deadline, and stop conditions.
2. Translate the objective into relevant ATT&CK tactic areas, distinguishing discovery or validation from access expansion, persistence, stealth, defense impairment, lateral movement, exfiltration, and impact.
3. Assign each activity a risk tier based on expected state change, sensitive exposure, breadth, duration, stability risk, and defensive visibility.
4. Require stronger justification as work moves from understanding to validation, from validation to chaining, and from chaining to demonstrated impact.
5. Keep unknowns, assumptions, leads, suspected issues, confirmed findings, and demonstrated impact separate.

## Evidence Standard

- Every ATT&CK mapping must include observed behavior, evidence basis, confidence, limitation, scope basis, and decision relevance.
- A tactic mapping needs a clear adversary objective. A technique mapping needs observed behavior matching that class. A sub-technique mapping needs distinguishing evidence.
- Procedure-level detail belongs in case records or reports, not reusable methodology.
- Untested tactic areas are coverage gaps, not evidence of absence.

## Risk Control

- Pause or stop when authorization is unclear, scope is exceeded, stability changes, sensitive exposure is unnecessary, or value no longer justifies risk.
- Deconflict timing, identities, concurrent activity, monitoring expectations, response coordination, and cleanup responsibility.
- Separate technical validation from leadership judgment and remediation ownership.

## Reporting Shape

- Report objective, scope, ATT&CK coverage, evidence summary, confidence, limitations, risk narrative, remediation priority, validation status, gaps, and next action.
- Summarize coverage by tactic and technique only where evidence supports the mapping.
- Highlight residual uncertainty and explicit non-coverage.
