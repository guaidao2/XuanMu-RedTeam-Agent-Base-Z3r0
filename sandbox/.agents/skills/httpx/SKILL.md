---
name: httpx
description: Use ProjectDiscovery httpx for authorized HTTP probing, live host validation, response triage, and lightweight web fingerprint collection.
---

# httpx

Use ProjectDiscovery `httpx` for authorized HTTP probing of in-scope hosts and URLs. This is the ProjectDiscovery CLI, not the Python `httpx` library.

## Use When

- A domain, host, URL, or recon output list needs HTTP/HTTPS liveness validation.
- Results from DNS, `nmap`, or user-provided target lists need status code, title, redirect, header, TLS, or technology triage.
- A large target list needs normalized output before deeper browser review, fingerprinting, or vulnerability validation.

## Usage Rules

- Work only on explicitly authorized targets.
- Before constructing commands, run the installed help and use it as the source of truth:

```sh
httpx -help
```

- Prefer file or stdin input for target lists, and keep batches bounded.
- Prefer JSON output when results will be parsed with `jq` or consumed by another tool.
- Use silent/no-color output modes when piping to avoid mixing progress text with data.
- Save large outputs to files rather than streaming them into the conversation.
- Treat detected technologies, titles, redirects, and TLS observations as triage signals; validate important claims with response evidence, browser inspection, `observer_ward`, or targeted follow-up.
- Do not use update, cloud/dashboard upload, screenshot, headless browser, or high-concurrency modes unless the user explicitly asks and the scope permits it.
