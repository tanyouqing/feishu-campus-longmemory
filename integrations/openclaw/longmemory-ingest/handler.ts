const disabledValues = new Set(["0", "false", "off", "disabled", "no"]);
const defaultForcedUserId = "ou_ae7e8ab7eb92c6e0e37f0b9ab1964137";

const handler = async (event: any) => {
  const baseUrl = process.env.LONGMEMORY_BASE_URL;
  const ingestToken = process.env.LONGMEMORY_INGEST_TOKEN;

  if (!baseUrl || !ingestToken) {
    console.warn("[longmemory-ingest] Missing LONGMEMORY_BASE_URL or LONGMEMORY_INGEST_TOKEN");
    return;
  }

  if (event.type !== "message") {
    return;
  }

  logDiagnostic(
    `[longmemory-ingest] event type=${String(event.type)} action=${String(event.action)} ` +
      `session=${safeValue(event.sessionKey)} contextKeys=${contextKeys(event.context)}`,
  );

  if (["received", "sent"].includes(event.action)) {
    await forwardEvidenceEvent(baseUrl, ingestToken, event);
    return;
  }

  if (event.action === "preprocessed") {
    logDiagnostic("[longmemory-ingest] message:preprocessed observed; prompt injection is handled by the longmemory-context plugin");
  }
};

async function forwardEvidenceEvent(baseUrl: string, ingestToken: string, event: any) {
  const url = `${baseUrl.replace(/\/$/, "")}/events/ingest`;
  const userId = resolveUserId(event);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: requestHeaders(ingestToken),
      body: JSON.stringify({
        ...event,
        user_id: userId,
        source: "openclaw",
        event_type: `${event.type}:${event.action}`,
      }),
    });

    const body = await response.text();
    if (!response.ok) {
      console.warn(`[longmemory-ingest] Failed to forward event: ${response.status} ${preview(body)}`);
      return;
    }

    const payload = parseJsonSafely(body);
    logDiagnostic(
      `[longmemory-ingest] forwarded action=${String(event.action)} status=${response.status} ` +
        `user=${safeValue(userId)} event_id=${safeValue(payload?.event_id)}`,
    );
  } catch (error) {
    console.warn(`[longmemory-ingest] Failed to forward event: ${String(error)}`);
  }
}

function pickFirst(...values: any[]) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function resolveUserId(event: any) {
  return String(
    pickFirst(
      process.env.LONGMEMORY_FORCE_USER_ID,
      process.env.LONGMEMORY_USER_ID,
      defaultForcedUserId,
      event?.user_id,
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

function logDiagnostic(message: string) {
  if (disabledValues.has(String(process.env.LONGMEMORY_HOOK_DEBUG || "").toLowerCase())) {
    return;
  }
  console.warn(message);
}

function contextKeys(context: any) {
  if (!context || typeof context !== "object") {
    return "-";
  }
  const keys = Object.keys(context);
  return keys.length ? keys.join(",") : "-";
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

export default handler;
