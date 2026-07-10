---
name: dns-whois
description: Use dig, nslookup, whois, and related local CLIs for authorized DNS, WHOIS, ASN, mail, nameserver, and ownership triage.
---

# dns-whois

Use local DNS and WHOIS tools for authorized domain, host, nameserver, mail, address, ASN, registration, and ownership triage.

## Help First

Before constructing commands, use installed help or version output as the source of truth:

```sh
dig -h
nslookup -help
whois --help
```

## Usage Rules

- Work only on in-scope domains, hosts, networks, or user-provided indicators.
- Record the exact queried identifier and query time when results support a finding.
- Prefer targeted record lookups over broad enumeration.
- Treat WHOIS, DNS, and registry data as time-sensitive intelligence that may be stale, proxied, incomplete, or privacy-protected.
- Cross-check important ownership, delegation, and resolution claims with independent DNS records or supporting evidence.
- Save large query batches and raw outputs to files rather than streaming them into the conversation.

## Output

Report the queried identifier, command used, relevant records or ownership signals, confidence, time sensitivity, output paths, and any unresolved or conflicting evidence.
