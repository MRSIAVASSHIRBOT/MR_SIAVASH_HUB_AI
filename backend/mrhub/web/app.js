(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const tokenKey = "mrh_session_token";
  let token = sessionStorage.getItem(tokenKey);

  function message(target, text, kind = "") {
    const node = $(target);
    node.textContent = text || "";
    node.className = kind ? `message ${kind}` : "message";
  }

  function element(tag, text, className = "") {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }

  function setAuthenticated(value) {
    $("#auth-panel").hidden = value;
    $("#workspace").hidden = !value;
    $("#logout-button").hidden = !value;
    $("#refresh-button").hidden = !value;
    $("#session-state").textContent = value ? "نشست فعال" : "بدون نشست";
    $("#session-state").className = value ? "status-pill" : "status-pill status-muted";
  }

  function endSession() {
    token = null;
    sessionStorage.removeItem(tokenKey);
    setAuthenticated(false);
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    if (token && options.auth !== false) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
    });
    let payload = null;
    try { payload = await response.json(); } catch { payload = null; }
    if (response.status === 401 || response.status === 403) {
      if (token && options.auth !== false) endSession();
    }
    if (!response.ok) {
      const detail = payload && payload.detail;
      throw new Error(typeof detail === "string" ? detail : `درخواست ناموفق بود (HTTP ${response.status})`);
    }
    return payload;
  }

  function renderEmpty(container, text) {
    container.replaceChildren(element("p", text, "muted"));
  }

  function renderRecords(containerSelector, records, renderRecord, emptyText) {
    const container = $(containerSelector);
    container.replaceChildren();
    if (!Array.isArray(records) || records.length === 0) {
      renderEmpty(container, emptyText);
      return;
    }
    for (const record of records) container.append(renderRecord(record));
  }

  function recordCard(title, body, metadata) {
    const card = element("article", undefined, "record");
    const head = element("div", undefined, "record-head");
    head.append(element("strong", title || "بدون عنوان"));
    card.append(head);
    if (body) card.append(element("p", body));
    if (metadata) card.append(element("small", metadata));
    return card;
  }

  function deleteButton(label, onDelete) {
    const button = element("button", label, "button button-quiet");
    button.type = "button";
    button.addEventListener("click", onDelete);
    return button;
  }

  async function loadOverview() {
    message("#workspace-message", "در حال به‌روزرسانی…");
    const [health, ready, providers, tasks] = await Promise.allSettled([
      api("/health", { auth: false }),
      api("/ready", { auth: false }),
      api("/models/providers"),
      api("/tasks?limit=12"),
    ]);
    const cards = $("#system-cards");
    cards.replaceChildren();
    const entries = [
      ["Liveness", health.status === "fulfilled" ? health.value.status : "unavailable"],
      ["Readiness", ready.status === "fulfilled" ? ready.value.status : "unavailable"],
      ["Worker", ready.status === "fulfilled" ? ready.value.worker : "not detected"],
    ];
    for (const [title, value] of entries) {
      const card = element("article", undefined, "status-card");
      card.append(element("small", title), element("strong", value));
      cards.append(card);
    }
    if (providers.status === "fulfilled") {
      renderRecords("#provider-list", providers.value.providers, (provider) => {
        const card = element("article", undefined, "provider-card");
        card.append(
          element("strong", provider.model),
          element("small", `${provider.provider} · ${provider.local ? "محلی" : "ابری"} · ${provider.health_status}`)
        );
        return card;
      }, "هیچ ارائه‌دهنده‌ای ثبت نشده است.");
    } else {
      renderEmpty($("#provider-list"), "دریافت فهرست مدل‌ها ناموفق بود.");
    }
    if (tasks.status === "fulfilled") {
      renderRecords("#task-list", tasks.value, (task) =>
        recordCard(task.task_type, task.description, `${task.status} · ${task.task_id}`),
      "هنوز کاری ثبت نشده است.");
    } else {
      renderEmpty($("#task-list"), "دریافت صف کارها ناموفق بود.");
    }
    const failures = [health, ready, providers, tasks].filter((item) => item.status === "rejected").length;
    message("#workspace-message", failures ? `به‌روزرسانی انجام شد؛ ${failures} بخش در دسترس نبود.` : "وضعیت به‌روز شد.", failures ? "error" : "success");
  }

  async function loadMemory() {
    const response = await api("/memory?limit=100");
    renderRecords("#memory-results", response.entries, (item) => {
      const card = recordCard(item.category, item.content, `${item.verification_status} · ${item.provenance} · ${item.memory_id}`);
      card.append(deleteButton("حذف", async () => {
        if (!window.confirm("این یادداشت حذف شود؟")) return;
        try { await api(`/memory/${encodeURIComponent(item.memory_id)}`, { method: "DELETE" }); await loadMemory(); }
        catch (error) { message("#workspace-message", error.message, "error"); }
      }));
      return card;
    }, "حافظه خالی است.");
  }

  async function loadKnowledge() {
    const response = await api("/knowledge/documents?limit=100");
    renderRecords("#knowledge-results", response.documents, (item) => {
      const card = recordCard(item.title, `منبع: ${item.source_ref}`, `${item.chunk_count} قطعه · ${item.trust_classification} · SHA-256 ${item.content_hash}`);
      card.append(deleteButton("حذف سند", async () => {
        if (!window.confirm("سند و همهٔ قطعات نمایه‌شدهٔ آن حذف شوند؟")) return;
        try { await api(`/knowledge/documents/${encodeURIComponent(item.document_id)}`, { method: "DELETE" }); await loadKnowledge(); }
        catch (error) { message("#workspace-message", error.message, "error"); }
      }));
      return card;
    }, "هنوز سندی ثبت نشده است.");
  }

  async function refreshAll() {
    try {
      await Promise.all([loadOverview(), loadMemory(), loadKnowledge()]);
    } catch (error) {
      message("#workspace-message", error.message, "error");
    }
  }

  $("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") || "");
    try {
      const session = await api("/auth/login", {
        method: "POST",
        auth: false,
        body: { username: String(form.get("username") || "owner"), password },
      });
      token = session.access_token;
      sessionStorage.setItem(tokenKey, token);
      event.currentTarget.reset();
      $("#login-form").elements.username.value = "owner";
      setAuthenticated(true);
      await refreshAll();
      message("#auth-message", "");
    } catch (error) {
      message("#auth-message", error.message, "error");
    }
  });

  $("#setup-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = String(new FormData(event.currentTarget).get("password") || "");
    try {
      await api("/auth/setup", { method: "POST", auth: false, body: { password } });
      const session = await api("/auth/login", {
        method: "POST",
        auth: false,
        body: { username: "owner", password },
      });
      token = session.access_token;
      sessionStorage.setItem(tokenKey, token);
      event.currentTarget.reset();
      setAuthenticated(true);
      await refreshAll();
      message("#auth-message", "حساب مالک ساخته شد و وارد شدید.", "success");
    } catch (error) {
      message("#auth-message", error.message, "error");
    }
  });

  $("#logout-button").addEventListener("click", async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* Clear the browser token even if the API is unavailable. */ }
    endSession();
  });
  $("#refresh-button").addEventListener("click", refreshAll);

  $("#memory-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/memory", { method: "POST", body: { category: form.get("category"), content: form.get("content") } });
      event.currentTarget.reset();
      await loadMemory();
      message("#workspace-message", "یادداشت ذخیره شد.", "success");
    } catch (error) { message("#workspace-message", error.message, "error"); }
  });

  $("#memory-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = String(new FormData(event.currentTarget).get("query") || "");
    try {
      const result = await api("/memory/search", { method: "POST", body: { query, limit: 10 } });
      renderRecords("#memory-results", result.results, (item) =>
        recordCard(item.category, item.content, `${item.verification_status} · ${item.provenance} · ${item.memory_id}`),
      "نتیجه‌ای پیدا نشد.");
    } catch (error) { message("#workspace-message", error.message, "error"); }
  });
  $("#memory-list-button").addEventListener("click", () => loadMemory().catch((error) => message("#workspace-message", error.message, "error")));

  $("#knowledge-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const document = await api("/knowledge/documents", {
        method: "POST",
        body: {
          title: form.get("title"),
          content: form.get("content"),
          source_ref: String(form.get("source_ref") || "").trim() || null,
          language: "fa",
          trust_classification: "user_supplied",
        },
      });
      event.currentTarget.reset();
      await loadKnowledge();
      message("#workspace-message", `سند ثبت شد؛ ${document.chunk_count} قطعه ساخته شد.`, "success");
    } catch (error) { message("#workspace-message", error.message, "error"); }
  });

  $("#knowledge-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = String(new FormData(event.currentTarget).get("query") || "");
    try {
      const result = await api("/knowledge/search", { method: "POST", body: { query, limit: 10 } });
      renderRecords("#knowledge-results", result.results, (item) => {
        const card = recordCard(item.title, item.content, `${item.citation_ref} · ${item.source_ref} · ${item.trust_classification}`);
        return card;
      }, "نتیجه‌ای پیدا نشد.");
    } catch (error) { message("#workspace-message", error.message, "error"); }
  });
  $("#knowledge-list-button").addEventListener("click", () => loadKnowledge().catch((error) => message("#workspace-message", error.message, "error")));

  $("#inference-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const mode = submitter && submitter.dataset.mode === "remote" ? "remote" : "local";
    const inputText = String(new FormData(event.currentTarget).get("input_text") || "");
    const output = $("#inference-result");
    output.textContent = mode === "remote" ? "در حال ارسال صریح به OpenRouter…" : "در حال اجرای مدل محلی…";
    try {
      const result = await api(mode === "remote" ? "/models/generate-remote" : "/models/generate", {
        method: "POST",
        body: { input_text: inputText },
      });
      output.textContent = `Provider: ${result.provider}\nModel: ${result.model}\n\n${result.output_text}`;
    } catch (error) {
      output.textContent = error.message;
    }
  });

  if (token) {
    setAuthenticated(true);
    refreshAll().catch((error) => message("#workspace-message", error.message, "error"));
  } else {
    setAuthenticated(false);
  }
})();
