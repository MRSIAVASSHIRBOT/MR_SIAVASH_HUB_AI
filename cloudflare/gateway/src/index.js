const API_BASE = "https://api.cloudflare.com/client/v4";
const REQUEST_TIMEOUT_MS = 8_000;
const MAX_RESPONSE_BYTES = 1_048_576;
const MAX_PAGES = 20;
const PAGE_SIZE = 50;
const MAX_LIST_ITEMS = MAX_PAGES * PAGE_SIZE;
const ACCOUNT_ID_PATTERN = /^[a-f0-9]{32}$/;
const RESOURCE_NAME_PATTERN = /^[a-z0-9_][a-z0-9_-]{0,62}$/;
const JSON_CONTENT_TYPE = /^application\/(?:json|[a-z0-9.+-]+\+json)(?:\s*;|$)/i;

class GatewayFault extends Error {
  constructor(code, status) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

function jsonResponse(payload, status = 200, requestId = "") {
  return new Response(JSON.stringify({ ...payload, request_id: requestId }), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
    },
  });
}

async function digest(value) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

async function verifyGatewayToken(request, expectedToken) {
  if (typeof expectedToken !== "string" || expectedToken.length < 32) return false;
  const authorization = request.headers.get("authorization") || "";
  if (!authorization.startsWith("Bearer ")) return false;
  const suppliedToken = authorization.slice(7).trim();
  if (!suppliedToken) return false;

  const [suppliedHash, expectedHash] = await Promise.all([
    digest(suppliedToken),
    digest(expectedToken),
  ]);
  let difference = 0;
  for (let index = 0; index < suppliedHash.length; index += 1) {
    difference |= suppliedHash[index] ^ expectedHash[index];
  }
  return difference === 0;
}

function requireAccountId(env) {
  if (typeof env.CF_ACCOUNT_ID !== "string" || !ACCOUNT_ID_PATTERN.test(env.CF_ACCOUNT_ID)) {
    throw new GatewayFault("gateway_account_not_configured", 503);
  }
  return env.CF_ACCOUNT_ID;
}

function requireZoneId(env) {
  if (typeof env.CF_ZONE_ID !== "string" || !ACCOUNT_ID_PATTERN.test(env.CF_ZONE_ID)) {
    throw new GatewayFault("gateway_zone_not_configured", 503);
  }
  return env.CF_ZONE_ID;
}

async function readBoundedJson(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!JSON_CONTENT_TYPE.test(contentType)) {
    throw new GatewayFault("provider_invalid_content_type", 502);
  }

  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_RESPONSE_BYTES) {
    throw new GatewayFault("provider_response_too_large", 502);
  }

  if (!response.body) throw new GatewayFault("provider_empty_response", 502);
  const reader = response.body.getReader();
  const chunks = [];
  let totalBytes = 0;
  try {
    while (true) {
      const result = await reader.read();
      if (result.done) break;
      totalBytes += result.value.byteLength;
      if (totalBytes > MAX_RESPONSE_BYTES) {
        await reader.cancel();
        throw new GatewayFault("provider_response_too_large", 502);
      }
      chunks.push(result.value);
    }
  } finally {
    reader.releaseLock();
  }

  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  let payload;
  try {
    payload = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new GatewayFault("provider_invalid_json", 502);
  }
  if (!payload || typeof payload !== "object" || payload.success !== true ||
      !("result" in payload)) {
    throw new GatewayFault("provider_api_error", 502);
  }
  return payload;
}

async function cloudflareGet(path, env, query = {}) {
  if (typeof env.CF_API_TOKEN !== "string" || !env.CF_API_TOKEN.trim()) {
    throw new GatewayFault("gateway_provider_token_not_configured", 503);
  }

  const url = new URL(API_BASE + path);
  for (const [key, value] of Object.entries(query)) {
    url.searchParams.set(key, String(value));
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await globalThis.fetch(url, {
      method: "GET",
      redirect: "manual",
      signal: controller.signal,
      headers: {
        authorization: "Bearer " + env.CF_API_TOKEN,
        accept: "application/json",
      },
    });
    if (response.status >= 300 && response.status < 400) {
      throw new GatewayFault("provider_redirect_rejected", 502);
    }
    if (!response.ok) throw new GatewayFault("provider_http_error", 502);
    return await readBoundedJson(response);
  } catch (error) {
    if (error instanceof GatewayFault) throw error;
    if (error && error.name === "AbortError") {
      throw new GatewayFault("provider_timeout", 504);
    }
    throw new GatewayFault("provider_unavailable", 502);
  } finally {
    clearTimeout(timeout);
  }
}

function requireListResult(payload) {
  if (!Array.isArray(payload.result)) {
    throw new GatewayFault("provider_invalid_result", 502);
  }
  if (payload.result.length > MAX_LIST_ITEMS) {
    throw new GatewayFault("provider_item_limit", 502);
  }
  if (payload.result.some((item) => !item || typeof item !== "object" || Array.isArray(item))) {
    throw new GatewayFault("provider_invalid_item", 502);
  }
  return payload.result;
}

async function listWorkers(env) {
  const accountId = requireAccountId(env);
  const payload = await cloudflareGet("/accounts/" + accountId + "/workers/scripts", env);
  return requireListResult(payload).flatMap((item) => {
    if (typeof item.id !== "string" || !RESOURCE_NAME_PATTERN.test(item.id)) return [];
    return [{
      id: item.id,
      etag: typeof item.etag === "string" ? item.etag : null,
      created_on: typeof item.created_on === "string" ? item.created_on : null,
      modified_on: typeof item.modified_on === "string" ? item.modified_on : null,
    }];
  });
}

async function listWorkerRoutes(env) {
  const zoneId = requireZoneId(env);
  const payload = await cloudflareGet("/zones/" + zoneId + "/workers/routes", env);
  return requireListResult(payload).flatMap((item) => {
    if (typeof item.id !== "string" || item.id.length > 128 ||
        typeof item.pattern !== "string" || item.pattern.length > 253) return [];
    return [{
      id: item.id,
      pattern: item.pattern,
      script: typeof item.script === "string" ? item.script : null,
      zone_id: typeof item.zone_id === "string" ? item.zone_id : null,
    }];
  });
}

async function listD1Databases(env) {
  const accountId = requireAccountId(env);
  const items = [];
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const payload = await cloudflareGet(
      "/accounts/" + accountId + "/d1/database",
      env,
      { page, per_page: PAGE_SIZE },
    );
    const current = requireListResult(payload);
    items.push(...current);
    if (items.length > MAX_LIST_ITEMS) throw new GatewayFault("provider_item_limit", 502);

    const totalPages = payload.result_info && payload.result_info.total_pages;
    if (Number.isInteger(totalPages)) {
      if (totalPages < 1 || totalPages > MAX_PAGES) {
        throw new GatewayFault("provider_pagination_limit", 502);
      }
      if (page >= totalPages) break;
    } else if (current.length < PAGE_SIZE) {
      break;
    }
    if (page === MAX_PAGES) throw new GatewayFault("provider_pagination_limit", 502);
  }

  return items.flatMap((item) => {
    if (typeof item.uuid !== "string" || item.uuid.length > 128 ||
        typeof item.name !== "string" || item.name.length > 128) return [];
    return [{
      uuid: item.uuid,
      name: item.name,
      created_at: typeof item.created_at === "string" && item.created_at.length <= 64
        ? item.created_at : null,
    }];
  });
}

async function getWorkerSettings(env, scriptName) {
  if (!RESOURCE_NAME_PATTERN.test(scriptName)) {
    throw new GatewayFault("invalid_worker_name", 400);
  }
  const accountId = requireAccountId(env);
  const payload = await cloudflareGet(
    "/accounts/" + accountId + "/workers/scripts/" + scriptName + "/settings",
    env,
  );
  if (!payload.result || typeof payload.result !== "object" || Array.isArray(payload.result)) {
    throw new GatewayFault("provider_invalid_result", 502);
  }

  const rawBindings = Array.isArray(payload.result.bindings) ? payload.result.bindings : [];
  if (rawBindings.length > 100) throw new GatewayFault("provider_item_limit", 502);
  const bindings = rawBindings.flatMap((binding) => {
    if (!binding || typeof binding !== "object" ||
        typeof binding.name !== "string" || binding.name.length < 1 || binding.name.length > 128 ||
        typeof binding.type !== "string" || binding.type.length < 1 || binding.type.length > 64) return [];
    return [{ name: binding.name, type: binding.type }];
  });

  return {
    compatibility_date: typeof payload.result.compatibility_date === "string"
      ? payload.result.compatibility_date.slice(0, 32) : null,
    usage_model: typeof payload.result.usage_model === "string"
      ? payload.result.usage_model.slice(0, 32) : null,
    bindings,
  };
}

function resolveOperation(pathname) {
  if (pathname === "/health") return { name: "health" };
  if (pathname === "/v1/workers") return { name: "list_workers" };
  if (pathname === "/v1/worker-routes") return { name: "list_worker_routes" };
  if (pathname === "/v1/d1-databases") return { name: "list_d1_databases" };
  const settingsMatch = pathname.match(/^\/v1\/workers\/([a-z0-9_][a-z0-9_-]{0,62})\/settings$/);
  if (settingsMatch) return { name: "get_worker_settings", scriptName: settingsMatch[1] };
  return null;
}

export async function handleRequest(request, env) {
  const requestId = crypto.randomUUID();
  const startedAt = Date.now();
  let operation = "unknown";
  let status = 500;

  try {
    if (request.method !== "GET") throw new GatewayFault("method_not_allowed", 405);
    if (request.body !== null) throw new GatewayFault("request_body_not_allowed", 400);

    const url = new URL(request.url);
    if (url.search || url.hash) throw new GatewayFault("query_not_allowed", 400);

    if (!(await verifyGatewayToken(request, env.GATEWAY_AUTH_TOKEN))) {
      throw new GatewayFault("unauthorized", 401);
    }

    const route = resolveOperation(url.pathname);
    if (!route) throw new GatewayFault("not_found", 404);
    operation = route.name;

    let data;
    if (route.name === "health") {
      data = { status: "ready", mode: "read_only" };
    } else if (route.name === "list_workers") {
      data = await listWorkers(env);
    } else if (route.name === "list_worker_routes") {
      data = await listWorkerRoutes(env);
    } else if (route.name === "list_d1_databases") {
      data = await listD1Databases(env);
    } else {
      data = await getWorkerSettings(env, route.scriptName);
    }

    status = 200;
    return jsonResponse({ ok: true, data }, status, requestId);
  } catch (error) {
    const fault = error instanceof GatewayFault
      ? error
      : new GatewayFault("internal_error", 500);
    status = fault.status;
    return jsonResponse({ ok: false, error: { code: fault.code } }, status, requestId);
  } finally {
    console.log({
      event: "cloudflare_gateway_request",
      request_id: requestId,
      operation,
      status,
      duration_ms: Date.now() - startedAt,
    });
  }
}

export default {
  fetch(request, env) {
    return handleRequest(request, env);
  },
};
