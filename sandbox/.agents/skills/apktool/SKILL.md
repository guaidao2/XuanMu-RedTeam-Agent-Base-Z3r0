---
name: apktool
description: Use apktool for authorized Android APK resource decoding, manifest review, smali inspection, rebuild checks, and static mobile artifact triage.
---

# apktool

Use `apktool` for authorized Android APK resource decoding and smali-level inspection when Java decompilation alone is insufficient.

## Help First

Before constructing commands, run the installed help and use it as the source of truth:

```sh
apktool --help
```

## Usage Rules

- Work only on explicitly provided APKs or artifacts in scope.
- Prefer decoding into a task-scoped output directory.
- Preserve the original artifact; never modify it in place.
- Treat decoded resources, manifests, smali, certificates, and configuration values as static evidence, not proof of runtime exploitability.
- Save large decoded outputs and grep results to files rather than streaming them into the conversation.
- Do not rebuild, sign, patch, or modify an APK unless the user explicitly asks and the scope permits it.
- Use `jadx` when readable Java/Kotlin-like source is needed; use `apktool` when manifest, resources, smali, or packaging fidelity matters.

## Output

Report the APK path, command used, output directory, relevant manifest/resource/smali paths, and any findings or blockers that affect analysis.
