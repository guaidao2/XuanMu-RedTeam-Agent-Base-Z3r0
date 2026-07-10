---
name: mitre-attack-cryptography-review-methodology
description: ATT&CK-centered cryptography review methodology for credential access, stealth, defense impairment, collection, exfiltration, and impact reasoning.
---

# MITRE ATT&CK Cryptography Review Methodology

## Purpose

- Use ATT&CK to describe the adversary relevance of cryptographic weakness, not to overstate exploitability.
- Separate cryptographic goal failure from adversary behavior mapping.

## Review Flow

1. Confirm objective, scope, authorization basis, system boundary, data sensitivity, analysis boundaries, disclosure constraints, cleanup duties, and stop conditions.
2. Build a cryptographic asset model covering protected data, trust boundaries, threat actors, secrets, keys, certificates, tokens, primitives, protocols, storage, rotation paths, and failure modes.
3. Separate cryptographic goals: confidentiality, integrity, authenticity, freshness, non-repudiation, unlinkability, forward secrecy, key separation, misuse resistance, and recovery.
4. Inventory design choices and settings by primitive family, mode, integrity protection, uniqueness rule, derivation setting, randomness source, dependency assumption, and protocol version.
5. Trace key lifecycle from creation, derivation, exchange, wrapping, storage, access control, use context, rotation, revocation, backup, destruction, and incident recovery.
6. Convert observations into hypotheses with suspected misuse or weakness, precondition, expected signal, disproof condition, exploitability limit, and risk note.

## ATT&CK Mapping Rules

- Map credential access when weakness can expose or weaken authentication material.
- Map stealth when weakness can hide behavior or reduce observability.
- Map defense impairment when weakness can degrade protective capability.
- Map collection when weakness can expose protected data for gathering.
- Map exfiltration when weakness can support data movement across a boundary.
- Map command and control when protocol weakness can support unauthorized remote direction.
- Map impact when weakness can degrade integrity, availability, trust, or operational value.
- Avoid technique or sub-technique specificity unless cryptographic evidence supports that behavior.

## Evidence Rules

- For protocols, reason across state, authentication binding, transcript integrity, replay resistance, downgrade resistance, channel binding, identity validation, and error behavior.
- Separate design weakness, implementation defect, unsafe setting, dependency limitation, side-channel risk, theoretical cryptanalysis, practical exploitability, and ATT&CK behavior relevance.
- Report cryptographic goal affected, adversary behavior relevance, primitive or protocol context, root cause, evidence, exploit conditions, impact, limitations, remediation guidance, confidence, and verification steps.
