---
name: sqlmap
description: Use for authorized SQL injection testing with the sqlmap CLI, including detection, DBMS fingerprinting, request replay, and extraction checks against in-scope web targets.
---

# Sqlmap

Use `sqlmap` only for authorized, in-scope SQL injection testing. Keep targets, parameters, request files, and risk level aligned with the task.

## Help First

Before constructing or explaining a `sqlmap` command, execute the installed CLI help command and use that raw output as the source of truth:

```sh
sqlmap --help
```

Use `sqlmap -hh` when advanced options are needed. Derive options, syntax, tamper script usage, output flags, and request replay behavior from the current installed help output.

## Common Inputs

- URL with a clear injectable parameter.
- Raw HTTP request file captured from the target workflow.
- Cookie, header, proxy, or authentication context required to reproduce the request.
- Explicit scope limits, such as target host, path, parameter, or database action.

## Output

- Report target scope, command used, tested parameter, injection result, DBMS fingerprint, and relevant findings.
- Include output paths when sqlmap writes session data or result files.
- Avoid broad extraction unless it is explicitly requested and in scope.
