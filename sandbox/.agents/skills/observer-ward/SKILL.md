---
name: observer-ward
description: Use observer_ward for authorized web application and service fingerprint identification against in-scope HTTP targets.
---

# observer_ward

Use `observer_ward` for authorized service and web application fingerprint identification. It is useful for identifying exposed applications, middleware, services, versions, CPE-style product context, and fingerprints from community probe data.

Skill name is `observer-ward`; the installed CLI command is `observer_ward`.

## Use When

- The task needs web application or service fingerprinting for in-scope targets.
- Reconnaissance output from DNS, browser review, HTTP probing, or user-provided URLs needs product or technology identification.
- A target list needs lightweight fingerprint triage before deeper validation.
- A finding needs supporting evidence such as matched product name, version, status, title, certificate data, request/response data, or matched probe output.

## Usage Rules

- Work only on explicitly authorized targets.
- Before constructing commands, run the installed help and use it as the source of truth:

```sh
observer_ward --help
```

- Use `-t` / `--target` for one or more explicit targets, `-l` / `--list` for a file with one target per line, or stdin for pipeline input.
- Keep target sets bounded. For large lists, write results to a file with `-o` / `--output`.
- Prefer machine-readable output with `--format json` when downstream parsing with `jq` or later evidence review is needed.
- Use `--silent` when piping results to other tools so progress logs do not mix with structured output.
- Use `--ir` for request/response evidence and `--ic` for certificate evidence only when that detail is needed; both can increase output size.
- Treat fingerprints as leads. Cross-check important product or version matches with headers, page content, certificates, browser output, or another tool before reporting them as confirmed.
- Use `--debug` only for troubleshooting or evidence collection because it can expose request/response details and increase output volume.
- Do not run update, plugin, daemon, MITM, webhook, API server, MCP, or Redis/asynq modes unless the user explicitly asks for that workflow and the scope permits it.
