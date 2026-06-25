const state = {
  sessionId: null,
  jobId: null,
  draft: null,
  pollTimer: null,
};

function sessionIdFromQuery() {
  return new URLSearchParams(window.location.search).get("session_id");
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
  if (!res.ok) return;
  state.draft = await res.json();
  renderTree(state.draft.root);
}

async function loadLlmCalls() {
  if (!state.sessionId) return;
  const res = await fetch(`/api/gen-catalog/sessions/${state.sessionId}/llm-calls`);
  if (!res.ok) return;
  const calls = await res.json();
  const list = document.getElementById("llm-calls-list");
  list.innerHTML = "";
  for (const call of calls) {
    const li = document.createElement("li");
    li.textContent = `${call.call_type || ""} ${call.segment_id || ""}`;
    list.appendChild(li);
  }
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
  if (!res.ok) return;
  const job = await res.json();
  setProgress(job);
  if (job.status === "running") {
    state.pollTimer = setTimeout(() => pollJob(jobId), 800);
    return;
  }
  await loadDraft();
  await loadLlmCalls();
}

async function postAction(path, query = "") {
  clearError();
  const res = await fetch(`/api/gen-catalog/sessions/${state.sessionId}/${path}${query}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    showError(err.detail || res.statusText);
    return;
  }
  const data = await res.json();
  state.jobId = data.job_id;
  pollJob(state.jobId);
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

state.sessionId = sessionIdFromQuery();
if (!state.sessionId) {
  showError("缺少 session_id 参数，请从招标解读页进入");
} else {
  loadPrerequisites();
  loadDraft();
  loadLlmCalls();
}
