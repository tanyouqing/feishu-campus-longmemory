---
name: longmemory-ingest
description: "Forward OpenClaw message evidence to LongMemory."
metadata:
  {
    "openclaw": {
      "events": ["message:received", "message:sent", "message:preprocessed"],
      "requires": { "bins": ["node"], "env": ["LONGMEMORY_BASE_URL", "LONGMEMORY_INGEST_TOKEN"] }
    }
  }
---

# LongMemory Ingest Hook

This hook forwards real OpenClaw message events to `feishu-campus-longmemory`. Prompt injection has moved to the native OpenClaw plugin in `../longmemory-context-plugin`, which uses `before_prompt_build` and returns prompt context through OpenClaw's plugin hook API.

Required environment variables:

- `LONGMEMORY_BASE_URL`, for example `http://127.0.0.1:8000`
- `LONGMEMORY_INGEST_TOKEN`

Optional environment variables:

- `LONGMEMORY_FORCE_USER_ID` or `LONGMEMORY_USER_ID`, optional override for the user ID used by Evidence forwarding and Memory Search
- `LONGMEMORY_HOOK_DEBUG`, enabled by default; set to `false`, `0`, `off`, `disabled`, or `no` to hide diagnostic hook logs

Behavior:

- `message:received` and `message:sent` are forwarded to `/events/ingest` as Evidence.
- `message:preprocessed` is only observed for diagnostics. The native plugin handles Context Pack injection before prompt build.
- Requests include `ngrok-skip-browser-warning: true`, so ngrok free-domain warning pages do not interfere with JSON API calls.
- The hook logs diagnostic lines for event delivery. If the middleware is unavailable, it logs a warning and lets OpenClaw continue.

The hook intentionally does not send mock events. It only uses the OpenClaw event object it receives from the gateway.

Prompt injection plugin:

- Install `../longmemory-context-plugin` as a native OpenClaw plugin.
- The plugin schema intentionally allows empty config during installation. Add `plugins.entries.longmemory-context.config.baseUrl` and `ingestToken` in `openclaw.json` after installation.
- Keep this internal hook enabled for Evidence Store writes.
- Enable the plugin entry `longmemory-context` for prompt injection.
- The native plugin must use `plugins.entries.longmemory-context.config` in `openclaw.json` for `baseUrl`, `ingestToken`, and prompt settings. It intentionally does not read `process.env`, because OpenClaw 4.12 blocks native plugins that combine environment variable access with network sends.

Diagnostic checklist:

1. Look for `[longmemory-ingest] forwarded action=received status=200` to confirm Evidence forwarding.
2. Look for `[longmemory-context] before_prompt_build` to confirm plugin prompt injection is running.
3. Look for `[longmemory-context] search result empty=false packLen=<n>` to confirm LongMemory returned injectable context.
4. Look for `[longmemory-context] returning before_prompt_build injection` to confirm the plugin returned prompt context to OpenClaw.
