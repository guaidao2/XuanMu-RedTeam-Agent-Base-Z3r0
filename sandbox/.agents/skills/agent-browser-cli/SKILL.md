---
name: agent-browser-cli
description: Use agent-browser-cli to perceive and control the supervised Chromium browser inside the sandbox, interact with pages, capture screenshots/PDFs, inspect cookies/CDP/network/console state, and troubleshoot only when needed.
---

# agent-browser-cli

Use `agent-browser-cli` when a task requires browser perception, browser control, page interaction, screenshots, PDFs, cookies, Chrome DevTools Protocol, network logs, console logs, or browser troubleshooting.

`agent-browser-cli` controls the sandbox's supervised Chromium through a Rust daemon and the bundled Chrome extension bridge. The browser is launched by `supervisord` with profile data under `/data` and the extension loaded from `/opt/agent-browser/chrome-extension`. It is not Selenium or Playwright.

## Core Rules

Follow these rules strictly:

1. Start with the command closest to the user's goal.
2. Do not run health checks before normal browser work.
3. Treat a stopped daemon as normal until a goal command fails.
4. Use high-level commands before raw JavaScript, JSON, or CDP.
5. Use `scan` for page content.
6. Use `snapshot` for actionable element references.
7. Use `exec`, JSON commands, or CDP only as escape hatches.
8. Re-run `snapshot` after any page structure or content change before reusing `@e` references.
9. Never paste large base64 payloads, screenshots, PDFs, or huge response bodies into the conversation.
10. Write binary artifacts to files and report only paths, sizes, and essential metadata.
11. Do not change ports or perform configuration changes without explicit user confirmation.
12. Do not guess when a tab, profile, browser, label, or `@e` reference is ambiguous.

## Normal Startup Behavior

For ordinary browser tasks, run the target command directly. These commands auto-start the daemon when needed:

```bash
agent-browser-cli tabs
agent-browser-cli open https://example.com
agent-browser-cli scan --text-only
agent-browser-cli snapshot --limit 200
agent-browser-cli exec --tab <tabId> 'return document.title'
```

Do not run `status`, `doctor`, or `logs` first unless one of these is true:

- A target command failed.
- The command output explicitly reports a connection problem.
- The command output reports the extension is not connected.
- The command output reports a port mismatch.
- The command output reports there are no usable tabs.
- The user explicitly asked for troubleshooting.

If troubleshooting is justified, use this order:

```bash
agent-browser-cli status
agent-browser-cli doctor
agent-browser-cli logs --tail 100
```

`daemon_not_running` and `running=false` do not by themselves justify stopping browser work. Prefer a target command that can auto-start the daemon.

`doctor` only checks state. It does not auto-start the daemon or change configuration.

## Command Selection

Choose the smallest sufficient command:

```text
scan      Read page text, headings, lists, visible content, and general page state.
snapshot  Find clickable/fillable elements and create @e references.
exec      Run JavaScript when high-level commands are insufficient.
JSON/CDP  Handle cookies, cross-tab work, low-level browser control, or unsupported cases.
```

Preferred workflow:

1. Use `scan` or `scan --text-only` to understand content.
2. If a selector is obvious, use direct `click` or `fill` with that selector.
3. If a selector is not obvious or the page is complex, use `snapshot` and act on `@e` references.
4. After navigation, dynamic updates, filtering, form changes, or DOM mutation, run `snapshot` again before using `@e`.
5. Fall back to `exec`, JSON, or CDP only when high-level commands cannot express the action reliably.

Common commands:

```bash
agent-browser-cli tabs
agent-browser-cli tabtree
agent-browser-cli tabtree --full
agent-browser-cli tabtree --profile work
agent-browser-cli tabtree --tab <tabId>
agent-browser-cli lookup tab <tabId>
agent-browser-cli lookup browser <browser_id>
agent-browser-cli lookup profile work
agent-browser-cli tabs --profile work
agent-browser-cli open https://example.com
agent-browser-cli open --profile work https://example.com
agent-browser-cli open --window https://example.com
agent-browser-cli open --window --focus https://example.com
agent-browser-cli scan --tabs-only
agent-browser-cli scan --profile work --tab <tabId> --text-only
agent-browser-cli snapshot --limit 200
agent-browser-cli snapshot --offset 200 --limit 200
agent-browser-cli snapshot --details
agent-browser-cli click 'button[type=submit]'
agent-browser-cli click '@e1'
agent-browser-cli fill '@e2' 'hello'
agent-browser-cli fill '@e2' --clear
agent-browser-cli fill '@e2' ' world' --append
agent-browser-cli send-keys --target '@e2' 'Enter'
agent-browser-cli mouse-click '@e3'
agent-browser-cli close --tab <tabId>
agent-browser-cli exec --tab <tabId> 'return document.title'
```

After `open`, continue against `result.opened_tab_id` or `result.opened_session_key` when the command output provides them.

## Browser, Profile, Tab, and Element Identity

High-level actions support `--tab <tabId>`.

When multiple Chrome profiles or browser instances are present, commands may also support:

```bash
--profile <profile_id-or-label>
--browser <browser_id>
```

`tabs` output includes:

```text
browser_id
profile_id
profile_label
tab_id
session_key
```

Use `tabtree` to inspect browser -> profile -> tabs. It supports `--tab`, `--profile`, and `--browser` filters. Filtered output still preserves parent nodes.

Use `tabtree --full` when compact output omits full URLs or `session_key`.

Use lookup commands when identity is unclear:

```bash
agent-browser-cli lookup tab <tabId>
agent-browser-cli lookup browser <browser_id>
agent-browser-cli lookup profile <profile_id-or-label>
```

Profile labels:

```bash
agent-browser-cli profile-label set work --profile <profile_id>
agent-browser-cli profile-label clear --profile <profile_id>
```

Profile label constraints:

- Labels may contain only English letters, digits, `-`, `_`, and `.`.
- Labels are validated for uniqueness only within the current daemon.
- Popup labels are local conveniences and do not guarantee cross-profile uniqueness.
- If a label matches multiple profiles, stop and disambiguate with `--profile` or `--browser`.

`@e` references:

- Valid only in the current daemon.
- Valid only for the current `session_key`.
- Valid only for the most recent `snapshot`.
- Must use the explicit form `@e1`, `@e2`, etc.
- Must not be reused after page changes without a fresh `snapshot`.

If `--tab` alone is ambiguous, add `--profile` or `--browser`. Do not guess.

## Waiting and Monitoring

Keep waiting and monitoring separate.

Use `--wait-js` for slow page changes:

```bash
agent-browser-cli click '@e1' --wait-js 'return document.body.innerText.includes("Done")' --wait-timeout 10
```

Use `--monitor` only when before/after page diff information is useful:

```bash
agent-browser-cli click '@e1' --wait-js 'return document.body.innerText.includes("Done")' --wait-timeout 10 --monitor
```

`--monitor` is disabled by default.

Do not use fixed `setTimeout` sleeps inside scripts when `--wait-js` can express the condition.

## Alerts, Confirms, and Prompts

The extension does not permanently rewrite business-page `alert`, `confirm`, or `prompt`.

During a CLI page command, native dialogs may be temporarily suppressed and then restored. If native dialog behavior appears wrong, ask the user to reload the Chrome extension and the page before deeper troubleshooting.

## Ports and Configuration

Fixed API port:

```text
127.0.0.1:18767
```

Default extension WebSocket port:

```text
127.0.0.1:18765
```

Configuration file:

```text
~/.agent-browser-cli/config.json
```

Changing the extension port affects both the Chrome extension and the daemon connection. Before running this command, explain the impact and get explicit user confirmation:

```bash
agent-browser-cli set-extension-port <port>
```

This writes to `~/.agent-browser-cli/config.json`. If the daemon is running, it restarts.

## Network and Console Debugging

Use network and console commands only when the task requires request or log inspection.

The extension must continuously listen to CDP events for these features. After extension modification or upgrade, require the user to reload the Chrome extension before relying on network or console capture.

Network commands:

```bash
agent-browser-cli network start --tab <tabId>
agent-browser-cli network list --tab <tabId>
agent-browser-cli network list --tab <tabId> --filter api
agent-browser-cli network detail <requestId> --tab <tabId>
agent-browser-cli network clear --tab <tabId>
agent-browser-cli network stop --tab <tabId>
```

Console commands:

```bash
agent-browser-cli console start --tab <tabId>
agent-browser-cli console list --tab <tabId>
agent-browser-cli console list --tab <tabId> --level error
agent-browser-cli console clear --tab <tabId>
agent-browser-cli console stop --tab <tabId>
```

Network and console constraints:

- `network detail` may truncate large response bodies and mark `base64Encoded`.
- Do not paste huge response bodies into the conversation.
- `network clear` clears request cache.
- `network stop` stops listening and clears request cache.
- `console clear` clears log cache.
- `console stop` stops listening and clears log cache.
- `agent-browser-cli stop` and daemon idle exit also clear daemon-side `snapshot` and `@e` caches and notify the extension to clear network and console debug caches.

## Tab Groups and Windows

When opening new tabs for separate work streams, use Chrome native tab groups through `--session` or `--group-title`.

Use a new window only when isolation is useful:

```bash
agent-browser-cli open https://example.com --session research
agent-browser-cli open https://example.com --group-title "TaskA"
agent-browser-cli open --window https://example.com
agent-browser-cli open --window --focus https://example.com
agent-browser-cli open --profile work https://example.com
```

Rules:

- `--session` and `--group-title` both set the tab group title.
- If both are provided, `--group-title` wins.
- `--window` does not focus the new window unless `--focus` is also provided.
- `--window --group-title` and `--window --session` add the first tab in the new window to the group.
- Tab grouping is organizational only. If grouping fails but the tab opens, continue the main task.

## Screenshots and PDFs

Always let the CLI write screenshots and PDFs to files. Do not paste base64 into the conversation.

Screenshots:

```bash
agent-browser-cli screenshot --out /tmp/page.png
agent-browser-cli screenshot --full-page --out /tmp/full.png
agent-browser-cli screenshot --target '@e1' --out /tmp/button.png
agent-browser-cli screenshot --selector 'button[type=submit]' --format jpeg --quality 70 --out /tmp/button.jpg
```

Screenshot rules:

- Default capture is the current viewport.
- `--full-page` captures the full page.
- Use either `--target` or the compatible alias `--selector`.
- The target may be an `@e` reference or a CSS selector.
- Without `--out`, files are written under `/tmp/agent-browser-cli-screenshots/`.

PDFs:

```bash
agent-browser-cli save-pdf --out /tmp/page.pdf
agent-browser-cli save-pdf --paper a4 --landscape --scale 0.9 --out /tmp/page.pdf
```

PDF rules:

- Defaults are `paper=a4`, `scale=1.0`, and `print-background=true`.
- Use `--no-print-background` only when backgrounds should be disabled.
- Without `--out`, files are written under `/tmp/agent-browser-cli-pdfs/`.
- Default filenames are derived from the sanitized page title.

If high-level capture commands fail, use `exec` and CDP only if the script writes the artifact to disk. Still do not paste base64.

## JavaScript Execution

Use inline `exec` only for small scripts:

```bash
agent-browser-cli exec --tab <tabId> 'return document.title'
```

For complex JavaScript, write a temporary script file and run:

```bash
agent-browser-cli exec --tab <tabId> --file /tmp/script.js
```

Execution rules:

- Prefer `--wait-js` over fixed delays.
- When using `await`, explicitly `return` the final value or the result may be `null`.
- Keep scripts scoped to the current task.
- Prefer DOM APIs and high-level CLI commands over CDP when they are reliable.

Example:

```bash
agent-browser-cli exec --tab <tabId> 'document.querySelector("button").click()' --wait-js 'return document.body.innerText.includes("Done")' --wait-timeout 3
```

## JSON and CDP Escape Hatch

Use JSON commands for cookies, cross-tab work, CDP, extension management, or browser content permissions when high-level commands are insufficient.

Examples:

```bash
agent-browser-cli exec '{"cmd":"tabs"}'
agent-browser-cli exec '{"cmd":"cookies"}'
agent-browser-cli exec '{"cmd":"cdp","tabId":303987837,"method":"Page.captureScreenshot","params":{"format":"png"}}'
```

CDP interaction rules:

- For clicks, prefer the three-event sequence: `mouseMoved`, `mousePressed`, `mouseReleased`.
- On first attach, Chrome may show an infobar.
- Warm up first attach with a harmless `mouseMoved(0,0)` when needed.
- Use CDP only when high-level commands, selectors, `@e`, or DOM JavaScript are inadequate.

## File Uploads

Prefer the browser `DataTransfer` API for file upload simulation. Do not prefer CDP `DOM.setFileInputFiles` unless the page blocks normal DOM assignment.

```js
const input = document.querySelector('input[type=file]');
const file = new File(['content'], 'demo.txt', { type: 'text/plain' });
const dt = new DataTransfer();
dt.items.add(file);
input.files = dt.files;
input.dispatchEvent(new Event('input', { bubbles: true }));
input.dispatchEvent(new Event('change', { bubbles: true }));
return input.files.length;
```

## Troubleshooting Gate

Enter troubleshooting only after a failed target command, an explicit browser/extension/connectivity error, or a direct user request.

Allowed lightweight troubleshooting commands:

```bash
agent-browser-cli status
agent-browser-cli doctor
agent-browser-cli logs --tail 100
agent-browser-cli restart
agent-browser-cli stop
agent-browser-cli tabs
```

Interpret `status` carefully:

- `ok=true` means the status command executed successfully.
- Actual browser usability is determined by `healthy` and `summary`.
- `daemon_not_running` before a target command is usually normal.

### Daemon Not Running

Typical status:

```json
{ "summary": "daemon_not_running", "running": false }
```

During normal browser work, first run a target command such as `tabs`, `open`, `exec`, or `scan` so the daemon can auto-start.

Use restart only when auto-start fails or explicit troubleshooting is requested:

```bash
agent-browser-cli restart
agent-browser-cli status
```

### Extension Not Connected

Typical status:

```json
{ "summary": "extension_not_connected", "connection": { "extension_connected": false } }
```

Handle in this order:

1. Confirm the supervised Chromium process is running.
2. Confirm the `/opt/agent-browser/chrome-extension` extension is loaded.
3. Confirm the extension popup port equals the `configured_port` shown by `doctor`.
4. Ask the user to reload the extension in `chrome://extensions`.
5. Recheck:

```bash
agent-browser-cli status
```

### No Usable Tabs

Typical status:

```json
{ "summary": "no_active_tabs", "connection": { "active_tabs": 0 } }
```

Open or ask the user to open a normal `http` or `https` page. Do not rely on `about:blank`, `chrome://` pages, or extension pages.

### Port Mismatch

Typical status:

```json
{ "summary": "port_mismatch" }
```

First try:

```bash
agent-browser-cli restart
agent-browser-cli doctor
```

If changing the extension port is necessary, explain that it writes `~/.agent-browser-cli/config.json`, affects the Chrome extension and daemon connection, and may restart the daemon. Get explicit confirmation before:

```bash
agent-browser-cli set-extension-port <port>
```

### Logs

Daemon log file:

```text
~/.agent-browser-cli/logs/daemon.log
```

Read logs through the CLI. By default, `logs` shows the most recent 100 lines:

```bash
agent-browser-cli logs
agent-browser-cli logs --tail 200
```

`logs` outputs plain text. It does not output JSON and does not support `--follow`.

### Restart and Stop

```bash
agent-browser-cli restart
agent-browser-cli stop
```

`restart` reloads configuration and starts the daemon.

`stop` stops only the daemon.

## Response Discipline

When using this skill in an agent response:

- State the browser action being taken, not internal implementation detail.
- Report tab IDs, profile labels, file paths, and relevant errors when they matter.
- Summarize large outputs instead of pasting them.
- Ask for user action only when Chrome UI interaction, extension reload, permission changes, or explicit confirmation is required.
- Do not present troubleshooting as required when a goal command has not failed.
- Do not expose cookies, tokens, credentials, or sensitive page data unless the user explicitly requested that exact data and it is necessary for the task.
