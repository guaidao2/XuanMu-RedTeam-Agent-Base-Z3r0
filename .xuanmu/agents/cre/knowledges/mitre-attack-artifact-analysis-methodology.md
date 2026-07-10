---
name: mitre-attack-artifact-analysis-methodology
description: ATT&CK-centered artifact analysis methodology for behavior mapping, validation, exploitability assessment, and reporting.
---

# MITRE ATT&CK Artifact Analysis Methodology

## Purpose

- Use ATT&CK to classify recovered or observed behavior.
- Do not infer adversary behavior from artifact presence alone. Mapping requires behavior evidence, reachability, and context.

## Analysis Flow

1. Confirm objective, scope, authorization basis, artifact handling rules, analysis boundaries, environment constraints, sensitive-data limits, disclosure constraints, cleanup duties, and stop conditions.
2. Preserve artifact integrity through identity, provenance, version, format, platform assumptions, dependencies, protection indicators, timestamps, and chain-of-custody notes.
3. Build an artifact model from layout, privilege context, trust boundaries, exposed interfaces, input sources, persistent state, external behavior, and defensive controls.
4. Convert observations into hypotheses with component, expected behavior, precondition, analysis method class, observable signal, disproof condition, security relevance, and risk note.
5. Separate recovered representation, inferred behavior, reachable behavior, and validated behavior.

## ATT&CK Mapping Rules

- Map execution when behavior indicates controlled activity can run.
- Map persistence when behavior indicates future access or repeated influence can be maintained.
- Map privilege escalation when behavior indicates authority boundaries can change.
- Map stealth when behavior indicates hiding or reducing observability.
- Map defense impairment when behavior indicates weakening protective capability.
- Map credential access when behavior involves authentication material or identity proof.
- Map discovery when behavior learns environment, identity, relationship, or configuration state.
- Map collection, command and control, exfiltration, or impact only when recovered or observed behavior supports that objective.

## Evidence Rules

- Treat naming hints, embedded text, and recovered representations as leads until control flow, data flow, or behavior supports the finding.
- Separate reachability, triggerability, input control, control influence, privilege context, and impact.
- Avoid sub-technique specificity unless evidence distinguishes the narrower behavior.

## Output

- Report artifact identity, scope basis, ATT&CK behavior mapping, hypothesis, method class, recovered logic, evidence, trigger conditions, exploitability, limitations, cleanup status, confidence, and verification guidance.
