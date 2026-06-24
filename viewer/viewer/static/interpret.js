const state = {
  sessionId: null,
  pollTimer: null,
  result: null,
  activeTab: "disqualification",
};

const STAGES = ["pipeline_1", "pipeline_2", "merge", "interpret", "template"];
const STAGE_LABELS = {
  pipeline_1: "提取文件 1",
  pipeline_2: "提取文件 2",
  merge: "合并工作区",
  interpret: "解读招标",
  template: "提取模版",
};

const TABS = [
  { key: "disqualification", label: "废标项", field: "disqualification_items" },
  { key: "scoring", label: "得分项", field: "scoring_items" },
  { key: "risk", label: "风险", field: "bid_risk_items" },
  { key: "directory", label: "目录要求", field: "directory_requirements" },
  { key: "templates", label: "模版", field: null },
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

function renderProgress(job, dualFile) {
  const panel = document.getElementById("interpret-progress");
  panel.hidden = false;
  const useDual = job?.dual_file ?? dualFile;
  const visible = useDual ? STAGES : STAGES.filter((s) => s !== "pipeline_2" && s !== "merge");
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
  document.getElementById("interpret-progress-label").textContent = job?.message || STAGE_LABELS[stage] || "处理中…";
  document.getElementById("interpret-progress-percent").textContent = `${percent}%`;
  document.getElementById("interpret-progress-fill").style.width = `${percent}%`;
  const detail = job?.detail || "";
  const stepText = job?.step_total ? `（${job.step_current}/${job.step_total}）` : "";
  document.getElementById("interpret-progress-detail").textContent = `${detail}${stepText ? ` ${stepText}` : ""}`.trim();
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
      await loadResult(state.sessionId);
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
        }
        if (job.status === "done") {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
          renderProgress(job, dualFile);
          setError("", true);
          await refreshSessions();
          await loadResult(job.session_id);
          setTimeout(hideProgress, 1500);
          resolve(job);
        } else if (job.status === "failed") {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
          hideProgress();
          const msg = job.error || job.message || "解读失败";
          setError(msg.includes("LLM") || msg.includes("API") ? `请配置 LLM_API_KEY：${msg}` : msg);
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
      state.sessionId = sessionId;
      await pollJob(job.job_id, job.dual_file);
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
    btn.addEventListener("click", () => {
      state.activeTab = tab.key;
      renderTabs();
      renderCards();
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

function renderCards() {
  const container = document.getElementById("result-cards");
  container.innerHTML = "";
  const tab = TABS.find((t) => t.key === state.activeTab);
  if (!tab || !state.result) {
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

async function loadResult(sessionId) {
  state.sessionId = sessionId;
  const result = await api(`/api/interpret/sessions/${sessionId}/result`);
  await resolveNodeIds(sessionId, result);
  state.result = result;
  renderOverview(result.interpretation?.overview);
  document.getElementById("result-panel").hidden = false;
  renderTabs();
  renderCards();
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

document.getElementById("start-btn").addEventListener("click", async () => {
  const file1 = document.getElementById("file1-input").files[0];
  const file2 = document.getElementById("file2-input").files[0];
  if (!file1) {
    setError("请选择文件 1");
    return;
  }
  const btn = document.getElementById("start-btn");
  btn.disabled = true;
  setError("", true);
  try {
    const form = new FormData();
    form.append("file1", file1);
    if (file2) {
      form.append("file2", file2);
    }
    const dualFile = Boolean(file2);
    renderProgress({ stage: "pipeline_1", message: "上传完成，开始处理…", progress_percent: 0 }, dualFile);
    const result = await api("/api/interpret/upload", { method: "POST", body: form });
    state.sessionId = result.session_id;
    await refreshSessions();
    await pollJob(result.job_id, dualFile);
  } catch (err) {
    setError(err.message || "上传失败");
    console.error(err);
  } finally {
    btn.disabled = false;
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
    await loadResult(sessionId);
  } else if (session.status === "running") {
    document.getElementById("result-panel").hidden = true;
    await resumeRunningSession(sessionId);
  } else {
    document.getElementById("result-panel").hidden = true;
  }
});

refreshSessions().catch(console.error);
