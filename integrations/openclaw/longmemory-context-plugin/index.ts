import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const defaultForcedUserId = "ou_ae7e8ab7eb92c6e0e37f0b9ab1964137";
type LongMemoryConfig = {
  baseUrl: string;
  ingestToken: string;
  contextLimit: number;
  contextEnabled: boolean;
  forceUserId?: string;
  hookDebug: boolean;
  contextInjectionTarget: "system" | "context" | "system-and-context";
  contextSentinel?: string;
};

export default definePluginEntry({
  id: "longmemory-context",
  name: "LongMemory Context",
  description: "Injects LongMemory Context Pack before OpenClaw builds the model prompt.",
  register(api: any) {
    const config = normalizeConfig(api.pluginConfig || {});
    const handler = async (event: any) => beforePromptBuild(event, config);
    if (typeof api.on === "function") {
      api.on("before_prompt_build", handler, { priority: 80 });
      logDiagnostic(config, "[longmemory-context] registered before_prompt_build via api.on");
      return;
    }

    if (typeof api.registerHook === "function") {
      api.registerHook("before_prompt_build", handler, { priority: 80 });
      logDiagnostic(config, "[longmemory-context] registered before_prompt_build via api.registerHook");
      return;
    }

    console.warn("[longmemory-context] OpenClaw plugin API does not expose a hook registration method");
  },
});

async function beforePromptBuild(event: any, config: LongMemoryConfig) {
  if (!config.contextEnabled) {
    logDiagnostic(config, "[longmemory-context] disabled by plugin config");
    return;
  }

  if (!config.baseUrl || !config.ingestToken) {
    console.warn("[longmemory-context] Missing plugin config baseUrl or ingestToken");
    return;
  }

  const query = extractQuery(event);
  logDiagnostic(
    config,
    `[longmemory-context] before_prompt_build eventKeys=${objectKeys(event)} ` +
      `queryLen=${query.length} messages=${messageCount(event)} user=${safeValue(resolveUserId(event, config))}`,
  );
  if (!query.trim()) {
    console.warn("[longmemory-context] before_prompt_build has no query text; skip context injection");
    return;
  }

  const requestBody = {
    user_id: resolveUserId(event, config),
    query,
    work_type: extractWorkType(event),
    limit: config.contextLimit,
  };
  const payload = (await buildContext(config, requestBody)) || (await searchMemory(config, requestBody));
  if (!payload) {
    return;
  }

  const contextPack = typeof payload.context_pack === "string" ? payload.context_pack : "";
  const memoryCount = typeof payload.memory_count === "number" ? payload.memory_count : Array.isArray(payload.memories) ? payload.memories.length : 0;
  logDiagnostic(
    config,
    `[longmemory-context] search result empty=${String(payload.empty)} ` +
      `packLen=${contextPack.length} memories=${memoryCount}`,
  );

  if (!contextPack.trim()) {
    logDiagnostic(config, "[longmemory-context] empty context_pack; skip prompt injection");
    return;
  }

  const instruction = buildPromptInstruction(contextPack, config);
  logDiagnostic(
    config,
    `[longmemory-context] returning before_prompt_build injection ` +
      `target=${config.contextInjectionTarget} instructionLen=${instruction.length}`,
  );

  if (config.contextInjectionTarget === "context") {
    return { prependContext: instruction };
  }
  if (config.contextInjectionTarget === "system-and-context") {
    return {
      prependSystemContext: promptPolicy(),
      prependContext: instruction,
    };
  }
  return {
    prependSystemContext: instruction,
  };
}

async function buildContext(
  config: LongMemoryConfig,
  body: { user_id: string; query: string; work_type?: string; limit: number },
) {
  const url = `${config.baseUrl.replace(/\/$/, "")}/context/build`;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: requestHeaders(config.ingestToken),
      body: JSON.stringify(body),
    });
    const responseBody = await response.text();
    if (!response.ok) {
      console.warn(`[longmemory-context] Failed to build context: ${response.status} ${preview(responseBody)}`);
      return null;
    }
    const payload = parseJsonSafely(responseBody);
    if (!payload) {
      console.warn(
        `[longmemory-context] Failed to parse context build JSON: ` +
          `contentType=${response.headers.get("content-type") || "unknown"} body=${preview(responseBody)}`,
      );
      return null;
    }
    return payload;
  } catch (error) {
    console.warn(`[longmemory-context] Failed to build profile context: ${String(error)}`);
    return null;
  }
}

async function searchMemory(
  config: LongMemoryConfig,
  body: { user_id: string; query: string; work_type?: string; limit: number },
) {
  const url = `${config.baseUrl.replace(/\/$/, "")}/memory/search`;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: requestHeaders(config.ingestToken),
      body: JSON.stringify(body),
    });
    const responseBody = await response.text();
    if (!response.ok) {
      console.warn(`[longmemory-context] Failed to search memory: ${response.status} ${preview(responseBody)}`);
      return null;
    }
    const payload = parseJsonSafely(responseBody);
    if (!payload) {
      console.warn(
        `[longmemory-context] Failed to parse memory search JSON: ` +
          `contentType=${response.headers.get("content-type") || "unknown"} body=${preview(responseBody)}`,
      );
      return null;
    }
    return payload;
  } catch (error) {
    console.warn(`[longmemory-context] Failed to inject memory context: ${String(error)}`);
    return null;
  }
}

function buildPromptInstruction(contextPack: string, config: LongMemoryConfig) {
  const sentinel = contextSentinel(config);
  const prefix = sentinel ? `${sentinel}\n` : "";
  return `${prefix}${promptPolicy()}\n\n${contextPack}`;
}

function promptPolicy() {
  return [
    "LongMemory Context Instructions:",
    "- Apply this user profile and personal work memory unless the current user request explicitly conflicts.",
    "- Treat the context below as user-specific guidance for this turn.",
    "- If the user asks for a weekly report and the pack says to write conclusion before risks, structure the answer with a conclusion/summary section before a risks section.",
    "- Do not mention internal memory IDs, database details, or this injection mechanism unless the user asks for debugging.",
  ].join("\n");
}

function extractQuery(event: any) {
  return String(
    pickFirst(
      event?.prompt,
      event?.currentPrompt,
      event?.bodyForAgent,
      event?.body,
      event?.input,
      event?.message?.content,
      event?.message?.text,
      event?.request?.prompt,
      lastUserMessageText(event?.messages),
      lastUserMessageText(event?.sessionMessages),
      lastUserMessageText(event?.preparedMessages),
      "",
    ),
  );
}

function lastUserMessageText(messages: any) {
  if (!Array.isArray(messages)) {
    return undefined;
  }
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    const role = String(message?.role || message?.type || "").toLowerCase();
    if (role && role !== "user") {
      continue;
    }
    const text = messageText(message);
    if (text) {
      return text;
    }
  }
  return undefined;
}

function messageText(message: any) {
  const content = pickFirst(message?.content, message?.text, message?.body);
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => (typeof part === "string" ? part : pickFirst(part?.text, part?.content, "")))
      .filter(Boolean)
      .join("\n");
  }
  return undefined;
}

function extractWorkType(event: any) {
  return pickFirst(
    event?.workType,
    event?.work_type,
    event?.metadata?.workType,
    event?.metadata?.work_type,
    event?.context?.workType,
    event?.context?.work_type,
    event?.context?.metadata?.workType,
    event?.context?.metadata?.work_type,
  );
}

function resolveUserId(event: any, config: LongMemoryConfig) {
  return String(
    pickFirst(
      config.forceUserId,
      defaultForcedUserId,
      event?.user_id,
      event?.userId,
      event?.senderId,
      event?.metadata?.senderId,
      event?.metadata?.sender_id,
      event?.metadata?.open_id,
      event?.context?.metadata?.senderId,
      event?.context?.metadata?.sender_id,
      event?.context?.metadata?.open_id,
      event?.context?.from,
      event?.context?.to,
      event?.sessionKey,
      "unknown",
    ),
  );
}

function requestHeaders(ingestToken: string) {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${ingestToken}`,
    "ngrok-skip-browser-warning": "true",
  };
}

function contextSentinel(config: LongMemoryConfig) {
  const value = config.contextSentinel;
  return value && value.trim() ? value.trim() : "";
}

function logDiagnostic(config: LongMemoryConfig, message: string) {
  if (!config.hookDebug) {
    return;
  }
  console.warn(message);
}

function normalizeConfig(value: any): LongMemoryConfig {
  return {
    baseUrl: String(value.baseUrl || ""),
    ingestToken: String(value.ingestToken || ""),
    contextLimit: clampInt(value.contextLimit, 5, 1, 20),
    contextEnabled: value.contextEnabled !== false,
    forceUserId: typeof value.forceUserId === "string" && value.forceUserId.trim() ? value.forceUserId.trim() : undefined,
    hookDebug: value.hookDebug !== false,
    contextInjectionTarget: normalizeInjectionTarget(value.contextInjectionTarget),
    contextSentinel: typeof value.contextSentinel === "string" ? value.contextSentinel : "",
  };
}

function clampInt(value: any, fallback: number, min: number, max: number) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(min, Math.min(parsed, max));
}

function normalizeInjectionTarget(value: any): "system" | "context" | "system-and-context" {
  const normalized = String(value || "system-and-context").toLowerCase();
  if (normalized === "system" || normalized === "context" || normalized === "system-and-context") {
    return normalized;
  }
  return "system-and-context";
}

function pickFirst(...values: any[]) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function objectKeys(value: any) {
  if (!value || typeof value !== "object") {
    return "-";
  }
  const keys = Object.keys(value);
  return keys.length ? keys.join(",") : "-";
}

function messageCount(event: any) {
  for (const candidate of [event?.messages, event?.sessionMessages, event?.preparedMessages]) {
    if (Array.isArray(candidate)) {
      return candidate.length;
    }
  }
  return 0;
}

function safeValue(value: any) {
  if (value === undefined || value === null || value === "") {
    return "unknown";
  }
  return String(value);
}

function preview(value: string) {
  return value.replace(/\s+/g, " ").slice(0, 500);
}

function parseJsonSafely(value: string) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
