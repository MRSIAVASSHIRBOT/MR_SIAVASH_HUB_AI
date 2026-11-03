(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const tokenKey = "mrh_session_token";
  let token = sessionStorage.getItem(tokenKey);
  let mediaAssetsCache = [];
  let activeModelRunWorkflowId = null;

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

  function actionButton(label, onAction) {
    const button = element("button", label, "button button-secondary");
    button.type = "button";
    button.addEventListener("click", onAction);
    return button;
  }

  function renderJobSummary(summary) {
    const counts = summary.status_counts || {};
    const workflowCounts = summary.workflow_status_counts || {};
    const entries = [
      ["کل وظایف", summary.total_tasks ?? 0],
      ["در صف", counts.queued ?? 0],
      ["در حال اجرا", counts.running ?? 0],
      ["نیازمند تأیید", counts.waiting_approval ?? 0],
      ["موفق", counts.succeeded ?? 0],
      ["ناموفق", counts.failed ?? 0],
      ["تلاش مجدد", summary.retry_scheduled ?? 0],
      ["نیازمند بازیابی", summary.recovery_required_workflows ?? 0],
      ["Lease منقضی", summary.expired_running_leases ?? 0],
      ["قدیمی‌ترین صف (ثانیه)", summary.oldest_queued_age_seconds ?? "—"],
      ["حالت اجرا", summary.execution_mode === "pull_driven" ? "Pull-driven" : "نامشخص"],
      ["اجرای خودکار", summary.automatic_execution ? "فعال" : "غیرفعال"],
    ];
    const container = $("#job-summary");
    container.replaceChildren();
    for (const [label, value] of entries) {
      const card = element("article", undefined, "status-card");
      card.append(element("small", label), element("strong", value));
      container.append(card);
    }
    const workflowTotal = Object.values(workflowCounts).reduce(
      (total, value) => total + Number(value || 0), 0
    );
    const card = element("article", undefined, "status-card");
    card.append(element("small", "کل Workflowها"), element("strong", workflowTotal));
    container.append(card);
  }

  function selectWorkflowForResume(workflowId) {
    $("#workflow-resume-form").elements.workflow_id.value = workflowId;
    $("#workflow-resume-form").scrollIntoView({ behavior: "smooth", block: "center" });
    $("#workflow-resume-form").elements.request_json.focus();
    message("#workflow-resume-message", "شناسه وارد شد؛ ورودی اصلی را دقیقاً وارد کنید.");
  }

  function selectWorkflowForReconciliation(workflow) {
    const step = workflow.steps.find((item) => item.status === "unknown_outcome");
    if (!step) return;
    const form = $("#workflow-reconciliation-form");
    form.elements.workflow_id.value = workflow.workflow_id;
    form.elements.step_number.value = String(step.step_number);
    form.scrollIntoView({ behavior: "smooth", block: "center" });
    message("#workflow-reconciliation-message", "مرحلهٔ دارای نتیجهٔ نامشخص انتخاب شد. ابتدا نتیجه را در سرویس مقصد مستقلاً بررسی کنید.");
  }

  function renderWorkflowCard(workflow) {
    const title = "Workflow · " + workflow.workflow_id.slice(0, 8);
    const metadata = [
      workflow.status,
      "مرحله " + workflow.current_step,
      workflow.last_error_code || "بدون خطای ثبت‌شده",
    ].join(" · ");
    const card = recordCard(title, workflow.workflow_id, metadata);
    const actions = element("div", undefined, "workflow-actions");
    actions.append(actionButton("جزئیات مراحل", async () => {
      try {
        const detail = await api("/agent/workflows/" + encodeURIComponent(workflow.workflow_id));
        const list = element("div", undefined, "workflow-step-list");
        for (const step of detail.steps || []) {
          const item = element("div", undefined, "workflow-step");
          item.append(
            element("strong", "مرحله " + step.step_number + " · " + step.step_name),
            element("span", step.status),
            element("small", "تلاش: " + step.attempt_count + " · " + (step.error_code || "بدون خطا"))
          );
          list.append(item);
        }
        const previous = card.querySelector(".workflow-step-list");
        if (previous) previous.remove();
        card.append(list);
      } catch (error) {
        message("#workspace-message", error.message, "error");
      }
    }));
    if (workflow.status === "paused") {
      actions.append(actionButton("آماده‌سازی ادامه", () => selectWorkflowForResume(workflow.workflow_id)));
    }
    if (workflow.status === "recovery_required") {
      actions.append(actionButton("تطبیق نتیجه", () => selectWorkflowForReconciliation(workflow)));
    }
    if (["queued", "running", "paused"].includes(workflow.status)) {
      actions.append(actionButton("لغو", async () => {
        if (!window.confirm("درخواست لغو این Workflow ثبت شود؟")) return;
        try {
          await api("/agent/workflows/" + encodeURIComponent(workflow.workflow_id) + "/cancel", { method: "POST" });
          await loadOverview();
        } catch (error) {
          message("#workspace-message", error.message, "error");
        }
      }));
    }
    card.append(actions);
    return card;
  }

  function readResumeInput() {
    const form = $("#workflow-resume-form");
    const workflowId = String(form.elements.workflow_id.value || "").trim();
    let request;
    try {
      request = JSON.parse(String(form.elements.request_json.value || ""));
    } catch {
      throw new Error("ورودی اصلی باید JSON معتبر باشد.");
    }
    if (!workflowId || !request || typeof request !== "object" || Array.isArray(request)) {
      throw new Error("شناسهٔ Workflow و یک شیء JSON معتبر لازم است.");
    }
    return { workflowId, request };
  }

  async function checkWorkflowResume() {
    try {
      const { workflowId, request } = readResumeInput();
      const result = await api(
        "/agent/workflows/" + encodeURIComponent(workflowId) + "/resume-check",
        { method: "POST", body: { request } }
      );
      message(
        "#workflow-resume-message",
        "تصمیم: " + result.decision + " · مرحلهٔ بعدی: " + (result.next_step ?? "—") + " · " + (result.reason_code || "بدون مانع"),
        result.decision === "resume" || result.decision === "finish" ? "success" : "error"
      );
    } catch (error) {
      message("#workflow-resume-message", error.message, "error");
    }
  }

  async function queueWorkflowResume(event) {
    event.preventDefault();
    try {
      const { workflowId, request } = readResumeInput();
      const result = await api(
        "/agent/workflows/" + encodeURIComponent(workflowId) + "/resume",
        { method: "POST", body: { request } }
      );
      message(
        "#workflow-resume-message",
        result.queued ? "درخواست ادامه در صف Worker قرار گرفت؛ اجرای مرحله‌ها در HTTP انجام نمی‌شود." : "درخواست ادامه ثبت شد.",
        "success"
      );
      await loadOverview();
    } catch (error) {
      message("#workflow-resume-message", error.message, "error");
    }
  }

  async function reconcileWorkflowOutcome(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const workflowId = String(form.get("workflow_id") || "").trim();
    const stepNumber = Number(form.get("step_number"));
    const outcome = String(form.get("outcome") || "");
    const digest = String(form.get("output_digest") || "").trim();
    if (outcome === "succeeded" && !/^[0-9a-f]{64}$/.test(digest)) {
      message("#workflow-reconciliation-message", "برای ثبت موفقیت، SHA-256 معتبر ۶۴ نویسه‌ای لازم است.", "error");
      return;
    }
    try {
      const result = await api(
        "/agent/workflows/" + encodeURIComponent(workflowId) + "/reconciliation",
        {
          method: "POST",
          body: {
            step_number: stepNumber,
            outcome,
            output_digest: outcome === "succeeded" ? digest : null,
          },
        }
      );
      message(
        "#workflow-reconciliation-message",
        "نتیجه ثبت شد؛ وضعیت Workflow: " + result.workflow.status + ". برای ادامه، ورودی اصلی را دوباره بررسی و ارسال کنید.",
        "success"
      );
      await loadOverview();
    } catch (error) {
      message("#workflow-reconciliation-message", error.message, "error");
    }
  }

  async function loadOverview() {
    message("#workspace-message", "در حال به‌روزرسانی…");
    const [health, ready, providers, tasks, jobs, workflows] = await Promise.allSettled([
      api("/health", { auth: false }),
      api("/ready", { auth: false }),
      api("/models/providers"),
      api("/tasks?limit=12"),
      api("/jobs/summary"),
      api("/agent/workflows?limit=50"),
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
      renderRecords("#task-list", tasks.value, (task) => {
        const card = recordCard(task.task_type, task.description, task.status + " · " + task.task_id);
        if (["queued", "running"].includes(task.status)) {
          card.append(actionButton("لغو وظیفه", async () => {
            if (!window.confirm("این وظیفه لغو شود؟")) return;
            try {
              await api("/jobs/" + encodeURIComponent(task.task_id) + "/cancel", { method: "POST" });
              await loadOverview();
            } catch (error) {
              message("#workspace-message", error.message, "error");
            }
          }));
        }
        return card;
      }, "هنوز کاری ثبت نشده است.");
    } else {
      renderEmpty($("#task-list"), "دریافت صف کارها ناموفق بود.");
    }
    if (jobs.status === "fulfilled") {
      renderJobSummary(jobs.value);
    } else {
      renderEmpty($("#job-summary"), "دریافت آمار Job Engine ناموفق بود.");
    }
    if (workflows.status === "fulfilled") {
      renderRecords("#workflow-list", workflows.value.workflows, renderWorkflowCard, "هنوز Workflowای ثبت نشده است.");
    } else {
      renderEmpty($("#workflow-list"), "دریافت گردش‌کارها ناموفق بود.");
    }
    const failures = [health, ready, providers, tasks, jobs, workflows].filter((item) => item.status === "rejected").length;
    message("#workspace-message", failures ? `به‌روزرسانی انجام شد؛ ${failures} بخش در دسترس نبود.` : "وضعیت به‌روز شد.", failures ? "error" : "success");
  }

  async function loadMediaAssets() {
    const response = await api("/content/assets?limit=100");
    mediaAssetsCache = Array.isArray(response.assets) ? response.assets : [];
    const select = $("#draft-media-select");
    const selected = select.value;
    select.replaceChildren(element("option", "بدون رسانه"));
    select.options[0].value = "";
    for (const asset of mediaAssetsCache) {
      const sizeMb = (Number(asset.file_size || 0) / (1024 * 1024)).toFixed(1);
      const option = element(
        "option",
        `${asset.original_filename} · ${asset.media_type} · ${sizeMb} MB`
      );
      option.value = asset.asset_id;
      select.append(option);
    }
    if (mediaAssetsCache.some((asset) => asset.asset_id === selected)) select.value = selected;
    updateMediaSelectAvailability();
    renderRecords("#media-asset-list", mediaAssetsCache, (asset) => {
      const sizeMb = (Number(asset.file_size || 0) / (1024 * 1024)).toFixed(1);
      const card = recordCard(
        asset.original_filename,
        asset.media_type,
        `${sizeMb} MB · ${asset.processing_status} · ${asset.asset_id}`
      );
      card.append(deleteButton("حذف رسانه", async () => {
        if (!window.confirm("این فایل رسانه‌ای حذف شود؟ اگر در تاریخچهٔ پیش‌نویس استفاده شده باشد، حذف رد می‌شود.")) return;
        try {
          await api(`/content/assets/${encodeURIComponent(asset.asset_id)}`, { method: "DELETE" });
          await loadMediaAssets();
          message("#media-message", "رسانه حذف شد.", "success");
        } catch (error) {
          message("#media-message", error.message, "error");
        }
      }));
      return card;
    }, "هنوز رسانه‌ای آپلود نشده است.");
    return mediaAssetsCache;
  }

  function updateMediaSelectAvailability() {
    const form = $("#content-draft-form");
    if (!form) return;
    const isTelegram = form.elements.platform.value === "telegram";
    const select = $("#draft-media-select");
    select.disabled = !isTelegram;
    if (!isTelegram) select.value = "";
    $("#media-attachment-help").textContent = isTelegram
      ? "فقط JPEG، PNG و MP4 تا ۲۵ مگابایت قابل پیوست‌اند؛ تغییر رسانه تأیید پیش‌نویس را باطل می‌کند."
      : "پیوست رسانه فعلاً فقط برای پیش‌نویس‌های Telegram پشتیبانی می‌شود.";
  }

  async function uploadSelectedMedia() {
    const input = $("#media-file-input");
    const file = input.files && input.files[0];
    if (!file) {
      message("#media-message", "ابتدا یک فایل انتخاب کنید.", "error");
      return;
    }
    const allowedTypes = new Set(["image/jpeg", "image/png", "video/mp4"]);
    if (!allowedTypes.has(file.type)) {
      message("#media-message", "فقط JPEG، PNG یا MP4 پذیرفته می‌شود.", "error");
      return;
    }
    if (file.size < 1 || file.size > 25_000_000) {
      message("#media-message", "اندازهٔ فایل باید بین ۱ بایت و ۲۵ مگابایت باشد.", "error");
      return;
    }
    message("#media-message", "در حال آپلود به فضای محلی…");
    const headers = new Headers({
      "Content-Type": file.type,
      "X-File-Name": file.name,
    });
    if (token) headers.set("Authorization", `Bearer ${token}`);
    try {
      const response = await fetch("/content/assets", {
        method: "POST",
        headers,
        body: file,
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
      });
      let payload = null;
      try { payload = await response.json(); } catch { payload = null; }
      if (response.status === 401 || response.status === 403) endSession();
      if (!response.ok) {
        const detail = payload && payload.detail;
        throw new Error(typeof detail === "string" ? detail : `آپلود ناموفق بود (HTTP ${response.status})`);
      }
      input.value = "";
      await loadMediaAssets();
      if ($("#draft-media-select").disabled === false) {
        $("#draft-media-select").value = payload.asset_id;
      }
      message("#media-message", "رسانه در فضای محلی ذخیره شد؛ هنوز چیزی منتشر نشده است.", "success");
    } catch (error) {
      message("#media-message", error.message, "error");
    }
  }

  async function loadContentDrafts() {
    const response = await api("/content/drafts?limit=100");
    renderRecords("#content-draft-list", response.drafts, (draft) => {
      const card = recordCard(
        draft.title,
        draft.body,
        `${draft.platform} · ${draft.content_type} · ${draft.status} · نسخه ${draft.version}${draft.media_asset_id ? " · دارای رسانه" : ""}`
      );
      const actions = element("div", undefined, "button-row");
      if (draft.status === "draft") {
        actions.append(actionButton("تأیید پیش‌نویس", async () => {
          try { await api(`/content/drafts/${encodeURIComponent(draft.draft_id)}/approve`, { method: "POST" }); await loadContentDrafts(); }
          catch (error) { message("#workspace-message", error.message, "error"); }
        }));
        actions.append(actionButton("بایگانی", async () => {
          try { await api(`/content/drafts/${encodeURIComponent(draft.draft_id)}/archive`, { method: "POST" }); await loadContentDrafts(); }
          catch (error) { message("#workspace-message", error.message, "error"); }
        }));
      } else if (draft.status === "approved") {
        actions.append(actionButton("لغو تأیید", async () => {
          try { await api(`/content/drafts/${encodeURIComponent(draft.draft_id)}/revoke-approval`, { method: "POST" }); await loadContentDrafts(); }
          catch (error) { message("#workspace-message", error.message, "error"); }
        }));
        actions.append(actionButton("بایگانی", async () => {
          try { await api(`/content/drafts/${encodeURIComponent(draft.draft_id)}/archive`, { method: "POST" }); await loadContentDrafts(); }
          catch (error) { message("#workspace-message", error.message, "error"); }
        }));
      } else {
        actions.append(actionButton("بازگردانی", async () => {
          try { await api(`/content/drafts/${encodeURIComponent(draft.draft_id)}/restore`, { method: "POST" }); await loadContentDrafts(); }
          catch (error) { message("#workspace-message", error.message, "error"); }
        }));
      }
      actions.append(deleteButton("حذف", async () => {
        if (!window.confirm("این پیش‌نویس و تاریخچهٔ آن حذف شوند؟")) return;
        try { await api(`/content/drafts/${encodeURIComponent(draft.draft_id)}`, { method: "DELETE" }); await loadContentDrafts(); }
        catch (error) { message("#workspace-message", error.message, "error"); }
      }));
      card.append(actions);
      return card;
    }, "هنوز پیش‌نویسی ثبت نشده است.");
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
      await Promise.all([loadOverview(), loadContentDrafts(), loadMediaAssets(), loadMemory(), loadKnowledge()]);
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

  $("#workflow-refresh-button").addEventListener("click", () =>
    loadOverview().catch((error) => message("#workspace-message", error.message, "error"))
  );
  $("#workflow-resume-check").addEventListener("click", checkWorkflowResume);
  $("#workflow-resume-form").addEventListener("submit", queueWorkflowResume);
  $("#workflow-reconciliation-form").addEventListener("submit", reconcileWorkflowOutcome);

  $("#logout-button").addEventListener("click", async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* Clear the browser token even if the API is unavailable. */ }
    endSession();
  });
  $("#refresh-button").addEventListener("click", refreshAll);

  $("#media-upload-button").addEventListener("click", uploadSelectedMedia);
  $("#media-refresh-button").addEventListener("click", () =>
    loadMediaAssets().catch((error) => message("#media-message", error.message, "error"))
  );
  $("#content-draft-form").elements.platform.addEventListener("change", updateMediaSelectAvailability);

  $("#content-draft-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const hashtags = String(form.get("hashtags") || "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
    try {
      await api("/content/drafts", {
        method: "POST",
        body: {
          title: form.get("title"),
          platform: form.get("platform"),
          content_type: form.get("content_type"),
          body: form.get("body"),
          hashtags,
          media_asset_id: String(form.get("media_asset_id") || "").trim() || null,
        },
      });
      event.currentTarget.reset();
      await loadContentDrafts();
      message("#workspace-message", "پیش‌نویس ذخیره شد؛ انتشار خودکار انجام نشده است.", "success");
    } catch (error) { message("#workspace-message", error.message, "error"); }
  });

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

  $("#agent-run-form").addEventListener("submit", runAgent);
  $("#agent-queue-button").addEventListener("click", queueAgentRun);
  $("#agent-queued-refresh-button").addEventListener("click", refreshQueuedAgentRun);
  $("#agent-queued-cancel-button").addEventListener("click", cancelQueuedAgentRun);

  function readAgentRunPayload(form) {
    const values = new FormData(form);
    return {
      goal: String(values.get("goal") || ""),
      context_query: String(values.get("context_query") || "").trim() || null,
      provider_mode: String(values.get("provider_mode") || "local"),
      include_memory: form.elements.include_memory.checked,
      include_knowledge: form.elements.include_knowledge.checked,
      max_turns: Number(values.get("max_turns") || 3),
      max_output_tokens: Number(values.get("max_output_tokens") || 512),
    };
  }

  async function queueAgentRun() {
    const form = $("#agent-run-form");
    if (!form.reportValidity()) return;
    const button = $("#agent-queue-button");
    const output = $("#agent-queued-result");
    button.disabled = true;
    output.textContent = "در حال ثبت درخواست در صف…";
    try {
      const result = await api("/agent/model-runs", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: readAgentRunPayload(form),
      });
      activeModelRunWorkflowId = result.workflow_id;
      $("#agent-queued-refresh-button").disabled = false;
      output.textContent = [
        "وضعیت: " + (result.status || "queued"),
        "Workflow: " + result.workflow_id,
        "Task: " + result.task_id,
        "شناسهٔ درخواست تکرارناپذیر ثبت شد.",
        "برای مشاهدهٔ نتیجه، وضعیت را دستی به‌روزرسانی کنید.",
      ].join("\n");
      await refreshQueuedAgentRun();
    } catch (error) {
      output.textContent = error.message;
      message("#workspace-message", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function refreshQueuedAgentRun() {
    if (!activeModelRunWorkflowId) return;
    const output = $("#agent-queued-result");
    try {
      const result = await api(
        "/agent/model-run-workflows/" + encodeURIComponent(activeModelRunWorkflowId)
      );
      const execution = result.result && result.result.execution
        ? result.result.execution
        : {};
      const step = (result.steps || [])[0] || {};
      output.textContent = [
        "وضعیت Workflow: " + result.status,
        "وضعیت مرحله: " + (step.status || "—"),
        "کد وضعیت: " + (result.last_error_code || "—"),
        "شناسه: " + result.workflow_id,
        execution.status ? "وضعیت اجرای مدل: " + execution.status : "",
        execution.selected_provider
          ? "ارائه‌دهنده: " + (execution.selected_provider.provider || "—")
          : "",
        execution.turns !== undefined ? "نوبت‌ها: " + execution.turns : "",
        execution.tool_calls !== undefined ? "فراخوانی ابزارها: " + execution.tool_calls : "",
        "",
        execution.answer || execution.error || (
          result.status === "recovery_required"
            ? "نتیجهٔ اجرا نامشخص است؛ سیستم آن را خودکار تکرار نمی‌کند."
            : "هنوز نتیجه‌ای ثبت نشده است."
        ),
      ].filter((line) => line !== "").join("\n");
      $("#agent-queued-cancel-button").hidden = !["queued", "running"].includes(result.status);
      message(
        "#workspace-message",
        "وضعیت اجرای صف‌شده به‌روزرسانی شد.",
        ["succeeded", "cancelled"].includes(result.status) ? "success" : ""
      );
    } catch (error) {
      output.textContent = error.message;
      message("#workspace-message", error.message, "error");
    }
  }

  async function cancelQueuedAgentRun() {
    if (!activeModelRunWorkflowId) return;
    if (!window.confirm("درخواست لغو اجرای صف‌شده ثبت شود؟")) return;
    try {
      const result = await api(
        "/agent/model-run-workflows/" + encodeURIComponent(activeModelRunWorkflowId) + "/cancel",
        { method: "POST" }
      );
      $("#agent-queued-result").textContent = "نتیجهٔ درخواست لغو: " + result.status;
      await refreshQueuedAgentRun();
    } catch (error) {
      message("#workspace-message", error.message, "error");
    }
  }

  async function runAgent(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const output = $("#agent-run-result");
    output.textContent = "در حال اجرای عامل با محدودیت زمان و نوبت…";
    $("#agent-run-sources").replaceChildren();
    const providerMode = String(values.get("provider_mode") || "local");
    try {
      const result = await api("/agent/run", {
        method: "POST",
        body: {
          goal: String(values.get("goal") || ""),
          context_query: String(values.get("context_query") || "").trim() || null,
          provider_mode: providerMode,
          include_memory: form.elements.include_memory.checked,
          include_knowledge: form.elements.include_knowledge.checked,
          max_turns: Number(values.get("max_turns") || 3),
          max_output_tokens: Number(values.get("max_output_tokens") || 512),
        },
      });
      const execution = result.execution || {};
      const selected = execution.selected_provider || {};
      output.textContent = [
        "وضعیت: " + (execution.status || "نامشخص"),
        "حالت ارائه‌دهنده: " + result.provider_mode,
        "Provider: " + (selected.provider || "—"),
        "Model: " + (selected.model || "—"),
        "نوبت‌ها: " + (execution.turns ?? 0),
        "فراخوانی ابزارها: " + (execution.tool_calls ?? 0),
        "",
        execution.answer || execution.error || "پاسخی تولید نشد.",
      ].join("\n");
      renderRecords(
        "#agent-run-sources",
        result.context_sources,
        (source) => recordCard(
          source.reference || "منبع بدون شناسه",
          source.source_ref || "",
          [
            source.trust_classification || "trust نامشخص",
            source.freshness_status || "freshness نامشخص",
            source.freshness_checked_at || "",
          ].filter(Boolean).join(" · ")
        ),
        "برای این درخواست منبعی بازیابی نشد."
      );
      message(
        "#workspace-message",
        execution.status === "completed" ? "اجرای عامل پایان یافت؛ هیچ انتشار یا اثر خارجی انجام نشد." : "اجرای عامل با وضعیت " + (execution.status || "نامشخص") + " پایان یافت.",
        execution.status === "completed" ? "success" : "error"
      );
    } catch (error) {
      output.textContent = error.message;
      message("#workspace-message", error.message, "error");
    }
  }

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
