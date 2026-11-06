import test from "node:test";
import assert from "node:assert/strict";
import worker, { handleRequest } from "../src/index.js";

const ENV = {
  GATEWAY_AUTH_TOKEN: "gateway-test-token-that-is-long-enough-123456",
  CF_API_TOKEN: "provider-test-token",
  CF_ACCOUNT_ID: "a".repeat(32),
  CF_ZONE_ID: "b".repeat(32),
};

async function withFetch(handler, callback) {
  const original = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    const request = new Request(input, init);
    return handler({ method: request.method, url: new URL(request.url), headers: request.headers });
  };
  try {
    return await callback();
  } finally {
    globalThis.fetch = original;
  }
}

function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.token !== null) {
    headers.set("authorization", "Bearer " + (options.token || ENV.GATEWAY_AUTH_TOKEN));
  }
  const init = {
    method: options.method || "GET",
    headers,
  };
  if (options.body !== undefined) init.body = options.body;
  return new Request("https://gateway.example" + path, init);
}

async function json(response) {
  return response.json();
}

test("health is authenticated and reports only the read-only service state", async () => {
  const response = await worker.fetch(request("/health"), ENV);
  assert.equal(response.status, 200);
  assert.deepEqual(await json(response).then(value => value.data), {
    status: "ready",
    mode: "read_only",
  });
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("missing or invalid gateway credentials fail before any provider request", async () => {
  await withFetch(() => {
    assert.fail("provider fetch must not be called");
  }, async () => {
    const missing = await worker.fetch(request("/v1/workers", { token: null }), ENV);
    assert.equal(missing.status, 401);
    const invalid = await worker.fetch(request("/v1/workers", { token: "wrong-token" }), ENV);
    assert.equal(invalid.status, 401);
  });
});

test("gateway rejects non-GET methods, query strings, and request bodies", async () => {
  const post = await worker.fetch(request("/v1/workers", { method: "POST" }), ENV);
  assert.equal(post.status, 405);
  const query = await worker.fetch(request("/v1/workers?account_id=attacker"), ENV);
  assert.equal(query.status, 400);
  const bodyRequest = {
    method: "GET",
    url: "https://gateway.example/v1/workers",
    headers: new Headers({ authorization: "Bearer " + ENV.GATEWAY_AUTH_TOKEN }),
    body: new ReadableStream(),
  };
  const body = await worker.fetch(bodyRequest, ENV);
  assert.equal(body.status, 400);
});

test("unknown paths are not forwarded to Cloudflare", async () => {
  await withFetch(() => {
    assert.fail("unknown paths must not reach the provider");
  }, async () => {
    const response = await worker.fetch(request("/v1/arbitrary?url=https://evil.example"), ENV);
    assert.equal(response.status, 400);
    const unknown = await worker.fetch(request("/v1/arbitrary"), ENV);
    assert.equal(unknown.status, 404);
  });
});

test("Worker inventory uses a fixed endpoint and projects safe metadata only", async () => {
  await withFetch(async upstream => {
    assert.equal(upstream.method, "GET");
    assert.equal(upstream.url.href, "https://api.cloudflare.com/client/v4/accounts/" +
      ENV.CF_ACCOUNT_ID + "/workers/scripts");
    assert.equal(upstream.headers.get("authorization"), "Bearer " + ENV.CF_API_TOKEN);
    return Response.json({
      success: true,
      result: [
        { id: "gateway-staging", etag: "etag-1", created_on: "2026-11-06T00:00:00Z" },
        { id: "../invalid", etag: "unsafe" },
      ],
    });
  }, async () => {
    const response = await worker.fetch(request("/v1/workers"), ENV);
    assert.equal(response.status, 200, await response.clone().text());
    const body = await json(response);
    assert.deepEqual(body.data, [{
      id: "gateway-staging",
      etag: "etag-1",
      created_on: "2026-11-06T00:00:00Z",
      modified_on: null,
    }]);
  });
});

test("Worker route inventory does not send unsupported pagination parameters", async () => {
  await withFetch(async upstream => {
    assert.equal(upstream.url.href, "https://api.cloudflare.com/client/v4/zones/" +
      ENV.CF_ZONE_ID + "/workers/routes");
    return Response.json({
      success: true,
      result: [{
        id: "route-1",
        pattern: "example.test/api/*",
        script: "gateway-staging",
        zone_id: ENV.CF_ZONE_ID,
      }],
    });
  }, async () => {
    const response = await worker.fetch(request("/v1/worker-routes"), ENV);
    assert.equal(response.status, 200);
    assert.equal((await json(response)).data[0].script, "gateway-staging");
  });
});

test("D1 inventory uses bounded documented pagination", async () => {
  const requestedPages = [];
  await withFetch(async upstream => {
    requestedPages.push(upstream.url.searchParams.get("page"));
    assert.equal(upstream.url.pathname, "/client/v4/accounts/" + ENV.CF_ACCOUNT_ID + "/d1/database");
    assert.equal(upstream.url.searchParams.get("per_page"), "50");
    const page = Number(upstream.url.searchParams.get("page"));
    return Response.json({
      success: true,
      result: [{ uuid: "db-" + page, name: "metadata-" + page }],
      result_info: { total_pages: 2 },
    });
  }, async () => {
    const response = await worker.fetch(request("/v1/d1-databases"), ENV);
    assert.equal(response.status, 200);
    assert.deepEqual((await json(response)).data.map(item => item.uuid), ["db-1", "db-2"]);
  });
  assert.deepEqual(requestedPages, ["1", "2"]);
});

test("D1 inventory rejects malformed and unbounded pagination metadata", async (t) => {
  const cases = [
    { total_pages: true, code: "provider_invalid_pagination" },
    { total_pages: -1, code: "provider_invalid_pagination" },
    { total_pages: "2", code: "provider_invalid_pagination" },
    { total_pages: 21, code: "provider_pagination_limit" },
  ];
  for (const item of cases) {
    await t.test(JSON.stringify(item.total_pages), async () => {
      await withFetch(async () => Response.json({
        success: true,
        result: [],
        result_info: { total_pages: item.total_pages },
      }), async () => {
        const response = await worker.fetch(request("/v1/d1-databases"), ENV);
        assert.equal(response.status, 502);
        assert.equal((await json(response)).error.code, item.code);
      });
    });
  }
});

test("D1 inventory accepts a valid empty result with zero pages", async () => {
  await withFetch(async () => Response.json({
    success: true,
    result: [],
    result_info: { total_pages: 0 },
  }), async () => {
    const response = await worker.fetch(request("/v1/d1-databases"), ENV);
    assert.equal(response.status, 200);
    assert.deepEqual((await json(response)).data, []);
  });
});

test("Worker settings never return secret or plain-text binding values", async () => {
  const secret = "must-not-leave-the-provider";
  await withFetch(async upstream => {
    assert.ok(upstream.url.pathname.endsWith("/workers/scripts/gateway-staging/settings"));
    return Response.json({
      success: true,
      result: {
        compatibility_date: "2026-11-06",
        usage_model: "standard",
        bindings: [
          { name: "DB", type: "d1", id: "db-id" },
          { name: "API_SECRET", type: "secret_text", text: secret },
          { name: "PUBLIC_ORIGIN", type: "plain_text", text: secret },
        ],
      },
    });
  }, async () => {
    const response = await worker.fetch(request("/v1/workers/gateway-staging/settings"), ENV);
    assert.equal(response.status, 200);
    const serialized = JSON.stringify(await json(response));
    assert.ok(!serialized.includes(secret));
    assert.ok(!serialized.includes('"text"'));
    assert.ok(serialized.includes("API_SECRET"));
  });
});

test("provider redirects and non-JSON responses fail closed", async () => {
  await withFetch(async () => new Response(null, {
    status: 302,
    headers: { location: "https://attacker.example/redirect" },
  }), async () => {
    const response = await worker.fetch(request("/v1/workers"), ENV);
    assert.equal(response.status, 502);
    assert.equal((await json(response)).error.code, "provider_redirect_rejected");
  });

  await withFetch(async () => new Response("not json", {
    status: 200,
    headers: { "content-type": "text/plain" },
  }), async () => {
    const response = await worker.fetch(request("/v1/workers"), ENV);
    assert.equal(response.status, 502);
    assert.equal((await json(response)).error.code, "provider_invalid_content_type");
  });
});

test("oversized provider responses are rejected before JSON parsing", async () => {
  await withFetch(async () => new Response(JSON.stringify({
    success: true,
    result: [],
  }), {
    status: 200,
    headers: {
      "content-type": "application/json",
      "content-length": "2000000",
    },
  }), async () => {
    const response = await worker.fetch(request("/v1/workers"), ENV);
    assert.equal(response.status, 502);
    assert.equal((await json(response)).error.code, "provider_response_too_large");
  });
});

test("provider errors do not expose raw response bodies or credentials", async () => {
  await withFetch(async () => Response.json({
    success: false,
    errors: [{ code: 1234, message: "private provider detail" }],
    result: null,
  }, { status: 200 }), async () => {
    const response = await worker.fetch(request("/v1/workers"), ENV);
    assert.equal(response.status, 502);
    const serialized = await response.text();
    assert.ok(!serialized.includes("private provider detail"));
    assert.ok(!serialized.includes(ENV.CF_API_TOKEN));
  });
});

test("missing server-side account and provider configuration fails closed", async () => {
  const missingAccount = { ...ENV, CF_ACCOUNT_ID: "" };
  const accountResponse = await worker.fetch(request("/v1/workers"), missingAccount);
  assert.equal(accountResponse.status, 503);

  const missingProviderToken = { ...ENV, CF_API_TOKEN: "" };
  const providerResponse = await worker.fetch(request("/v1/workers"), missingProviderToken);
  assert.equal(providerResponse.status, 503);
});

test("exported handler delegates to the tested request boundary", async () => {
  const response = await handleRequest(request("/health"), ENV);
  assert.equal(response.status, 200);
});
