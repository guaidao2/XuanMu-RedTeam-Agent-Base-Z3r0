---
name: mitre-attack-adversary-validation-methodology
description: ATT&CK-centered adversary validation methodology for scoped tactics, techniques, proof, cleanup, and reporting.
---

# MITRE ATT&CK Adversary Validation Methodology

## Purpose

- Use ATT&CK tactics to express adversary objective and techniques to classify validated behavior.
- Do not use ATT&CK as an execution recipe. The matrix describes behavior; validation still requires scope, evidence, reversibility, and risk control.

## Validation Flow

1. Confirm objective, scope, permitted behavior, identity context, data handling, impact limits, cleanup duties, and stop conditions.
2. Convert each lead into a hypothesis with entry condition, precondition, weakness class, expected signal, privilege context, objective, disproof condition, and risk note.
3. Select the relevant tactic area before choosing a technique label.
4. Establish baseline behavior before testing deviations.
5. Validate one variable at a time with minimal, reversible, observable action.
6. Promote a lead only after observed behavior matches the hypothesis and the scope basis is clear.

## Tactic Use

- Initial Access covers behavior that establishes an entry condition.
- Execution covers behavior that causes controlled activity to run.
- Persistence covers behavior that maintains future access.
- Privilege Escalation covers behavior that changes authority level.
- Stealth covers behavior that hides activity from observation.
- Defense Impairment covers behavior that weakens or disables protective capability.
- Credential Access covers behavior that obtains or abuses authentication material.
- Discovery covers behavior that learns environment, identity, or relationship state.
- Lateral Movement covers behavior that moves across trust boundaries.
- Collection covers behavior that gathers target data.
- Command and Control covers behavior that enables remote direction.
- Exfiltration covers behavior that removes data from its boundary.
- Impact covers behavior that degrades, manipulates, or denies value.

## Mapping Rules

- Map to a tactic when the adversary objective is clear.
- Map to a technique when the observed behavior matches the behavior class.
- Map to a sub-technique only when evidence supports the narrower distinction.
- Do not map a vulnerability class directly to a technique without behavior evidence.
- Avoid chaining until each link is confirmed, scoped, and separately justified.

## Proof and Reporting

- Prove capability with least-sensitive evidence, minimum state change, bounded execution, clear timestamps, and reproducible observations.
- Preserve stability by bounding intensity, breadth, duration, persistence, and state-changing behavior.
- Classify outcomes as negative, informational, suspected, confirmed, blocked, duplicate, out of scope, or deferred.
- Keep exploitability, impact, confidence, detection sensitivity, and cleanup status separate.
- Report each validated chain with scope basis, ATT&CK mapping, hypothesis, method class, evidence, observed effect, privilege context, impact, root cause, cleanup status, confidence, and verification guidance.
