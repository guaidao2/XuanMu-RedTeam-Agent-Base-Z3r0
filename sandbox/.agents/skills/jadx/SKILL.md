---
name: jadx
description: Android APK decompiler for converting DEX bytecode to readable Java source with the jadx CLI. Use for APK decompilation, app logic review, vulnerability discovery, hardcoded credential checks, API endpoint discovery, and Android reverse engineering.
---

# Jadx CLI

Use `jadx` to decompile Android APK, DEX, AAR, and JAR inputs into readable Java source and decoded resources. Prefer CLI output that can be searched, scripted, and archived.

## Prerequisites

- `jadx` must be installed and available in `PATH`.
- Java runtime must be available.
- Output directories need write permission.
- Decompiled output can be several times larger than the input APK.

## Core Commands

```bash
# Standard decompilation
jadx app.apk -d app-jadx

# Recommended for obfuscated production apps
jadx --deobf app.apk -d app-jadx

# Faster code-only pass
jadx --no-res --deobf app.apk -d app-code

# Resources-only pass
jadx --no-src app.apk -d app-resources

# Preserve partially decompiled methods when errors occur
jadx --show-bad-code app.apk -d app-jadx

# Fallback mode for difficult inputs
jadx --fallback --show-bad-code app.apk -d app-jadx
```

## Output Layout

```text
app-jadx/
├── sources/                 # Decompiled Java source
│   └── com/example/app/
└── resources/               # Decoded Android resources
    ├── AndroidManifest.xml
    ├── res/
    └── assets/
```

Start analysis from `resources/AndroidManifest.xml`, then inspect entry points and security-sensitive packages under `sources/`.

## Recommended Workflow

```bash
apk=app.apk
out=app-jadx

jadx --deobf --show-bad-code "$apk" -d "$out"

# Entry points and components
grep -r "extends Activity\|extends AppCompatActivity\|extends Application\|extends Service\|extends BroadcastReceiver" "$out/sources/"

# URLs and API declarations
grep -rE 'https?://[^"'"'"']+' "$out/sources/" "$out/resources/"
grep -r "@GET\|@POST\|@PUT\|@DELETE\|@PATCH\|baseUrl\|BASE_URL\|API_URL" "$out/sources/"

# Secrets and credentials
grep -ri "api.*key\|apikey\|secret\|password\|passwd\|token\|bearer" "$out/sources/" "$out/resources/"

# Crypto, storage, WebView, TLS handling
grep -r "Cipher.getInstance\|MessageDigest\|DES\|MD5\|SHA1\|SecureRandom" "$out/sources/"
grep -r "SharedPreferences\|SQLite\|openFileOutput\|MODE_WORLD_READABLE\|MODE_WORLD_WRITABLE" "$out/sources/"
grep -r "setJavaScriptEnabled.*true\|addJavascriptInterface\|WebView.*loadUrl" "$out/sources/"
grep -r "TrustManager\|HostnameVerifier\|CertificatePinner\|checkServerTrusted" "$out/sources/"
```

## Common Analysis Tasks

### API Endpoint Discovery

```bash
jadx --deobf app.apk -d app-jadx

find app-jadx/sources \
  -name '*Api*.java' -o \
  -name '*Service*.java' -o \
  -name '*Client*.java'

grep -r "@GET\|@POST\|@PUT\|@DELETE\|@PATCH" app-jadx/sources/ | sort -u
grep -r "baseUrl\|BASE_URL\|API_BASE\|API_URL" app-jadx/sources/ app-jadx/resources/ | sort -u
```

### Credential Check

```bash
jadx --no-res --deobf app.apk -d app-code

grep -ri "api.*key\|apikey\|client.*secret\|secret.*key" app-code/sources/
grep -ri "username.*password\|user.*pass\|password\|passwd\|pwd" app-code/sources/
grep -ri "token\|jwt\|bearer\|authorization" app-code/sources/
```

### IoT Companion App Review

```bash
jadx --deobf iot.apk -d iot-jadx

grep -rE 'https?://[^"'"'"']+' iot-jadx/sources/ iot-jadx/resources/ | grep -vi "google\|android\|facebook"
grep -ri "discover\|scan\|broadcast\|mdns\|udp\|mqtt\|coap\|onvif" iot-jadx/sources/
grep -ri "Authorization\|apiKey\|token\|login\|authenticate" iot-jadx/sources/
grep -r "CertificatePinner\|TrustManager\|HostnameVerifier" iot-jadx/sources/
```

### Batch Processing

```bash
for apk in *.apk; do
  name=$(basename "$apk" .apk)
  out="jadx-$name"
  jadx --no-res --deobf "$apk" -d "$out"
  grep -ri "api.*key\|password\|secret\|token\|baseUrl" "$out/sources/" > "findings-$name.txt" || true
done
```

## Useful Options

- `--deobf`: rename obfuscated classes and members where possible.
- `--deobf-use-sourcename`: use source file names as deobfuscation hints.
- `--show-bad-code`: emit partial code for methods jadx cannot cleanly decompile.
- `--fallback`: use fallback decompilation when normal output fails.
- `--no-res`: skip resources for faster source-only analysis.
- `--no-src`: decode resources without Java source output.
- `--export-gradle`: export a Gradle project layout.
- `-j <threads>`: set decompilation thread count.
- `-Xmx<size>`: set Java heap size, for example `-Xmx4096m`.

## Troubleshooting

```bash
# Obfuscated names make code hard to follow
jadx --deobf --deobf-use-sourcename app.apk -d app-jadx

# Decompiler errors hide important logic
jadx --show-bad-code --fallback app.apk -d app-jadx

# Large APK is slow
jadx --no-res -j 8 app.apk -d app-code

# Out of memory
jadx -Xmx4096m app.apk -d app-jadx

# Need build-like project structure
jadx --export-gradle app.apk -d app-project
```

## Reporting Findings

When reporting results, include:

- APK name and hash if available.
- jadx command used.
- Relevant file paths under `sources/` or `resources/`.
- Exact constants, URLs, method names, or component names found.
- Why the finding matters and what evidence supports it.
