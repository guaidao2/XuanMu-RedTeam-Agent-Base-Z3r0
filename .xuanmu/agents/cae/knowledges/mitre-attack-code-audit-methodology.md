---
name: mitre-attack-code-audit-methodology
description: ATT&CK-centered code audit methodology for connecting code evidence, weakness classes, adversary behavior, and remediation verification.
---

# MITRE ATT&CK Code Audit Methodology

## Purpose

- Use ATT&CK to translate code-level weaknesses into plausible adversary behavior.
- Do not infer ATT&CK behavior from a pattern alone; require reachability, controllability, defective control, affected sink, and plausible impact.
- Use weakness and control frameworks for root cause and verification language; use ATT&CK for behavior relevance.

## Audit Flow

1. Define scope by code boundary, version basis, language family, execution model, trust boundaries, privileged operations, sensitive data, and deployment assumptions.
2. Build an attack-surface model from entry points, background flows, parsing boundaries, data ingestion, identity controls, authorization checks, persistence operations, and outbound trust relationships.
3. Trace data flow from untrusted sources to sensitive sinks through transformations, guards, trust boundaries, and error paths.
4. Identify the defective control and the affected security property.
5. Ask what adversary behavior the weakness could enable if reachable.
6. Map ATT&CK only after the code evidence supports the behavior.

## ATT&CK Reasoning

- Initial Access relevance requires code evidence that an external or boundary-crossing condition can establish entry.
- Persistence relevance requires code evidence that future access or repeated influence can be maintained.
- Privilege Escalation relevance requires code evidence that authority boundaries can change.
- Credential Access relevance requires code evidence involving authentication material or identity proof.
- Discovery relevance requires code evidence that environment, identity, relationship, or configuration state can be exposed.
- Collection or Exfiltration relevance requires code evidence that sensitive data can be gathered or moved across a boundary.
- Impact relevance requires code evidence that value, integrity, availability, or operational continuity can be degraded.

## Evidence Rules

- Map tactics to adversary objective and techniques to plausible behavior only after reachability is established.
- Avoid sub-technique specificity unless the code path supports that precision.
- Treat secret exposure as behavior-relevant only when context supports use, abuse, or disclosure.
- Keep root cause, exploitability, impact, and ATT&CK relevance separate.

## Remediation Review

- Verify corrected source and sink, regression coverage, sibling patterns, and whether the fix addresses root cause rather than a single symptom.
- Report vulnerable flow, ATT&CK behavior relevance, root cause, evidence, prerequisites, impact, confidence, remediation guidance, and verification steps.
