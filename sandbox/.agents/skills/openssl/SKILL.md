---
name: openssl
description: Use openssl for authorized TLS, certificate, key, CSR, digest, signature, encoding, and protocol-material inspection inside the sandbox.
---

# openssl

Use `openssl` for authorized inspection of TLS endpoints and cryptographic material such as certificates, chains, CSRs, public keys, digests, signatures, encodings, and protocol evidence.

## Help First

Before constructing commands, run the installed help and subcommand help as needed:

```sh
openssl help
openssl <subcommand> -help
```

## Usage Rules

- Work only on in-scope endpoints or provided cryptographic artifacts.
- Prefer inspection and verification over transformation.
- Do not generate, overwrite, export, or convert private key material unless the user explicitly requests it and the scope permits it.
- Do not paste private keys, secrets, full certificates with sensitive context, or long binary encodings into the conversation.
- Save certificates, chains, handshake transcripts, and decoded outputs to files when they are large or sensitive.
- Treat protocol and certificate observations as evidence for review; do not overstate cryptographic exploitability without separate validation.

## Output

Report the target or artifact, command used, key observations, relevant validity/issuer/subject/fingerprint details when applicable, output paths, and any verification errors.
