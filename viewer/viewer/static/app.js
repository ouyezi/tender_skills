const state = { sessionId: null, selectedNodeId: null, pollTimer: null };

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || response.statusText);
  }
  return response.json();
}

function rewriteAssetUrls(markdown, sessionId) {
  const base = `/api/sessions/${sessionId}/assets/`;
  return markdown.replace(
    /(!\[[^\]]*\]\()(?!https?:\/\/|\/api\/)([^)]+)\)/g,
    (match, prefix, path) => `${prefix}${base}${path.replace(/^\//, "")})`,
  );
}

function setProgress(message, hidden = false) {
  const bar = document.getElementById("progress-bar");
  bar.hidden = hidden;
  if (!hidden) {
    bar.textContent = message;
  }
}

function markTreeSelection(nodeId) {
  document.querySelectorAll(".tree-node").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.nodeId === nodeId);
  });
}

async function refreshSessions() {
  const sessions = await api("/api/sessions");
  const select = document.getElementById("session-select");
  select.innerHTML = "";
  for (const session of sessions) {
    const option = document.createElement("option");
    option.value = session.id;
    option.textContent = `${session.title} (${session.status})`;
    select.appendChild(option);
  }
  if (sessions.length && !state.sessionId) {
    state.sessionId = sessions[0].id;
    select.value = state.sessionId;
    await loadOutline();
  } else if (state.sessionId) {
    select.value = state.sessionId;
  }
}

async function loadOutline() {
  if (!state.sessionId) {
    document.getElementById("outline-meta").textContent = "";
    document.getElementById("outline-tree").innerHTML = "";
    return;
  }
  const data = await api(`/api/sessions/${state.sessionId}/outline`);
  document.getElementById("outline-meta").textContent = `strategy: ${data.strategy}`;
  const container = document.getElementById("outline-tree");
  container.innerHTML = "";
  container.appendChild(renderNodes(data.nodes, 0));
  if (state.selectedNodeId) {
    markTreeSelection(state.selectedNodeId);
  }
}

function renderNodes(nodes, depth) {
  const ul = document.createElement("ul");
  for (const node of nodes) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.className = "tree-node";
    btn.type = "button";
    btn.dataset.nodeId = node.node_id;
    btn.style.paddingLeft = `${depth * 12 + 8}px`;
    btn.textContent = (node.needs_review ? "⚠ " : "") + node.title;
    btn.onclick = () => selectNode(node.node_id);
    li.appendChild(btn);
    if (node.children?.length) {
      li.appendChild(renderNodes(node.children, depth + 1));
    }
    ul.appendChild(li);
  }
  return ul;
}

async function selectNode(nodeId) {
  state.selectedNodeId = nodeId;
  markTreeSelection(nodeId);
  const section = await api(`/api/sessions/${state.sessionId}/sections/${nodeId}`);
  const markdown = rewriteAssetUrls(section.markdown, state.sessionId);
  const html = marked.parse(markdown, {
    mangle: false,
    headerIds: false,
  });
  document.getElementById("content-panel").innerHTML = html;
  const pathLabel =
    section.section_path?.length ? section.section_path.join(" › ") : section.title;
  document.getElementById("section-meta").textContent =
    `${pathLabel} · char: ${section.char_start}–${section.char_end} · needs_review: ${section.needs_review}`;
}

async function pollJob(jobId) {
  const bar = document.getElementById("progress-bar");
  bar.hidden = false;
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    try {
      const job = await api(`/api/jobs/${jobId}`);
      bar.textContent = `${job.stage}: ${job.message}`;
      if (job.status === "done") {
        clearInterval(state.pollTimer);
        bar.hidden = true;
        await refreshSessions();
        state.sessionId = job.session_id;
        document.getElementById("session-select").value = state.sessionId;
        await loadOutline();
      }
      if (job.status === "failed") {
        clearInterval(state.pollTimer);
        bar.textContent = job.error || "pipeline failed";
      }
    } catch (err) {
      clearInterval(state.pollTimer);
      bar.textContent = err.message || "job poll failed";
    }
  }, 1000);
}

document.getElementById("upload-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const form = new FormData();
    form.append("file", file);
    const result = await api("/api/upload", { method: "POST", body: form });
    state.sessionId = result.session_id;
    state.selectedNodeId = null;
    document.getElementById("content-panel").innerHTML = "";
    document.getElementById("section-meta").textContent = "";
    await refreshSessions();
    await pollJob(result.job_id);
  } catch (err) {
    setProgress(err.message || "upload failed");
    console.error(err);
  }
  event.target.value = "";
});

document.getElementById("open-btn").addEventListener("click", async () => {
  const path = document.getElementById("open-path").value.trim();
  if (!path) return;
  try {
    const result = await api("/api/workspaces/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    state.sessionId = result.session_id;
    state.selectedNodeId = null;
    document.getElementById("content-panel").innerHTML = "";
    document.getElementById("section-meta").textContent = "";
    await refreshSessions();
    await loadOutline();
  } catch (err) {
    setProgress(err.message || "open workspace failed");
    console.error(err);
  }
});

document.getElementById("session-select").addEventListener("change", async (event) => {
  state.sessionId = event.target.value || null;
  state.selectedNodeId = null;
  document.getElementById("content-panel").innerHTML = "";
  document.getElementById("section-meta").textContent = "";
  try {
    await loadOutline();
  } catch (err) {
    setProgress(err.message || "load outline failed");
    console.error(err);
  }
});

refreshSessions().catch(console.error);
