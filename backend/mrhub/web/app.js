(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const tokenKey = "mrh_session_token";
  let token = sessionStorage.getItem(tokenKey);
  let mediaAssetsCache = [];
  let activeModelRunWorkflowId = null;
  let pendingModelRunIdempotencyKey = null;
  let pendingModelRunPayloadFingerprint = null;
  let activeVideoAnalysisId = sessionStorage.getItem("mrh_video_analysis_id");
  let activeVideoRenderId = sessionStorage.getItem("mrh_video_render_id");
  let activeVideoRenderAnalysisId = sessionStorage.getItem("mrh_video_render_analysis_id");
  let pendingVideoRenderKey = sessionStorage.getItem("mrh_video_render_pending_key");
  let pendingVideoRenderAnalysisId = sessionStorage.getItem("mrh_video_render_pending_analysis_id");
  let activeVideoRenderStatus = null;
  let activeVideoRenderAssetId = null;
  let canSubmitVideoRender = false;
  if (!token) {
    sessionStorage.removeItem("mrh_video_analysis_id");
    sessionStorage.removeItem("mrh_video_render_id");
    sessionStorage.removeItem("mrh_video_render_analysis_id");
    sessionStorage.removeItem("mrh_video_render_pending_key");
    sessionStorage.removeItem("mrh_video_render_pending_analysis_id");
    activeVideoAnalysisId = null;
    activeVideoRenderId = null;
    activeVideoRenderAnalysisId = null;
    pendingVideoRenderKey = null;
    pendingVideoRenderAnalysisId = null;
  }
  let pendingVideoAnalysisKey = null;
  let pendingVideoAnalysisFingerprint = null;
  let videoPromptResults = [];
  let videoTimelineDrafts = [];
  let activeVideoTimelineDraft = null;

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
    sessionStorage.removeItem("mrh_video_analysis_id");
    activeVideoAnalysisId = null;
    canSubmitVideoRender = false;
    clearVideoRenderState();
    pendingVideoAnalysisKey = null;
    pendingVideoAnalysisFingerprint = null;
    videoPromptResults = [];
    videoTimelineDrafts = [];
    activeVideoTimelineDraft = null;
    $("#video-storyboard-panel").hidden = true;
    $("#video-storyboard-beats").replaceChildren();
    $("#video-analysis-result").replaceChildren();
    $("#video-prompt-output").value = "";
    $("#video-prompt-timeline").replaceChildren();
    $("#video-analysis-refresh").disabled = true;
    $("#video-prompt-source").replaceChildren(element("option", "پس از تکمیل تحلیل فعال می‌شود"));
    $("#video-prompt-source").disabled = true;
    $("#video-compose-prompt").disabled = true;
    $("#video-copy-prompt").disabled = true;
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

  async function downloadMediaAsset(assetId, filename = "media") {
    if (!token) throw new Error("نشست فعال برای دریافت رسانه وجود ندارد.");
    const response = await fetch(
      "/content/assets/" + encodeURIComponent(assetId) + "/file",
      {
        headers: { Authorization: "Bearer " + token },
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
      }
    );
    if (response.status === 401 || response.status === 403) endSession();
    if (!response.ok) {
      throw new Error("دریافت رسانه ناموفق بود (HTTP " + response.status + ")");
    }
    const blob = await response.blob();
    if (!blob.size || blob.size > 100_000_000) {
      throw new Error("اندازهٔ فایل رسانه خارج از محدودهٔ مجاز است.");
    }
    const objectUrl = URL.createObjectURL(blob);
    const link = element("a", "");
    link.href = objectUrl;
    link.download = filename || "media";
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  }

  async function loadMediaAssets() {
    const response = await api("/content/assets?limit=100");
    mediaAssetsCache = Array.isArray(response.assets) ? response.assets : [];
    updateVideoAssetOptions();
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
      const download = element("button", "دانلود رسانه", "button button-quiet");
      download.type = "button";
      download.addEventListener("click", async () => {
        try {
          await downloadMediaAsset(asset.asset_id, asset.original_filename || "media");
          message("#media-message", "دانلود رسانه آغاز شد.", "success");
        } catch (error) {
          message("#media-message", error.message, "error");
        }
      });
      card.append(download);
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

  function updateVideoAssetOptions() {
    const select = $("#video-analysis-assets");
    if (!select) return;
    const selected = new Set(Array.from(select.selectedOptions).map((option) => option.value));
    const videos = mediaAssetsCache.filter((asset) =>
      ["video/mp4", "video/quicktime"].includes(asset.media_type)
    );
    select.replaceChildren();
    if (!videos.length) {
      const option = element("option", "ویدئوی MP4 در کتابخانه وجود ندارد");
      option.value = "";
      option.disabled = true;
      select.append(option);
      return;
    }
    for (const asset of videos) {
      const option = element(
        "option",
        `${asset.original_filename} · ${(Number(asset.file_size || 0) / (1024 * 1024)).toFixed(1)} MB`
      );
      option.value = asset.asset_id;
      option.selected = selected.has(asset.asset_id);
      select.append(option);
    }
  }

  function renderVideoAnalysis(analysis) {
    const container = $("#video-analysis-result");
    container.replaceChildren();
    const labels = {
      accepted: "در صف اجرا",
      running: "در حال تحلیل",
      completed: "تحلیل تکمیل شد",
      failed: "تحلیل ناموفق",
      cancelled: "لغو شد",
    };
    const statusText = labels[analysis.status] || analysis.status || "نامشخص";
    container.append(recordCard(
      "وضعیت Job",
      statusText,
      `شناسه: ${analysis.analysis_id || activeVideoAnalysisId} · آخرین به‌روزرسانی: ${analysis.updated_at || "نامشخص"}`
    ));

    const result = analysis.result;
    const semantic = result && result.semantic_visual_analysis;
    const canCompose = analysis.status === "completed"
      && semantic && semantic.status === "completed"
      && Array.isArray(semantic.assets)
      && semantic.assets.length > 0
      && semantic.assets.every((asset) => asset.status === "completed");
    const source = $("#video-prompt-source");
    const previousAssetId = source.value;
    source.replaceChildren();
    if (canCompose) {
      for (const asset of semantic.assets) {
        const media = mediaAssetsCache.find((item) => item.asset_id === asset.asset_id);
        const option = element("option", media ? media.original_filename : asset.asset_id);
        option.value = asset.asset_id;
        source.append(option);
      }
      source.disabled = false;
      if (semantic.assets.some((asset) => asset.asset_id === previousAssetId)) {
        source.value = previousAssetId;
      }
    } else {
      const option = element(
        "option",
        analysis.status === "completed"
          ? "تحلیل معنایی معتبر در دسترس نیست"
          : "پس از تکمیل تحلیل فعال می‌شود"
      );
      option.value = "";
      source.append(option);
      source.disabled = true;
    }
    $("#video-compose-prompt").disabled = !canCompose;
    $("#video-copy-prompt").disabled = true;
    $("#video-prompt-output").value = "";
    $("#video-prompt-timeline").replaceChildren();
    videoPromptResults = [];

    if (result) {
      const assets = Array.isArray(result.assets) ? result.assets : [];
      for (const asset of assets) {
        const technical = asset.technical_metadata || {};
        container.append(recordCard(
          mediaAssetsCache.find((item) => item.asset_id === asset.asset_id)?.original_filename || asset.asset_id,
          `وضعیت فنی: ${technical.metadata_status || "نامشخص"} · فریم نمونه: ${asset.keyframe_count ?? "—"} · مرزهای صحنه: ${Array.isArray(asset.scene_start_timestamps) ? asset.scene_start_timestamps.length : 0}`,
          `مدت بررسی: ${asset.analysis_window_seconds ?? "—"} ثانیه · تحلیل صوت: ${asset.audio_analysis || result.audio_analysis || "انجام نشده"}`
        ));
      }
      const semanticLabel = semantic ? semantic.status : "unavailable";
      container.append(element(
        "p",
        `تحلیل معنایی: ${semanticLabel}. تحلیل صوتی در این مسیر اجرا نمی‌شود؛ رندر MP4 بی‌صدا و برش مستقیم در بخش جداگانه در دسترس است.`,
        "muted"
      ));
    } else if (analysis.error_code) {
      container.append(element("p", `کد خطا: ${analysis.error_code}`, "message error"));
    }
    $("#video-analysis-refresh").disabled = !activeVideoAnalysisId;
    const timeline = result && result.timeline;
    canSubmitVideoRender = analysis.status === "completed"
      && timeline && Array.isArray(timeline.video_track) && timeline.video_track.length > 0;
    $("#video-render-submit").disabled = !canSubmitVideoRender
      || (Boolean(activeVideoRenderId) && !activeVideoRenderStatus)
      || ["accepted", "running"].includes(activeVideoRenderStatus);
  }

  function clearVideoRenderState() {
    activeVideoRenderId = null;
    activeVideoRenderAnalysisId = null;
    activeVideoRenderStatus = null;
    activeVideoRenderAssetId = null;
    pendingVideoRenderKey = null;
    pendingVideoRenderAnalysisId = null;
    sessionStorage.removeItem("mrh_video_render_id");
    sessionStorage.removeItem("mrh_video_render_analysis_id");
    sessionStorage.removeItem("mrh_video_render_pending_key");
    sessionStorage.removeItem("mrh_video_render_pending_analysis_id");
    $("#video-render-result").replaceChildren();
    $("#video-render-refresh").disabled = true;
    $("#video-render-cancel").disabled = true;
    $("#video-render-submit").disabled = !canSubmitVideoRender;
    message("#video-render-message", "");
  }

  const videoRenderStatusLabels = {
    accepted: "در صف اجرا",
    running: "در حال رندر",
    completed: "رندر تکمیل شد",
    failed: "رندر ناموفق",
    cancelled: "لغو شد",
  };

  function renderVideoRender(render) {
    activeVideoRenderStatus = render.status || null;
    activeVideoRenderAssetId = render.output_asset_id || null;
    const container = $("#video-render-result");
    container.replaceChildren();
    const statusText = videoRenderStatusLabels[render.status] || render.status || "نامشخص";
    container.append(recordCard(
      "وضعیت رندر",
      statusText,
      "شناسه: " + (render.render_id || activeVideoRenderId || "—")
        + " · آخرین به‌روزرسانی: " + (render.updated_at || "نامشخص")
    ));
    if (render.error_code) {
      container.append(element("p", "کد خطا: " + render.error_code, "message error"));
    }
    if (render.status === "completed" && activeVideoRenderAssetId) {
      const download = element("button", "دریافت فایل MP4", "button button-primary");
      download.type = "button";
      download.addEventListener("click", downloadRenderedVideo);
      container.append(download);
      container.append(element("p", "شناسهٔ رسانهٔ خروجی: " + activeVideoRenderAssetId, "muted"));
    }
    const active = ["accepted", "running"].includes(render.status);
    $("#video-render-refresh").disabled = !activeVideoRenderId;
    $("#video-render-cancel").disabled = !active;
    $("#video-render-submit").disabled = !canSubmitVideoRender || active;
  }

  async function refreshVideoRender() {
    if (!activeVideoRenderId) {
      message("#video-render-message", "هنوز درخواست رندری ثبت نشده است.", "error");
      return;
    }
    try {
      const render = await api("/video-intelligence/renders/" + encodeURIComponent(activeVideoRenderId));
      renderVideoRender(render);
      const statusText = render.status === "completed"
        ? "فایل MP4 آمادهٔ دریافت است."
        : render.status === "failed"
          ? "رندر ناموفق بود: " + (render.error_code || "خطای نامشخص")
          : render.status === "cancelled"
            ? "رندر لغو شد."
            : "وضعیت فعلی: " + (videoRenderStatusLabels[render.status] || render.status) + ".";
      message("#video-render-message", statusText, render.status === "failed" ? "error" : "success");
    } catch (error) {
      message("#video-render-message", error.message, "error");
    }
  }

  async function submitVideoRender() {
    if (!activeVideoAnalysisId || !canSubmitVideoRender) {
      message("#video-render-message", "ابتدا تحلیل کامل با Timeline معتبر لازم است.", "error");
      return;
    }
    if (!pendingVideoRenderKey || pendingVideoRenderAnalysisId !== activeVideoAnalysisId) {
      if (!window.crypto || typeof window.crypto.randomUUID !== "function") {
        message("#video-render-message", "مرورگر از تولید شناسهٔ امن درخواست پشتیبانی نمی‌کند.", "error");
        return;
      }
      pendingVideoRenderKey = window.crypto.randomUUID();
      pendingVideoRenderAnalysisId = activeVideoAnalysisId;
      sessionStorage.setItem("mrh_video_render_pending_key", pendingVideoRenderKey);
      sessionStorage.setItem("mrh_video_render_pending_analysis_id", pendingVideoRenderAnalysisId);
    }
    const button = $("#video-render-submit");
    button.disabled = true;
    message("#video-render-message", "در حال ثبت Job رندر در صف Worker…");
    try {
      const accepted = await api(
        "/video-intelligence/analyses/" + encodeURIComponent(activeVideoAnalysisId) + "/renders",
        { method: "POST", headers: { "Idempotency-Key": pendingVideoRenderKey } }
      );
      activeVideoRenderId = accepted.render_id;
      activeVideoRenderAnalysisId = activeVideoAnalysisId;
      sessionStorage.setItem("mrh_video_render_id", activeVideoRenderId);
      sessionStorage.setItem("mrh_video_render_analysis_id", activeVideoRenderAnalysisId);
      pendingVideoRenderKey = null;
      pendingVideoRenderAnalysisId = null;
      sessionStorage.removeItem("mrh_video_render_pending_key");
      sessionStorage.removeItem("mrh_video_render_pending_analysis_id");
      renderVideoRender(accepted);
      message(
        "#video-render-message",
        accepted.created === false
          ? "درخواست قبلی بازیابی شد؛ Job تکراری ساخته نشد."
          : "درخواست ثبت شد. Worker باید فعال باشد تا رندر اجرا شود.",
        "success"
      );
      await refreshVideoRender();
    } catch (error) {
      message("#video-render-message", error.message + "؛ در تلاش مجدد، کلید idempotency حفظ می‌شود.", "error");
    } finally {
      button.disabled = !canSubmitVideoRender || ["accepted", "running"].includes(activeVideoRenderStatus);
    }
  }

  async function cancelVideoRender() {
    if (!activeVideoRenderId) return;
    if (!window.confirm("درخواست لغو رندر ثبت شود؟ رندر در حال اجرا ممکن است پس از پایان پردازش فعلی متوقف شود.")) return;
    const button = $("#video-render-cancel");
    button.disabled = true;
    try {
      const result = await api(
        "/video-intelligence/renders/" + encodeURIComponent(activeVideoRenderId),
        { method: "DELETE" }
      );
      renderVideoRender(result);
      await refreshVideoRender();
      if (result.cancellation_requested) {
        message(
          "#video-render-message",
          "درخواست لغو ثبت شد؛ Worker پس از مشاهدهٔ آن عملیات را نهایی می‌کند.",
          "success"
        );
      }
    } catch (error) {
      message("#video-render-message", error.message, "error");
      button.disabled = false;
    }
  }

  async function downloadRenderedVideo() {
    if (!activeVideoRenderAssetId) return;
    try {
      await downloadMediaAsset(activeVideoRenderAssetId, "mrhub-render.mp4");
      message("#video-render-message", "دانلود فایل MP4 آغاز شد.", "success");
    } catch (error) {
      message("#video-render-message", error.message, "error");
    }
  }

  async function refreshVideoAnalysis() {
    if (!activeVideoAnalysisId) {
      message("#video-analysis-message", "هنوز درخواست تحلیلی ثبت نشده است.", "error");
      return;
    }
    try {
      const analysis = await api(`/video-intelligence/analyses/${encodeURIComponent(activeVideoAnalysisId)}`);
      renderVideoAnalysis(analysis);
      if (activeVideoRenderId && activeVideoRenderAnalysisId === activeVideoAnalysisId) {
        await refreshVideoRender();
      } else if (activeVideoRenderId && activeVideoRenderAnalysisId !== activeVideoAnalysisId) {
        clearVideoRenderState();
      }
      const statusText = analysis.status === "completed"
        ? "تحلیل پایان یافت. وضعیت تحلیل معنایی را بررسی کنید."
        : analysis.status === "failed"
          ? `تحلیل ناموفق بود: ${analysis.error_code || "خطای نامشخص"}`
          : `وضعیت فعلی: ${analysis.status}. برای بررسی مجدد، دکمهٔ وضعیت را بزنید.`;
      message("#video-analysis-message", statusText, analysis.status === "failed" ? "error" : "success");
    } catch (error) {
      message("#video-analysis-message", error.message, "error");
    }
  }

  async function submitVideoAnalysis(event) {
    event.preventDefault();
    const selectedIds = Array.from($("#video-analysis-assets").selectedOptions)
      .map((option) => option.value)
      .filter(Boolean);
    if (selectedIds.length < 1 || selectedIds.length > 5) {
      message("#video-analysis-message", "بین ۱ تا ۵ ویدئو انتخاب کنید.", "error");
      return;
    }
    const duration = Number($("#video-analysis-duration").value);
    if (!Number.isInteger(duration) || duration < 3 || duration > 60) {
      message("#video-analysis-message", "مدت بررسی باید عدد صحیح بین ۳ تا ۶۰ ثانیه باشد.", "error");
      return;
    }
    const payload = {
      mode: $("#video-analysis-mode").value,
      source_asset_ids: selectedIds,
      duration_seconds: duration,
      output_aspect_ratio: $("#video-analysis-aspect").value,
      include_audio_analysis: false,
    };
    const fingerprint = JSON.stringify(payload);
    if (!pendingVideoAnalysisKey || pendingVideoAnalysisFingerprint !== fingerprint) {
      if (!window.crypto || typeof window.crypto.randomUUID !== "function") {
        message("#video-analysis-message", "مرورگر از تولید شناسهٔ امن درخواست پشتیبانی نمی‌کند.", "error");
        return;
      }
      pendingVideoAnalysisKey = window.crypto.randomUUID();
      pendingVideoAnalysisFingerprint = fingerprint;
    }
    const button = $("#video-analysis-submit");
    button.disabled = true;
    message("#video-analysis-message", "در حال ثبت درخواست امن در صف Worker…");
    try {
      const accepted = await api("/video-intelligence/analyses", {
        method: "POST",
        headers: { "Idempotency-Key": pendingVideoAnalysisKey },
        body: payload,
      });
      activeVideoAnalysisId = accepted.analysis_id;
      sessionStorage.setItem("mrh_video_analysis_id", activeVideoAnalysisId);
      canSubmitVideoRender = false;
      clearVideoRenderState();
      pendingVideoAnalysisKey = null;
      pendingVideoAnalysisFingerprint = null;
      videoPromptResults = [];
      videoTimelineDrafts = [];
      activeVideoTimelineDraft = null;
      $("#video-storyboard-panel").hidden = true;
      $("#video-storyboard-beats").replaceChildren();
      $("#video-prompt-output").value = "";
      $("#video-prompt-source").replaceChildren(element("option", "پس از تکمیل تحلیل فعال می‌شود"));
      $("#video-prompt-source").disabled = true;
      $("#video-compose-prompt").disabled = true;
      $("#video-copy-prompt").disabled = true;
      $("#video-analysis-refresh").disabled = false;
      message(
        "#video-analysis-message",
        accepted.created === false ? "درخواست قبلی بازیابی شد؛ شناسهٔ تکراری ساخته نشد." : "درخواست ثبت شد. Worker باید فعال باشد تا تحلیل اجرا شود.",
        "success"
      );
      await refreshVideoAnalysis();
    } catch (error) {
      message("#video-analysis-message", `${error.message}؛ در صورت تلاش مجدد با همین ورودی، همان کلید idempotency حفظ می‌شود.`, "error");
    } finally {
      button.disabled = false;
    }
  }

  function renderSelectedVideoPrompt() {
    const assetId = $("#video-prompt-source").value;
    const selected = videoPromptResults.find((item) => item.asset_id === assetId);
    const output = $("#video-prompt-output");
    const timeline = $("#video-prompt-timeline");
    timeline.replaceChildren();
    if (!selected) {
      output.value = "";
      $("#video-copy-prompt").disabled = true;
      $("#video-storyboard-panel").hidden = true;
      return;
    }
    output.value = selected.prompt;
    $("#video-copy-prompt").disabled = !selected.prompt;
    for (const beat of selected.timeline || []) {
      const sourceTime = Number.isFinite(Number(beat.source_timestamp_seconds))
        ? "Timestamp منبع: " + Number(beat.source_timestamp_seconds).toFixed(3) + "s"
        : "Timestamp منبع تعیین نشده است.";
      timeline.append(recordCard(
        "Beat " + Number(beat.start_seconds).toFixed(2) + "s – " + Number(beat.end_seconds).toFixed(2) + "s",
        sourceTime,
        beat.confidence === undefined ? "بازهٔ زمانی Storyboard" : "Confidence: " + Number(beat.confidence).toFixed(2)
      ));
    }
    const savedDraft = activeVideoTimelineDraft && activeVideoTimelineDraft.asset_id === assetId
      ? activeVideoTimelineDraft
      : videoTimelineDrafts.find((item) => item.asset_id === assetId) || null;
    activeVideoTimelineDraft = savedDraft;
    renderVideoStoryboardDraftOptions(assetId);
    $("#video-storyboard-duration").value = String(
      savedDraft ? savedDraft.duration_seconds : selected.duration_seconds
    );
    $("#video-prompt-aspect-ratio").value = savedDraft
      ? savedDraft.aspect_ratio
      : (selected.aspect_ratio || $("#video-prompt-aspect-ratio").value);
    renderVideoStoryboardEditor(savedDraft ? savedDraft.beats : selected.beats);
    $("#video-storyboard-panel").hidden = false;
    $("#video-storyboard-new").disabled = false;
    $("#video-storyboard-add-beat").disabled = false;
    $("#video-storyboard-save").disabled = false;
    $("#video-storyboard-compose").disabled = false;
  }

  async function composeVideoPrompt(timelineDraft = null) {
    if (!activeVideoAnalysisId) return;
    const button = $("#video-compose-prompt");
    button.disabled = true;
    message("#video-prompt-message", timelineDraft
      ? "در حال ساخت Prompt از نسخهٔ دقیق Storyboard ذخیره‌شده…"
      : "در حال ساخت Prompt از مشاهدات معتبر…");
    try {
      const response = await api(
        `/video-intelligence/analyses/${encodeURIComponent(activeVideoAnalysisId)}/prompts/compose`,
        {
          method: "POST",
          body: {
            aspect_ratio: $("#video-prompt-aspect-ratio").value,
            ...(timelineDraft ? {
              timeline_draft_id: timelineDraft.draft_id,
              timeline_draft_version: timelineDraft.version,
            } : {}),
          },
        }
      );
      videoPromptResults = Array.isArray(response.prompts) ? response.prompts : [];
      const source = $("#video-prompt-source");
      const previousAssetId = source.value;
      if (videoPromptResults.length) {
        source.replaceChildren();
        for (const item of videoPromptResults) {
          const media = mediaAssetsCache.find((asset) => asset.asset_id === item.asset_id);
          const option = element(media ? media.original_filename : item.asset_id);
          option.value = item.asset_id;
          source.append(option);
        }
        source.disabled = false;
        source.value = videoPromptResults.some((item) => item.asset_id === previousAssetId)
          ? previousAssetId
          : videoPromptResults[0].asset_id;
        renderSelectedVideoPrompt();
        await loadVideoTimelineDrafts();
        message("#video-prompt-message", timelineDraft
          ? videoPromptResults.length + " Prompt ساخته شد؛ Storyboard نسخه " + timelineDraft.version + " اعمال شد و هیچ Provider اجرا نشد."
          : videoPromptResults.length + " Prompt مستقل از تحلیل ساخته شد؛ Storyboard ذخیره‌شده اعمال نشد و هیچ Provider اجرا نشد.", "success");
      } else {
        message("#video-prompt-message", "تحلیل معنایی معتبر برای ساخت Prompt وجود ندارد.", "error");
      }
    } catch (error) {
      message("#video-prompt-message", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function copyVideoPrompt() {
    const value = $("#video-prompt-output").value;
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      message("#video-prompt-message", "Prompt کپی شد.", "success");
    } catch {
      message("#video-prompt-message", "دسترسی Clipboard در این مرورگر فعال نیست؛ متن را دستی کپی کنید.", "error");
    }
  }

  function renderVideoStoryboardDraftOptions(assetId) {
    const select = $("#video-storyboard-draft-select");
    const matching = videoTimelineDrafts.filter((draft) => draft.asset_id === assetId);
    select.replaceChildren();
    if (!matching.length) {
      select.append(element("option", "برای این ویدئو Storyboard ذخیره‌شده‌ای وجود ندارد"));
      select.value = "";
      select.disabled = true;
      return;
    }
    select.append(element("option", "Storyboard ذخیره‌شده را انتخاب کنید"));
    for (const draft of matching) {
      const option = element("option", "نسخه " + draft.version + " · " + draft.updated_at);
      option.value = draft.draft_id;
      select.append(option);
    }
    select.disabled = false;
    if (activeVideoTimelineDraft && activeVideoTimelineDraft.asset_id === assetId) {
      select.value = activeVideoTimelineDraft.draft_id;
    } else {
      select.value = "";
    }
  }

  function renderVideoStoryboardEditor(beats) {
    const container = $("#video-storyboard-beats");
    container.replaceChildren();
    if (!Array.isArray(beats) || !beats.length) {
      renderEmpty(container, "برای شروع، Prompt فعلی را به Storyboard تبدیل کنید.");
      return;
    }
    for (const [index, beat] of beats.entries()) {
      const card = element("article", undefined, "record");
      const header = element("div", undefined, "record-head");
      header.append(element("strong", "Beat " + (index + 1)));
      card.append(header);
      const grid = element("div", undefined, "form-grid");
      const addField = (labelText, fieldName, value, type, attributes = {}) => {
        const label = element("label", labelText);
        const control = document.createElement(type === "textarea" ? "textarea" : "input");
        if (type !== "textarea") control.type = type;
        control.dataset.storyboardField = fieldName;
        control.value = value === null || value === undefined ? "" : String(value);
        for (const [key, attributeValue] of Object.entries(attributes)) {
          control.setAttribute(key, String(attributeValue));
        }
        label.append(control);
        grid.append(label);
      };
      addField("شروع (ثانیه)", "start_seconds", beat.start_seconds, "number", { min: 0, max: 60, step: 0.1, required: true });
      addField("پایان (ثانیه)", "end_seconds", beat.end_seconds, "number", { min: 0, max: 60, step: 0.1, required: true });
      addField("Timestamp منبع (اختیاری)", "source_timestamp_seconds", beat.source_timestamp_seconds, "number", { min: 0, max: 86400, step: 0.001 });
      addField("دستور بصری Beat", "generation_instruction", beat.generation_instruction, "textarea", { maxlength: 1200, rows: 3, required: true });
      addField("انتقال به Beat بعدی", "transition_to_next", beat.transition_to_next || "clean cinematic cut", "text", { maxlength: 240 });
      card.dataset.confidence = beat.confidence === null || beat.confidence === undefined ? "" : String(beat.confidence);
      const remove = deleteButton("حذف Beat", () => {
        card.remove();
        renumberVideoStoryboardBeats();
      });
      const actions = element("div", undefined, "button-row");
      actions.append(remove);
      card.append(grid, actions);
      container.append(card);
    }
    $("#video-storyboard-add-beat").disabled = beats.length >= 20;
  }

  function renumberVideoStoryboardBeats() {
    const cards = Array.from($("#video-storyboard-beats").querySelectorAll("article.record"));
    cards.forEach((card, index) => {
      const title = card.querySelector(".record-head strong");
      if (title) title.textContent = "Beat " + (index + 1);
    });
    $("#video-storyboard-add-beat").disabled = cards.length >= 20;
  }

  function readVideoStoryboardBeats() {
    const cards = Array.from($("#video-storyboard-beats").querySelectorAll("article.record"));
    return cards.map((card) => {
      const value = (name) => {
        const field = card.querySelector('[data-storyboard-field="' + name + '"]');
        return field ? field.value.trim() : "";
      };
      const beat = {
        start_seconds: Number(value("start_seconds")),
        end_seconds: Number(value("end_seconds")),
        generation_instruction: value("generation_instruction"),
        transition_to_next: value("transition_to_next") || "clean cinematic cut",
      };
      const sourceTimestamp = value("source_timestamp_seconds");
      beat.source_timestamp_seconds = sourceTimestamp === "" ? null : Number(sourceTimestamp);
      beat.confidence = card.dataset.confidence === "" ? null : Number(card.dataset.confidence);
      return beat;
    });
  }

  function addVideoStoryboardBeat() {
    const beats = readVideoStoryboardBeats();
    if (beats.length >= 20) {
      message("#video-storyboard-message", "حداکثر ۲۰ Beat مجاز است.", "error");
      return;
    }
    const duration = Number($("#video-storyboard-duration").value);
    const start = beats.length ? beats[beats.length - 1].end_seconds : 0;
    const end = Math.min(duration, start + 2);
    if (!Number.isFinite(duration) || end <= start) {
      message("#video-storyboard-message", "برای افزودن Beat، ابتدا مدت هدف را افزایش دهید.", "error");
      return;
    }
    beats.push({
      start_seconds: start,
      end_seconds: end,
      generation_instruction: "یک صحنهٔ اصیل با ترکیب‌بندی واضح بساز.",
      transition_to_next: "clean cinematic cut",
    });
    renderVideoStoryboardEditor(beats);
    message("#video-storyboard-message", "Beat جدید اضافه شد؛ برای اعمال آن Storyboard را ذخیره کنید.");
  }

  async function loadVideoTimelineDrafts() {
    if (!activeVideoAnalysisId) return;
    const response = await api(
      "/video-intelligence/analyses/" + encodeURIComponent(activeVideoAnalysisId) + "/timeline-drafts"
    );
    videoTimelineDrafts = Array.isArray(response.drafts) ? response.drafts : [];
    const assetId = $("#video-prompt-source").value;
    const existing = videoTimelineDrafts.find((draft) => draft.asset_id === assetId);
    if (existing && (!activeVideoTimelineDraft || activeVideoTimelineDraft.asset_id !== assetId)) {
      activeVideoTimelineDraft = existing;
    } else if (
      activeVideoTimelineDraft &&
      !videoTimelineDrafts.some((draft) => draft.draft_id === activeVideoTimelineDraft.draft_id)
    ) {
      activeVideoTimelineDraft = null;
    }
    if (assetId) renderSelectedVideoPrompt();
  }

  async function persistVideoStoryboardDraft() {
    const selected = videoPromptResults.find((item) => item.asset_id === $("#video-prompt-source").value);
    if (!activeVideoAnalysisId || !selected) throw new Error("ابتدا یک Prompt و ویدئوی منبع انتخاب کنید.");
    const duration = Number($("#video-storyboard-duration").value);
    const beats = readVideoStoryboardBeats();
    if (!Number.isInteger(duration) || duration < 3 || duration > 60) {
      throw new Error("مدت Storyboard باید عدد صحیح بین ۳ تا ۶۰ ثانیه باشد.");
    }
    if (!beats.length || beats.length > 20) {
      throw new Error("Storyboard باید بین ۱ تا ۲۰ Beat داشته باشد.");
    }
    const payload = {
      duration_seconds: duration,
      aspect_ratio: $("#video-prompt-aspect-ratio").value,
      beats,
    };
    const isUpdate = activeVideoTimelineDraft && activeVideoTimelineDraft.asset_id === selected.asset_id;
    if (
      isUpdate &&
      activeVideoTimelineDraft.duration_seconds === duration &&
      activeVideoTimelineDraft.aspect_ratio === payload.aspect_ratio &&
      JSON.stringify(activeVideoTimelineDraft.beats) === JSON.stringify(beats)
    ) {
      return activeVideoTimelineDraft;
    }
    const saved = isUpdate
      ? await api("/video-intelligence/timeline-drafts/" + encodeURIComponent(activeVideoTimelineDraft.draft_id), {
          method: "PUT",
          body: { ...payload, expected_version: activeVideoTimelineDraft.version },
        })
      : await api("/video-intelligence/timeline-drafts", {
          method: "POST",
          body: { ...payload, analysis_id: activeVideoAnalysisId, asset_id: selected.asset_id },
        });
    activeVideoTimelineDraft = saved;
    videoTimelineDrafts = videoTimelineDrafts.filter((draft) => draft.draft_id !== saved.draft_id);
    videoTimelineDrafts.unshift(saved);
    renderVideoStoryboardDraftOptions(selected.asset_id);
    message("#video-storyboard-message", "Storyboard نسخه " + saved.version + " ذخیره شد.", "success");
    return saved;
  }

  async function saveVideoStoryboardDraft() {
    const button = $("#video-storyboard-save");
    button.disabled = true;
    try {
      await persistVideoStoryboardDraft();
    } catch (error) {
      message("#video-storyboard-message", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function composeVideoPromptFromStoryboard() {
    const button = $("#video-storyboard-compose");
    button.disabled = true;
    try {
      const saved = await persistVideoStoryboardDraft();
      await composeVideoPrompt(saved);
      message("#video-storyboard-message", "Prompt با Storyboard نسخه " + saved.version + " ساخته شد؛ اجرای Provider آغاز نشده است.", "success");
    } catch (error) {
      message("#video-storyboard-message", error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function selectVideoStoryboardDraft() {
    const draftId = $("#video-storyboard-draft-select").value;
    const selected = videoTimelineDrafts.find((draft) => draft.draft_id === draftId);
    if (!selected) return;
    activeVideoTimelineDraft = selected;
    $("#video-storyboard-duration").value = String(selected.duration_seconds);
    $("#video-prompt-aspect-ratio").value = selected.aspect_ratio;
    renderVideoStoryboardEditor(selected.beats);
    message("#video-storyboard-message", "Storyboard نسخه " + selected.version + " بارگذاری شد.");
  }

  function startNewVideoStoryboard() {
    const selected = videoPromptResults.find((item) => item.asset_id === $("#video-prompt-source").value);
    if (!selected) return;
    activeVideoTimelineDraft = videoTimelineDrafts.find((draft) => draft.asset_id === selected.asset_id) || null;
    $("#video-storyboard-draft-select").value = activeVideoTimelineDraft
      ? activeVideoTimelineDraft.draft_id
      : "";
    $("#video-storyboard-duration").value = String(selected.duration_seconds);
    $("#video-prompt-aspect-ratio").value = selected.aspect_ratio || "9:16";
    renderVideoStoryboardEditor(selected.beats);
    message("#video-storyboard-message", activeVideoTimelineDraft
      ? "Beatها به Prompt فعلی بازنشانی شدند؛ ذخیره، نسخهٔ موجود را با کنترل نسخه به‌روزرسانی می‌کند."
      : "نسخهٔ اولیه از Beatهای Prompt فعلی ساخته شد؛ هنوز ذخیره نشده است.");
  }

  async function handleVideoPromptSourceChange() {
    activeVideoTimelineDraft = null;
    renderSelectedVideoPrompt();
    try {
      await loadVideoTimelineDrafts();
    } catch (error) {
      message("#video-storyboard-message", error.message, "error");
    }
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
      if (activeVideoAnalysisId) {
        $("#video-analysis-refresh").disabled = false;
        await refreshVideoAnalysis();
      } else {
        canSubmitVideoRender = false;
        clearVideoRenderState();
      }
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

  $("#video-analysis-form").addEventListener("submit", submitVideoAnalysis);
  $("#video-analysis-refresh").addEventListener("click", refreshVideoAnalysis);
  $("#video-render-submit").addEventListener("click", submitVideoRender);
  $("#video-render-refresh").addEventListener("click", refreshVideoRender);
  $("#video-render-cancel").addEventListener("click", cancelVideoRender);
  $("#video-compose-prompt").addEventListener("click", composeVideoPrompt);
  $("#video-prompt-source").addEventListener("change", handleVideoPromptSourceChange);
  $("#video-copy-prompt").addEventListener("click", copyVideoPrompt);
  $("#video-storyboard-draft-select").addEventListener("change", selectVideoStoryboardDraft);
  $("#video-storyboard-new").addEventListener("click", startNewVideoStoryboard);
  $("#video-storyboard-add-beat").addEventListener("click", addVideoStoryboardBeat);
  $("#video-storyboard-save").addEventListener("click", saveVideoStoryboardDraft);
  $("#video-storyboard-compose").addEventListener("click", composeVideoPromptFromStoryboard);

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
  $("#agent-history-refresh-button").addEventListener("click", loadAgentRunHistory);
  $("#agent-queued-workflow-id").addEventListener("input", (event) => {
    $("#agent-queued-refresh-button").disabled = !event.currentTarget.value.trim();
  });

  function readAgentRunPayload(form) {
    const values = new FormData(form);
    return {
      goal: String(values.get("goal") || ""),
      context_query: String(values.get("context_query") || "").trim() || null,
      provider_mode: String(values.get("provider_mode") || "local"),
      include_memory: form.elements.include_memory.checked,
      include_knowledge: form.elements.include_knowledge.checked,
      knowledge_freshness_policy: String(values.get("knowledge_freshness_policy") || "include_all"),
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
      const requestBody = readAgentRunPayload(form);
      const payloadFingerprint = JSON.stringify(requestBody);
      if (
        !pendingModelRunIdempotencyKey
        || pendingModelRunPayloadFingerprint !== payloadFingerprint
      ) {
        pendingModelRunIdempotencyKey = crypto.randomUUID();
        pendingModelRunPayloadFingerprint = payloadFingerprint;
      }
      const result = await api("/agent/model-runs", {
        method: "POST",
        headers: { "Idempotency-Key": pendingModelRunIdempotencyKey },
        body: requestBody,
      });
      pendingModelRunIdempotencyKey = null;
      pendingModelRunPayloadFingerprint = null;
      activeModelRunWorkflowId = result.workflow_id;
      $("#agent-queued-workflow-id").value = result.workflow_id;
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
    const workflowId = activeModelRunWorkflowId || $("#agent-queued-workflow-id").value.trim();
    if (!workflowId) return;
    activeModelRunWorkflowId = workflowId;
    const output = $("#agent-queued-result");
    try {
      const result = await api(
        "/agent/model-run-workflows/" + encodeURIComponent(workflowId)
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
    const workflowId = activeModelRunWorkflowId || $("#agent-queued-workflow-id").value.trim();
    if (!workflowId) return;
    activeModelRunWorkflowId = workflowId;
    if (!window.confirm("درخواست لغو اجرای صف‌شده ثبت شود؟")) return;
    try {
      const result = await api(
        "/agent/model-run-workflows/" + encodeURIComponent(workflowId) + "/cancel",
        { method: "POST" }
      );
      $("#agent-queued-result").textContent = "نتیجهٔ درخواست لغو: " + result.status;
      await refreshQueuedAgentRun();
    } catch (error) {
      message("#workspace-message", error.message, "error");
    }
  }


  async function loadAgentRunHistory() {
    const output = $("#agent-history-result");
    const container = $("#agent-run-history");
    output.textContent = "در حال دریافت تاریخچهٔ اجراها…";
    container.replaceChildren();
    try {
      const result = await api("/agent/model-runs?limit=20");
      const runs = Array.isArray(result.runs) ? result.runs : [];
      for (const run of runs) {
        const metadata = run.metadata || {};
        const details = [
          "Provider: " + (metadata.selected_provider || "—"),
          "حالت: " + (metadata.provider_mode || "—"),
          "نوبت‌ها: " + (metadata.turns ?? "—"),
          "فراخوانی ابزار: " + (metadata.tool_calls ?? "—"),
          "تعداد منابع: " + (metadata.context_passage_count ?? "—"),
        ].join(" · ");
        container.append(recordCard(
          (run.outcome || "unknown") + " · " + (run.run_id || "بدون شناسه"),
          "",
          (run.created_at || "زمان نامشخص") + " · " + details
        ));
      }
      output.textContent = runs.length
        ? "تعداد اجراهای ثبت‌شده: " + (result.count ?? runs.length) + " · فقط فرادادهٔ مجاز نمایش داده می‌شود."
        : "هنوز سابقه‌ای برای نمایش وجود ندارد.";
    } catch (error) {
      output.textContent = error.message;
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
          knowledge_freshness_policy: String(
            values.get("knowledge_freshness_policy") || "include_all"
          ),
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
        "سیاست تازگی اسناد: " + result.knowledge_freshness_policy,
        "اسناد stale حذف‌شده: " + (result.excluded_stale_knowledge_count ?? 0),
        "اسناد بازبینی‌نشده حذف‌شده: " + (result.excluded_unreviewed_knowledge_count ?? 0),
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
