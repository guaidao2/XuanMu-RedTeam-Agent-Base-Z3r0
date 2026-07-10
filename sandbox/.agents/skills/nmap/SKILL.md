---
name: nmap
description: Use for authorized host discovery, port scanning, service/version detection, NSE script checks, network inventory, and local network diagnostics with the nmap CLI.
---

# Nmap

Use `nmap` for bounded, authorized network reconnaissance. Keep scan scope explicit, targeted, and matched to the task.

## Help First

Before constructing or explaining any `nmap` command, execute the installed CLI help command and use that raw output as the source of truth:

```sh
nmap --help
```

Do not maintain option descriptions, scan recipes, or command examples in this skill. Derive options, syntax, output flags, and script usage from the current `nmap --help` output.

## Output

- Report target scope, command used, open ports, detected services, versions, and any script findings.
