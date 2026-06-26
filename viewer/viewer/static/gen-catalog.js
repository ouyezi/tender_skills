const state = {
  sessionId: null,
  jobId: null,
  draft: null,
  pollTimer: null,
  llmCalls: [],
};

function sessionIdFromQuery() {
  return new URLSearchParams(window.location.search).get("session_id");
}

function setSessionInUrl(sessionId) {
  const url = new URL(window.location.href);
  if (sessionId) {
    url.searchParams.set("session_id", sessionId);
  } else {
    url.searchParams.delete("session_id");
  }
  window.history.replaceState({}, "", url);
}

function updateSessionLabel() {
  const sessionLabel = document.getElementById("session-label");
  if (!sessionLabel) return;
  if (!state.sessionId) {
    sessionLabel.textContent = "";
    return;
  }
  const select = document.getElementById("gen-catalog-session-select");
  const title = select?.selectedOptions?.[0]?.textContent || state.sessionId;
  sessionLabel.textContent = title.includes(state.sessionId) ? title : `会话: ${state.sessionId}`;
}

async function refreshSessions() {
  const res = await fetch("/api/interpret/sessions");
  if (!res.ok) return [];
  const sessions = await res.json();
  const select = document.getElementById("gen-catalog-session-select");
  if (!select) return sessions;
  const previous = state.sessionId || select.value || sessionIdFromQuery();
  select.innerHTML = '<option value="">— 选择会话 —</option>';
  for (const session of sessions) {
    const option = document.createElement("option");
    option.value = session.id;
    const ready = session.status === "success" ? "已解读" : session.status;
    option.textContent = `${session.title} (${ready})`;
    select.appendChild(option);
  }
  if (previous && sessions.some((s) => s.id === previous)) {
    select.value = previous;
    state.sessionId = previous;
  }
  return sessions;
}

async function loadSessionData() {
  clearError();
  if (!state.sessionId) {
    state.draft = null;
    document.getElementById("outline-tree").innerHTML = "";
    document.getElementById("node-detail").innerHTML = '<p class="muted">选择左侧节点查看详情</p>';
    document.getElementById("llm-calls-list").innerHTML = "";
    document.getElementById("gen-catalog-progress").hidden = true;
    updateSessionLabel();
    return;
  }
  setSessionInUrl(state.sessionId);
  updateSessionLabel();
  await Promise.all([loadPrerequisites(), loadDraft(), loadSessionStatus(), loadLlmCalls()]);
}

function setProgress(job) {
  const panel = document.getElementById("gen-catalog-progress");
  panel.hidden = false;
  document.getElementById("gen-catalog-progress-label").textContent = job.message || "";
  document.getElementById("gen-catalog-progress-percent").textContent = `${job.progress_percent || 0}%`;
  document.getElementById("gen-catalog-progress-fill").style.width = `${job.progress_percent || 0}%`;
  document.getElementById("gen-catalog-progress-detail").textContent = job.detail || "";
}

function showError(message) {
  const el = document.getElementById("gen-catalog-error");
  el.hidden = false;
  el.textContent = message;
}

function clearError() {
  const el = document.getElementById("gen-catalog-error");
  el.hidden = true;
  el.textContent = "";
}

function findNodeTitle(root, nodeId) {
  if (!root || !nodeId) return null;
  if (root.id === nodeId) return root.title;
  for (const child of root.children || []) {
    const found = findNodeTitle(child, nodeId);
    if (found) return found;
  }
  return null;
}

function formatLlmCallLabel(call) {
  const type = call.call_type || "";
  if (type === "gen_catalog_initial") {
    return "初始目录生成";
  }
  if (type === "gen_catalog_node_plan") {
    const seg = call.segment_id || "";
    const title = call.section_path?.[0] || findNodeTitle(state.draft?.root, seg) || "";
    return title ? `分析优化点「${title}」` : "分析优化点";
  }
  if (type === "gen_catalog_node_apply") {
    const seg = call.segment_id || "";
    const title = call.section_path?.[0] || findNodeTitle(state.draft?.root, seg) || "";
    return title ? `执行优化「${title}」` : "执行优化";
  }
  if (type === "gen_catalog_node") {
    const seg = call.segment_id || "";
    const title = call.section_path?.[0] || findNodeTitle(state.draft?.root, seg) || "";
    return title ? `完善章节「${title}」（${seg}）` : `完善章节（${seg}）`;
  }
  return `${type} ${call.segment_id || ""}`.trim();
}

async function loadPrerequisites() {
  if (!state.sessionId) return;
  const res = await fetch(`/api/gen-catalog/sessions/${state.sessionId}/prerequisites`);
  if (!res.ok) return;
  const data = await res.json();
  const box = document.getElementById("prerequisite-warnings");
  if (!data.warnings?.length) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.textContent = `提示：${data.warnings.join("；")}`;
}

async function loadDraft() {
  if (!state.sessionId) return;
  const res = await fetch(`/api/gen-catalog/sessions/${state.sessionId}/draft`);
  if (!res.ok) {
    state.draft = null;
    document.getElementById("outline-tree").innerHTML = "";
    return;
  }
  state.draft = await res.json();
  renderTree(state.draft.root);
}

async function loadSessionStatus() {
  if (!state.sessionId) return;
  const res = await fetch(`/api/gen-catalog/sessions/${state.sessionId}/status`);
  if (!res.ok) return;
  const data = await res.json();
  if (!data.has_session) {
    if (!data.has_draft) {
      setProgress({
        message: "尚未开始生成目录",
        detail: "请选择已解读会话后点击「生成目录」",
        progress_percent: 0,
      });
    }
    return;
  }
  const percent = data.step_total
    ? Math.min(100, Math.round((data.step_index / data.step_total) * 100))
    : 0;
  if (data.status === "paused") {
    const next = data.next_node_title
      ? `下一步将完善「${data.next_node_title}」`
      : "点击「继续」执行下一步";
    setProgress({
      message: `已暂停（${data.step_index}/${data.step_total} 步，共 ${data.refine_chapters} 个一级章节待完善）`,
      detail: next,
      progress_percent: percent,
    });
  } else if (data.status === "awaiting_accept") {
    setProgress({
      message: "目录生成完成，待确认落盘",
      detail: "点击「确认落盘」写入 bid_outline.json",
      progress_percent: 100,
    });
  }
}

async function loadLlmCalls() {
  if (!state.sessionId) return;
  const panel = document.getElementById("llm-calls-panel");
  const panelOpen = panel?.open ?? false;
  const res = await fetch(`/api/gen-catalog/sessions/${state.sessionId}/llm-calls`);
  if (!res.ok) return;
  state.llmCalls = await res.json();
  renderLlmCalls();
  if (panel && panelOpen) {
    panel.open = true;
  }
}

function formatLlmCallSubtitle(call) {
  const type = call.call_type || "";
  const seg = call.segment_id || "";
  if (type === "gen_catalog_node_plan") {
    return seg ? `分析优化点 · ${seg}` : "分析优化点";
  }
  if (type === "gen_catalog_node_apply") {
    return seg ? `执行优化 · ${seg}` : "执行优化";
  }
  return type;
}

function renderLlmCalls() {
  const container = document.getElementById("llm-calls-list");
  window.LlmCallsUi.syncLlmCallCards(container, state.llmCalls, {
    emptyHint: "暂无 LLM 调用记录",
    renderCard: (call) => {
      const title = formatLlmCallLabel(call);
      const subtitle = formatLlmCallSubtitle(call);
      return window.LlmCallCard.buildLlmCallCard(call, { title, subtitle });
    },
  });
}

function renderTree(root) {
  const container = document.getElementById("outline-tree");
  container.innerHTML = "";
  const ul = document.createElement("ul");
  ul.className = "outline-tree-list";
  for (const child of root.children || []) {
    ul.appendChild(renderNode(child));
  }
  container.appendChild(ul);
}

function renderNode(node) {
  const li = document.createElement("li");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "outline-tree-node";
  btn.textContent = node.title;
  btn.addEventListener("click", () => renderNodeDetail(node));
  li.appendChild(btn);
  if (node.children?.length) {
    const ul = document.createElement("ul");
    for (const child of node.children) {
      ul.appendChild(renderNode(child));
    }
    li.appendChild(ul);
  }
  return li;
}

function renderNodeDetail(node) {
  const panel = document.getElementById("node-detail");
  panel.innerHTML = `
    <h2>${node.title}</h2>
    <p><strong>概要</strong>：${node.summary || "—"}</p>
    <p><strong>撰写规范</strong>：${node.writing_spec || "—"}</p>
    <p><strong>评分引用</strong>：${(node.scoring_refs || []).join(", ") || "—"}</p>
    <p><strong>废标引用</strong>：${(node.disqualification_refs || []).join(", ") || "—"}</p>
    <p><strong>模板</strong>：${node.template_ref?.file || "—"}</p>
  `;
}

async function pollJob(jobId) {
  const res = await fetch(`/api/gen-catalog/jobs/${jobId}`);
  if (!res.ok) {
    showError(`无法获取任务状态 (${res.status})`);
    setButtonsEnabled(true);
    return;
  }
  const job = await res.json();
  setProgress(job);
  if (job.status === "running") {
    await loadLlmCalls();
    state.pollTimer = setTimeout(() => pollJob(jobId), 800);
    return;
  }
  setButtonsEnabled(true);
  if (job.status === "failed") {
    showError(job.error || job.message || "任务失败");
    return;
  }
  clearError();
  await loadSessionData();
}

function setButtonsEnabled(enabled) {
  for (const id of ["start-btn", "continue-btn", "accept-btn", "restart-btn"]) {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = !enabled;
  }
}

function showPending(message) {
  const panel = document.getElementById("gen-catalog-progress");
  panel.hidden = false;
  document.getElementById("gen-catalog-progress-label").textContent = message;
  document.getElementById("gen-catalog-progress-percent").textContent = "…";
  document.getElementById("gen-catalog-progress-fill").style.width = "0%";
  document.getElementById("gen-catalog-progress-detail").textContent = "首次调用大模型可能需要 1–3 分钟，请稍候";
}

async function postAction(path, query = "") {
  if (!state.sessionId) {
    showError("请先在下拉框中选择解读会话");
    return;
  }
  clearError();
  setButtonsEnabled(false);
  showPending("已提交，等待服务响应…");
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
  try {
    const res = await fetch(`/api/gen-catalog/sessions/${state.sessionId}/${path}${query}`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = err.detail;
      const message = typeof detail === "string" ? detail : JSON.stringify(detail) || res.statusText;
      showError(message);
      setButtonsEnabled(true);
      return;
    }
    const data = await res.json();
    state.jobId = data.job_id;
    showPending("任务已启动，大模型处理中…");
    pollJob(state.jobId);
  } catch (err) {
    showError(err?.message || "网络请求失败");
    setButtonsEnabled(true);
  }
}

document.getElementById("start-btn").addEventListener("click", () => {
  const mode = document.getElementById("mode-select").value;
  postAction("start", `?mode=${encodeURIComponent(mode)}`);
});

document.getElementById("continue-btn").addEventListener("click", () => postAction("continue"));
document.getElementById("accept-btn").addEventListener("click", () => postAction("accept"));
document.getElementById("restart-btn").addEventListener("click", () => {
  const mode = document.getElementById("mode-select").value;
  postAction("start", `?mode=${encodeURIComponent(mode)}&restart=true`);
});

document.getElementById("gen-catalog-session-select").addEventListener("change", async (event) => {
  state.sessionId = event.target.value || null;
  await loadSessionData();
});

async function initPage() {
  const querySession = sessionIdFromQuery();
  await refreshSessions();
  const select = document.getElementById("gen-catalog-session-select");
  if (querySession) {
    state.sessionId = querySession;
    if (select) select.value = querySession;
  } else if (select?.value) {
    state.sessionId = select.value;
  }
  if (!state.sessionId) {
    showError("请在下拉框选择已解读的会话，或从招标解读页点击「生成目录」进入");
  }
  await loadSessionData();
}

initPage().catch(console.error);
