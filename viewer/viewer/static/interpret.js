const state = {
  sessionId: null,
  pollTimer: null,
  result: null,
  brief: null,
  activeTab: "brief",
  llmCalls: [],
  pendingJobKind: "interpret",
};

const STAGES = ["pipeline_1", "pipeline_2", "merge", "interpret", "template"];
const BRIEF_STAGES = ["pipeline_1", "pipeline_2", "merge", "brief"];
const STAGE_LABELS = {
  pipeline_1: "提取文件 1",
  pipeline_2: "提取文件 2",
  merge: "合并工作区",
  brief: "提取概要",
  interpret: "解读招标",
  template: "提取模版",
};

const BRIEF_FIELD_LABELS = [
  { key: "issuer_company", label: "招标发起企业" },
  { key: "procurement_subject", label: "招标标的 / 采购内容" },
  { key: "budget_info", label: "预算 / 控制价" },
  { key: "qualification_requirements", label: "准入资质" },
  { key: "key_timelines", label: "工期与时间节点" },
];

const TABS = [
  { key: "brief", label: "概要", field: null },
  { key: "disqualification", label: "废标项", field: "disqualification_items" },
  { key: "scoring", label: "得分项", field: "scoring_items" },
  { key: "risk", label: "风险", field: "bid_risk_items" },
  { key: "directory", label: "目录要求", field: "directory_requirements" },
  { key: "templates", label: "模版", field: null },
  { key: "llm", label: "LLM 调用", field: null },
];

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || response.statusText);
  }
  return response.json();
}

function setError(message, hidden = false) {
  const bar = document.getElementById("interpret-error");
  bar.hidden = hidden;
  if (!hidden) {
    bar.textContent = message;
  }
}

function visibleStages(job, dualFile) {
  const kind = job?.job_kind || state.pendingJobKind || "interpret";
  const base = kind === "brief" ? BRIEF_STAGES : STAGES;
  return dualFile ? base : base.filter((s) => s !== "pipeline_2" && s !== "merge");
}

function renderProgress(job, dualFile) {
  const panel = document.getElementById("interpret-progress");
  panel.hidden = false;
  const useDual = job?.dual_file ?? dualFile;
  const visible = visibleStages(job, useDual);
  const stage = job?.stage || "pipeline_1";
  const stepsEl = document.getElementById("interpret-progress-steps");
  stepsEl.innerHTML = visible
    .map((s) => {
      const active = s === stage;
      const done = visible.indexOf(s) < visible.indexOf(stage);
      const cls = active ? "step active" : done ? "step done" : "step";
      return `<span class="${cls}">${STAGE_LABELS[s]}</span>`;
    })
    .join("");

  const percent = job?.progress_percent ?? 0;
  const detailEl = document.getElementById("interpret-progress-detail");
  if (stage === "interpret") {
    const segTotal = job?.segment_total ?? 0;
    const segCurrent = job?.segment_current ?? 0;
    const segText = segTotal > 0 ? `解读分段 (${segCurrent}/${segTotal})` : job?.message || "解读招标";
    const chapter = job?.detail || "";
    document.getElementById("interpret-progress-label").textContent = segText;
    detailEl.textContent = chapter;
  } else if (stage === "brief") {
    const segTotal = job?.segment_total ?? 0;
    const segCurrent = job?.segment_current ?? 0;
    const segText =
      segTotal > 0 ? `概要分片 (${segCurrent}/${segTotal})` : job?.message || "提取招标基础概要";
    document.getElementById("interpret-progress-label").textContent = segText;
    detailEl.textContent = job?.detail || "";
  } else {
    document.getElementById("interpret-progress-label").textContent =
      job?.message || STAGE_LABELS[stage] || "处理中…";
    const detail = job?.detail || "";
    const stepText = job?.step_total ? `（${job.step_current}/${job.step_total}）` : "";
    detailEl.textContent = `${detail}${stepText ? ` ${stepText}` : ""}`.trim();
  }
  document.getElementById("interpret-progress-percent").textContent = `${percent}%`;
  document.getElementById("interpret-progress-fill").style.width = `${percent}%`;
}

function hideProgress() {
  document.getElementById("interpret-progress").hidden = true;
}

async function refreshSessions() {
  const sessions = await api("/api/interpret/sessions");
  const select = document.getElementById("interpret-session-select");
  select.innerHTML = '<option value="">— 无会话 —</option>';
  for (const session of sessions) {
    const option = document.createElement("option");
    option.value = session.id;
    option.textContent = `${session.title} (${session.status})`;
    select.appendChild(option);
  }
  if (sessions.length && !state.sessionId) {
    state.sessionId = sessions[0].id;
    select.value = state.sessionId;
    if (sessions[0].status === "success") {
      await loadSessionData(state.sessionId);
    } else if (sessions[0].status === "running") {
      await resumeRunningSession(state.sessionId);
    }
  }
}

async function pollJob(jobId, dualFile) {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const job = await api(`/api/interpret/jobs/${jobId}`);
        if (job.status === "running") {
          renderProgress(job, dualFile);
          if (job.stage === "brief") {
            state.activeTab = "brief";
            showResultPanel();
          } else if (job.stage === "interpret" || job.stage === "template") {
            showResultPanel();
            await loadLlmCalls(job.session_id);
          }
        }
        if (job.status === "done") {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
          renderProgress(job, dualFile);
          setError("", true);
          await refreshSessions();
          if (job.job_kind === "brief") {
            await loadBrief(job.session_id);
            state.activeTab = "brief";
            showResultPanel();
          } else {
            await loadSessionData(job.session_id);
          }
          setTimeout(hideProgress, 1500);
          resolve(job);
        } else if (job.status === "failed") {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
          hideProgress();
          state.result = null;
          document.getElementById("overview-panel").hidden = true;
          await loadLlmCalls(job.session_id);
          showResultPanel();
          const msg = job.error || job.message || "解读失败";
          const needsApiKey =
            /LLM_API_KEY|OPENAI_API_KEY|required for LLM|LLMUnavailable/i.test(msg) &&
            !/validation error|JSON extraction failed/i.test(msg);
          setError(needsApiKey ? `请配置 LLM_API_KEY：${msg}` : msg);
          reject(new Error(msg));
        }
      } catch (err) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        reject(err);
      }
    };
    tick();
    state.pollTimer = setInterval(tick, 1000);
  });
}

async function resumeRunningSession(sessionId) {
  try {
    const job = await api(`/api/interpret/sessions/${sessionId}/job`);
    if (job.status === "running") {
      await enterRunningSession(sessionId, job.job_id, job.dual_file, job.job_kind || "interpret");
    }
  } catch {
    // no active job for this session
  }
}

function renderTabs() {
  const tabBar = document.getElementById("result-tabs");
  tabBar.innerHTML = "";
  for (const tab of TABS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = state.activeTab === tab.key ? "tab active" : "tab";
    btn.textContent = tab.label;
    btn.addEventListener("click", async () => {
      state.activeTab = tab.key;
      if (state.sessionId) {
        showResultPanel();
      }
      renderTabs();
      if (tab.key === "llm" && state.sessionId) {
        await loadLlmCalls(state.sessionId);
      } else {
        renderCards();
      }
    });
    tabBar.appendChild(btn);
  }
}

function renderStructureTree(nodes, depth = 0) {
  if (!nodes?.length) {
    return "";
  }
  return `<ul class="structure-tree depth-${depth}">${nodes
    .map((node) => {
      const mandatory = node.mandatory === false ? "（可选）" : "";
      const childHtml = node.children?.length ? renderStructureTree(node.children, depth + 1) : "";
      return `<li>${escapeHtml(node.title || "")}${mandatory ? ` <em>${mandatory}</em>` : ""}${childHtml}</li>`;
    })
    .join("")}</ul>`;
}

function renderOverview(overview) {
  const panel = document.getElementById("overview-panel");
  const content = document.getElementById("overview-content");
  if (!overview || !panel || !content) {
    return;
  }
  const fields = [
    ["summary", "总览"],
    ["disqualification_summary", "废标项"],
    ["scoring_summary", "得分项"],
    ["bid_risk_summary", "风险"],
    ["directory_summary", "目录"],
  ];
  const html = fields
    .filter(([key]) => overview[key])
    .map(([key, label]) => `<p><strong>${label}：</strong>${escapeHtml(overview[key])}</p>`)
    .join("");
  if (!html) {
    panel.hidden = true;
    return;
  }
  content.innerHTML = html;
  panel.hidden = false;
}

function renderScoringChildren(children) {
  if (!children?.length) {
    return "";
  }
  const rows = children
    .map((child) => {
      const score =
        child.max_score != null
          ? `${child.max_score}${child.score_range ? `（${child.score_range}）` : ""}`
          : child.score_range || "";
      let html = `<li class="scoring-child">`;
      html += `<strong>${escapeHtml(child.title || "细则")}</strong>`;
      if (score) {
        html += ` <span class="child-score">${escapeHtml(score)}</span>`;
      }
      if (child.criteria) {
        html += `<p class="child-criteria">${escapeHtml(child.criteria)}</p>`;
      }
      if (child.source_excerpt) {
        html += `<details class="child-excerpt"><summary>原文摘录</summary>`;
        html += `<blockquote>${escapeHtml(child.source_excerpt)}</blockquote></details>`;
      }
      html += `</li>`;
      return html;
    })
    .join("");
  return `<ul class="scoring-children">${rows}</ul>`;
}

function renderBrief(container) {
  if (!state.brief) {
    const hint = state.pendingJobKind === "brief" ? "概要提取进行中，请稍候…" : "尚未提取招标基础概要";
    container.innerHTML = `<p class="empty-tab">${hint}</p>`;
    return;
  }
  const brief = state.brief;
  let html = '<article class="result-card brief-card">';
  if (brief.summary_text) {
    html += `<section class="brief-summary"><h3>基础概要</h3><p class="brief-summary-text">${escapeHtml(
      brief.summary_text,
    )}</p>`;
    if (brief.summary_char_count != null) {
      html += `<p class="card-meta">共 ${brief.summary_char_count} 字</p>`;
    }
    html += `</section>`;
  }
  if (brief.fields) {
    html += `<section class="brief-fields"><h3>结构化字段</h3><dl class="brief-field-list">`;
    for (const { key, label } of BRIEF_FIELD_LABELS) {
      const value = brief.fields[key];
      if (!value) {
        continue;
      }
      html += `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`;
    }
    html += `</dl></section>`;
  }
  if (brief.segment_count != null && brief.segment_count > 1) {
    html += `<p class="card-meta">全文分 ${brief.segment_count} 片提取后合并</p>`;
  }
  html += `</article>`;
  container.innerHTML = html;
}

function renderCards() {
  const container = document.getElementById("result-cards");
  container.innerHTML = "";
  const tab = TABS.find((t) => t.key === state.activeTab);
  if (!tab) {
    return;
  }

  if (tab.key === "brief") {
    renderBrief(container);
    return;
  }

  if (tab.key === "llm") {
    renderLlmCalls(container);
    return;
  }

  if (!state.result) {
    container.innerHTML = '<p class="empty-tab">解读进行中，请稍候…</p>';
    return;
  }

  let items = [];
  if (tab.key === "templates") {
    items = state.result.templates?.templates || [];
  } else {
    items = state.result.interpretation?.[tab.field] || [];
  }

  if (!items.length) {
    container.innerHTML = '<p class="empty-tab">未提取到相关项</p>';
    return;
  }

  for (const item of items) {
    const card = document.createElement("article");
    card.className = "result-card";
    const path = (item.section_path || []).join(" › ");
    let body = `<h3>${escapeHtml(item.title || item.type_label || "未命名")}</h3>`;
    if (path) {
      body += `<p class="card-path">${escapeHtml(path)}</p>`;
    }
    if (item.summary) {
      body += `<p>${escapeHtml(item.summary)}</p>`;
    }
    if (item.trigger_condition) {
      body += `<p><strong>触发条件：</strong>${escapeHtml(item.trigger_condition)}</p>`;
    }
    if (item.max_score != null) {
      body += `<p><strong>分值：</strong>${item.max_score}${item.weight ? `（权重 ${escapeHtml(item.weight)}）` : ""}</p>`;
    }
    if (item.criteria) {
      body += `<p><strong>评分标准：</strong>${escapeHtml(item.criteria)}</p>`;
    }
    if (tab.key === "scoring" && item.children?.length) {
      body += renderScoringChildren(item.children);
    }
    if (item.severity) {
      body += `<p><span class="severity-badge ${item.severity}">${escapeHtml(item.severity)}</span> ${escapeHtml(item.risk_category || "")}</p>`;
    }
    if (item.required_sections?.length) {
      body += `<p><strong>必填章节：</strong>${escapeHtml(item.required_sections.join("、"))}</p>`;
      body += `<p><strong>强制：</strong>${item.mandatory ? "是" : "否"}</p>`;
    }
    if (tab.key === "directory") {
      if (item.inferred) {
        body += `<p><span class="inferred-badge">推断目录</span></p>`;
      }
      if (item.structure?.length) {
        body += renderStructureTree(item.structure);
      }
    }
    if (item.source_excerpt) {
      body += `<blockquote>${escapeHtml(item.source_excerpt)}</blockquote>`;
    }
    if (item.type_label && tab.key === "templates") {
      body += `<p><strong>类型：</strong>${escapeHtml(item.type_label)}</p>`;
    }

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const nodeId = item._node_id;
    if (nodeId) {
      const viewBtn = document.createElement("button");
      viewBtn.type = "button";
      viewBtn.textContent = "查看原文";
      viewBtn.addEventListener("click", () => openSourcePanel(state.sessionId, nodeId));
      actions.appendChild(viewBtn);

      const viewerLink = document.createElement("a");
      viewerLink.href = `/?session=${encodeURIComponent(state.sessionId)}&node=${encodeURIComponent(nodeId)}`;
      viewerLink.textContent = "在切片预览中打开";
      viewerLink.className = "viewer-link";
      actions.appendChild(viewerLink);
    }
    card.innerHTML = body;
    card.appendChild(actions);
    container.appendChild(card);
  }
}

function renderLlmCalls(container) {
  if (!state.llmCalls.length) {
    const hint = state.result ? "暂无 LLM 调用记录" : "解读进行中，LLM 调用将实时更新…";
    container.innerHTML = `<p class="empty-tab">${hint}</p>`;
    return;
  }
  for (const call of state.llmCalls) {
    const card = document.createElement("article");
    card.className = "result-card llm-call-card";
    const path = (call.section_path || []).join(" › ");
    const title = call.segment_id || call.call_type || "调用";
    let body = `<h3>${escapeHtml(title)}</h3>`;
    body += `<p class="card-path">${escapeHtml(call.call_type || "")}${path ? ` · ${escapeHtml(path)}` : ""}</p>`;
    if (call.timestamp) {
      body += `<p class="card-meta">${escapeHtml(call.timestamp)}</p>`;
    }
    if (call.token_estimate != null) {
      body += `<p><strong>token 估计：</strong>${call.token_estimate}</p>`;
    }
    if (call.messages?.length) {
      body += `<details open><summary>Prompt（${call.messages.length} 条消息）</summary><pre class="llm-payload">${escapeHtml(
        JSON.stringify(call.messages, null, 2),
      )}</pre></details>`;
    }
    if (call.response) {
      body += `<details><summary>Response（校验通过）</summary><pre class="llm-payload">${escapeHtml(call.response)}</pre></details>`;
    }
    if (call.attempts?.length) {
      body += `<details><summary>调用尝试（${call.attempts.length} 次）</summary>`;
      for (const att of call.attempts) {
        const status = att.success ? "成功" : "失败";
        const idx = (att.attempt ?? 0) + 1;
        body += `<div class="llm-attempt">`;
        body += `<p><strong>第 ${idx} 次 · ${status}</strong>`;
        if (att.duration_ms != null) {
          body += ` · ${att.duration_ms} ms`;
        }
        if (att.stream != null) {
          body += ` · ${att.stream ? "流式" : "非流式"}`;
        }
        body += `</p>`;
        if (att.model) {
          body += `<p><strong>模型：</strong>${escapeHtml(att.model)}</p>`;
        }
        if (att.finish_reason) {
          body += `<p><strong>结束原因：</strong>${escapeHtml(att.finish_reason)}</p>`;
        }
        if (att.usage) {
          const cached =
            att.usage.prompt_tokens_details?.cached_tokens ??
            att.usage.cached_tokens ??
            null;
          body += `<p><strong>Token 用量：</strong>`;
          if (cached != null) {
            body += ` cache=${cached}`;
          }
          body += `</p>`;
          body += `<pre class="llm-payload">${escapeHtml(JSON.stringify(att.usage, null, 2))}</pre>`;
        }
        if (att.validation_error) {
          body += `<p class="card-error"><strong>校验失败（响应已收到）：</strong>${escapeHtml(att.validation_error)}</p>`;
        }
        if (att.response_raw) {
          const label = att.success ? "原始响应" : "原始响应（未通过校验）";
          body += `<details${att.success ? "" : " open"}><summary>${label}（${att.response_chars ?? att.response_raw.length} 字符）</summary>`;
          body += `<pre class="llm-payload">${escapeHtml(att.response_raw)}</pre></details>`;
        }
        body += `</div>`;
      }
      body += `</details>`;
    }
    card.innerHTML = body;
    container.appendChild(card);
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

async function resolveNodeIds(sessionId, result) {
  const outline = await api(`/api/interpret/sessions/${sessionId}/outline`).catch(() => null);
  if (!outline) {
    return;
  }
  const nodes = flattenNodes(outline.nodes || []);
  const attach = (items) => {
    for (const item of items || []) {
      const path = item.section_path || [];
      if (!path.length) {
        continue;
      }
      const title = path[path.length - 1];
      const match = nodes.find((n) => n.title === title);
      if (match) {
        item._node_id = match.node_id;
      }
    }
  };
  attach(result.interpretation?.disqualification_items);
  attach(result.interpretation?.scoring_items);
  attach(result.interpretation?.bid_risk_items);
  attach(result.interpretation?.directory_requirements);
  for (const tpl of result.templates?.templates || []) {
    const path = tpl.section_path || [];
    if (path.length) {
      const title = path[path.length - 1];
      const match = nodes.find((n) => n.title === title);
      if (match) {
        tpl._node_id = match.node_id;
      }
    }
  }
}

function flattenNodes(nodes, out = []) {
  for (const node of nodes) {
    out.push(node);
    if (node.children?.length) {
      flattenNodes(node.children, out);
    }
  }
  return out;
}

function showResultPanel() {
  document.getElementById("result-panel").hidden = false;
  renderTabs();
  renderCards();
}

async function loadLlmCalls(sessionId) {
  if (!sessionId) {
    state.llmCalls = [];
    return;
  }
  state.llmCalls = await api(`/api/interpret/sessions/${sessionId}/llm-calls`).catch(() => []);
  renderCards();
}

async function loadBrief(sessionId) {
  if (!sessionId) {
    state.brief = null;
    return false;
  }
  try {
    state.brief = await api(`/api/interpret/sessions/${sessionId}/brief`);
    return true;
  } catch {
    state.brief = null;
    return false;
  }
}

async function loadResult(sessionId) {
  state.sessionId = sessionId;
  try {
    const result = await api(`/api/interpret/sessions/${sessionId}/result`);
    await resolveNodeIds(sessionId, result);
    state.result = result;
    await loadLlmCalls(sessionId);
    renderOverview(result.interpretation?.overview);
    return true;
  } catch {
    state.result = null;
    return false;
  }
}

async function loadSessionData(sessionId) {
  state.sessionId = sessionId;
  const hasBrief = await loadBrief(sessionId);
  const hasResult = await loadResult(sessionId);
  if (!hasResult) {
    await loadLlmCalls(sessionId);
    document.getElementById("overview-panel").hidden = true;
  }
  if (hasBrief && !hasResult) {
    state.activeTab = "brief";
  }
  showResultPanel();
  return { hasBrief, hasResult };
}

async function enterRunningSession(sessionId, jobId, dualFile, jobKind = "interpret") {
  state.sessionId = sessionId;
  state.result = null;
  state.pendingJobKind = jobKind;
  if (jobKind !== "brief") {
    document.getElementById("overview-panel").hidden = true;
  }
  showResultPanel();
  if (jobKind !== "brief") {
    await loadLlmCalls(sessionId);
  }
  await pollJob(jobId, dualFile);
}

async function openSourcePanel(sessionId, nodeId) {
  const section = await api(`/api/interpret/sessions/${sessionId}/sections/${nodeId}`);
  const panel = document.getElementById("source-panel");
  const content = document.getElementById("source-content");
  const md = rewriteAssetUrls(section.markdown, sessionId);
  content.innerHTML = marked.parse(md);
  panel.hidden = false;
}

function rewriteAssetUrls(markdown, sessionId) {
  const base = `/api/sessions/${sessionId}/assets/`;
  return markdown.replace(
    /(!\[[^\]]*\]\()(?!https?:\/\/|\/api\/)([^)]+)\)/g,
    (match, prefix, path) => `${prefix}${base}${path.replace(/^\//, "")})`,
  );
}

function sessionDualFile(session) {
  return Boolean(session?.source_files?.length > 1);
}

async function resolveDualFile(sessionId) {
  if (!sessionId) {
    return false;
  }
  try {
    const session = await api(`/api/interpret/sessions/${sessionId}`);
    return sessionDualFile(session);
  } catch {
    return false;
  }
}

async function startBriefJob({ sessionId, jobId, dualFile }) {
  state.sessionId = sessionId;
  state.pendingJobKind = "brief";
  state.activeTab = "brief";
  document.getElementById("overview-panel").hidden = true;
  showResultPanel();
  await refreshSessions();
  document.getElementById("interpret-session-select").value = sessionId;
  await pollJob(jobId, dualFile);
}

async function startInterpretJob({ sessionId, jobId, dualFile }) {
  state.sessionId = sessionId;
  state.pendingJobKind = "interpret";
  state.result = null;
  document.getElementById("overview-panel").hidden = true;
  showResultPanel();
  await refreshSessions();
  document.getElementById("interpret-session-select").value = sessionId;
  await pollJob(jobId, dualFile);
}

document.getElementById("brief-btn").addEventListener("click", async () => {
  const file1 = document.getElementById("file1-input").files[0];
  const file2 = document.getElementById("file2-input").files[0];
  const sessionId = state.sessionId || document.getElementById("interpret-session-select").value || null;
  if (!file1 && !sessionId) {
    setError("请选择文件，或在下拉框中选择已有会话");
    return;
  }
  const briefBtn = document.getElementById("brief-btn");
  const startBtn = document.getElementById("start-btn");
  briefBtn.disabled = true;
  startBtn.disabled = true;
  setError("", true);
  try {
    let result;
    let dualFile = false;
    if (file1) {
      const form = new FormData();
      form.append("file1", file1);
      if (file2) {
        form.append("file2", file2);
      }
      dualFile = Boolean(file2);
      state.brief = null;
      state.result = null;
      renderProgress(
        { stage: "pipeline_1", job_kind: "brief", message: "上传完成，开始提取概要…", progress_percent: 0 },
        dualFile,
      );
      result = await api("/api/interpret/upload?job_kind=brief", { method: "POST", body: form });
    } else {
      dualFile = await resolveDualFile(sessionId);
      state.brief = null;
      renderProgress(
        { stage: "brief", job_kind: "brief", message: "使用当前会话提取概要…", progress_percent: 0 },
        dualFile,
      );
      result = await api(`/api/interpret/sessions/${sessionId}/brief`, { method: "POST" });
    }
    await startBriefJob({ sessionId: result.session_id, jobId: result.job_id, dualFile });
  } catch (err) {
    setError(err.message || "概要提取失败");
    console.error(err);
  } finally {
    briefBtn.disabled = false;
    startBtn.disabled = false;
    document.getElementById("file1-input").value = "";
    document.getElementById("file2-input").value = "";
  }
});

document.getElementById("start-btn").addEventListener("click", async () => {
  const file1 = document.getElementById("file1-input").files[0];
  const file2 = document.getElementById("file2-input").files[0];
  const sessionId = state.sessionId || document.getElementById("interpret-session-select").value || null;
  if (!file1 && !sessionId) {
    setError("请选择文件，或在下拉框中选择已有会话");
    return;
  }
  const btn = document.getElementById("start-btn");
  const briefBtn = document.getElementById("brief-btn");
  btn.disabled = true;
  briefBtn.disabled = true;
  setError("", true);
  try {
    let result;
    let dualFile = false;
    if (file1) {
      const form = new FormData();
      form.append("file1", file1);
      if (file2) {
        form.append("file2", file2);
      }
      dualFile = Boolean(file2);
      state.pendingJobKind = "interpret";
      renderProgress(
        { stage: "pipeline_1", job_kind: "interpret", message: "上传完成，开始处理…", progress_percent: 0 },
        dualFile,
      );
      result = await api("/api/interpret/upload", { method: "POST", body: form });
    } else {
      dualFile = await resolveDualFile(sessionId);
      state.pendingJobKind = "interpret";
      renderProgress(
        { stage: "interpret", job_kind: "interpret", message: "使用当前会话开始解读…", progress_percent: 0 },
        dualFile,
      );
      result = await api(`/api/interpret/sessions/${sessionId}/run`, { method: "POST" });
    }
    await startInterpretJob({ sessionId: result.session_id, jobId: result.job_id, dualFile });
  } catch (err) {
    setError(err.message || "上传失败");
    console.error(err);
  } finally {
    btn.disabled = false;
    briefBtn.disabled = false;
    document.getElementById("file1-input").value = "";
    document.getElementById("file2-input").value = "";
  }
});

document.getElementById("close-source-panel").addEventListener("click", () => {
  document.getElementById("source-panel").hidden = true;
});

document.getElementById("interpret-session-select").addEventListener("change", async (event) => {
  const sessionId = event.target.value || null;
  state.sessionId = sessionId;
  if (!sessionId) {
    document.getElementById("result-panel").hidden = true;
    return;
  }
  const session = await api(`/api/interpret/sessions/${sessionId}`);
  if (session.status === "success") {
    await loadSessionData(sessionId);
  } else if (session.status === "running") {
    await resumeRunningSession(sessionId);
    if (!state.pollTimer) {
      state.result = null;
      document.getElementById("overview-panel").hidden = true;
      await loadBrief(sessionId);
      await loadLlmCalls(sessionId);
      showResultPanel();
    }
  } else {
    state.result = null;
    state.brief = null;
    document.getElementById("overview-panel").hidden = true;
    await loadBrief(sessionId);
    await loadLlmCalls(sessionId);
    showResultPanel();
  }
});

document.getElementById("delete-interpret-session-btn").addEventListener("click", async () => {
  if (!state.sessionId) {
    setError("请先选择会话");
    return;
  }
  if (!confirm("将永久删除该会话、工作区与上传文件，是否继续？")) {
    return;
  }
  try {
    await api(`/api/interpret/sessions/${state.sessionId}`, { method: "DELETE" });
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
    state.sessionId = null;
    state.result = null;
    state.brief = null;
    state.llmCalls = [];
    hideProgress();
    document.getElementById("result-panel").hidden = true;
    setError("", true);
    await refreshSessions();
  } catch (err) {
    setError(err.message || "删除会话失败");
    console.error(err);
  }
});

refreshSessions().catch(console.error);
