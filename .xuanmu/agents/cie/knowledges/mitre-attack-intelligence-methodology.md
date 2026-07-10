---
name: mitre-attack-intelligence-methodology
description: ATT&CK-centered intelligence methodology for reconnaissance and resource-development collection planning, source confidence, and validation handoff.
---

# MITRE ATT&CK Intelligence Methodology

## Purpose

- Use ATT&CK reconnaissance and resource-development tactics to structure collection planning, entity expansion, source evaluation, and validation handoff.
- Treat intelligence behavior as pre-validation activity. Do not claim compromise, exploitability, attribution, or business impact from indirect evidence alone.
- Use ATT&CK labels to describe collection behavior and adversary relevance, not to convert public information into confirmed findings.

## Collection Flow

1. Start with an intelligence requirement: decision supported, boundary, collection questions, confidence need, deadline, and acceptable collection risk.
2. Select ATT&CK reconnaissance or resource-development behavior categories that match the requirement.
3. Define expected entity types, relationship types, source classes, confidence threshold, and disproof conditions.
4. Collect and expand only through traceable evidence chains.
5. Convert observations into validation hypotheses only when the entity, relationship, exposure, and uncertainty are explicit.

## Entity Model

- Model identity, ownership, purpose, exposure, trust boundary, dependency, relationship, relevance, and confidence.
- Preserve source, observation time, observed value, relationship, rationale, and confidence for every expansion.
- Prefer smaller verified maps over broad inventories with weak provenance.
- Keep observed fact, source claim, inference, assumption, hypothesis, unknown, and evidence gap separate.

## ATT&CK Mapping Rules

- Map to reconnaissance when behavior concerns learning about a target.
- Map to resource development when behavior concerns preparing or acquiring resources before validation.
- Use technique labels only when evidence supports the behavior class.
- Use sub-technique labels only when the evidence distinguishes that narrower behavior.
- Do not use ATT&CK mapping to imply exploitability or access.

## Source Confidence

- Evaluate sources by proximity, freshness, authority, consistency, independence, bias, access constraint, and conflict with other evidence.
- Treat absence of evidence as a gap unless collection coverage and source limits justify a negative claim.
- Upgrade confidence only when independent evidence converges or a higher-proximity source confirms the relationship.

## Handoff Standard

- Hand off identifiers, evidence chain, confidence, ATT&CK behavior mapping, constraints, open gaps, validation question, expected signal, disproof condition, and risk note.
