---
name: binwalk
description: Use binwalk for authorized firmware, binary blob, archive, filesystem, and embedded-content triage with bounded extraction and evidence handling.
---

# binwalk

Use `binwalk` for authorized triage of firmware images, binary blobs, packed artifacts, and files that may contain embedded filesystems or compressed content.

## Help First

Before constructing commands, run the installed help and use it as the source of truth:

```sh
binwalk --help
```

## Usage Rules

- Work only on explicitly provided artifacts in scope.
- Start with identification/listing before extraction.
- Extract only into a task-scoped output directory.
- Treat signatures and offsets as leads; verify extracted files with `file`, hashes, directory review, or follow-up analysis.
- Keep extraction bounded and avoid recursive or broad extraction unless the user explicitly asks and the artifact scope permits it.
- Do not execute extracted files.
- Save large listings, extraction logs, and recursive output to files rather than streaming them into the conversation.

## Output

Report the artifact path, command used, output directory, notable offsets or embedded content, extracted paths, and limitations such as failed extraction or unsupported formats.
