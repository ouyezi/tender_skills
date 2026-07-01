const state = {
  sessionId: null,
  selectedNodeId: null,
  pollTimer: null,
  collapsedNodeIds: new Set(),
  currentSectionMarkdown: null,
  documentAssets: null,
  activeAssetRef: null,
};

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

function clearAssetHighlight() {
  state.activeAssetRef = null;
  document.querySelectorAll(".asset-row.active").forEach((row) => {
    row.classList.remove("active");
  });
  document.querySelectorAll(".asset-highlight").forEach((el) => {
    el.classList.remove("asset-highlight");
  });
}

function clearSectionView() {
  state.currentSectionMarkdown = null;
  clearAssetHighlight();
  document.getElementById("content-panel").innerHTML = "";
  const metaBar = document.getElementById("section-meta");
  metaBar.hidden = true;
  document.getElementById("section-meta-text").textContent = "";
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
    document.getElementById("assets-list").textContent = "—";
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
  await loadDocumentAssets();
}

async function loadDocumentAssets() {
  const listEl = document.getElementById("assets-list");
  if (!state.sessionId) {
    listEl.textContent = "—";
    return;
  }
  listEl.textContent = "加载中…";
  try {
    state.documentAssets = await api(`/api/sessions/${state.sessionId}/document-assets`);
    renderAssetsList(state.documentAssets);
  } catch (err) {
    listEl.textContent = err.message || "加载失败";
  }
}

function renderAssetsList(data) {
  const listEl = document.getElementById("assets-list");
  listEl.innerHTML = "";
  const groups = [
    ["图片", data.images || []],
    ["表格", data.tables || []],
  ];
  let any = false;
  for (const [label, items] of groups) {
    if (!items.length) continue;
    any = true;
    const details = document.createElement("details");
    details.className = "asset-group";
    details.open = true;
    const summary = document.createElement("summary");
    summary.textContent = `${label} (${items.length})`;
    details.appendChild(summary);
    for (const item of items) {
      details.appendChild(buildAssetRow(item));
    }
    listEl.appendChild(details);
  }
  if (!any) {
    listEl.textContent = "暂无图片/表格资产";
  }
}

function buildAssetRow(item) {
  const row = document.createElement("div");
  row.className = "asset-row";
  row.dataset.ref = item.ref;
  if (state.activeAssetRef === item.ref) {
    row.classList.add("active");
  }

  const main = document.createElement("div");
  main.className = "asset-row-main";

  const refEl = document.createElement("span");
  refEl.className = "asset-ref";
  refEl.textContent = item.ref;
  refEl.title = item.ref;
  main.appendChild(refEl);

  const detailBtn = document.createElement("button");
  detailBtn.type = "button";
  detailBtn.className = "asset-detail-btn";
  detailBtn.textContent = "查看详情";
  detailBtn.onclick = (event) => {
    event.stopPropagation();
    if (item.asset_type === "image") {
      openImagePreview(item.ref);
    } else {
      downloadTableDocx(item.ref);
    }
  };
  main.appendChild(detailBtn);
  row.appendChild(main);

  if (item.preview) {
    const preview = document.createElement("div");
    preview.className = "asset-preview";
    preview.textContent = item.preview;
    preview.title = item.preview;
    row.appendChild(preview);
  }

  row.onclick = () => {
    focusAssetInDocument(item).catch(console.error);
  };
  return row;
}

function openImagePreview(ref) {
  const modal = document.getElementById("image-preview-modal");
  document.getElementById("image-preview-ref").textContent = ref;
  document.getElementById("image-preview-img").src =
    `/api/sessions/${state.sessionId}/assets/${ref}`;
  modal.hidden = false;
}

function closeImagePreview() {
  document.getElementById("image-preview-modal").hidden = true;
  document.getElementById("image-preview-img").src = "";
}

function downloadTableDocx(ref) {
  const url = `/api/sessions/${state.sessionId}/tables/${encodeURIComponent(ref)}/export.docx`;
  window.location.assign(url);
}

async function focusAssetInDocument(asset) {
  if (!asset.outline_node_id || asset.char_start == null) {
    setProgress("无法定位该资产");
    return;
  }
  state.activeAssetRef = asset.ref;
  document.querySelectorAll(".asset-row").forEach((row) => {
    row.classList.toggle("active", row.dataset.ref === asset.ref);
  });
  if (state.selectedNodeId !== asset.outline_node_id) {
    await selectNode(asset.outline_node_id, { preserveAssetFocus: true });
  }
  highlightAssetInContent(asset);
  setProgress("", true);
}

function highlightAssetInContent(asset) {
  document.querySelectorAll(".asset-highlight").forEach((el) => {
    el.classList.remove("asset-highlight");
  });
  const panel = document.getElementById("content-panel");
  let target = null;
  if (asset.asset_type === "image") {
    target = panel.querySelector(`img[src*="${asset.ref}"]`);
  } else {
    target = panel.querySelector("table");
  }
  if (target) {
    target.classList.add("asset-highlight");
    target.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

function renderNodes(nodes, depth) {
  const ul = document.createElement("ul");
  for (const node of nodes) {
    const li = document.createElement("li");
    const row = document.createElement("div");
    row.className = "tree-row";
    row.style.paddingLeft = `${depth * 12 + 4}px`;

    const hasChildren = Boolean(node.children?.length);
    if (hasChildren) {
      const collapsed = state.collapsedNodeIds.has(node.node_id);
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "tree-toggle";
      toggle.textContent = collapsed ? "▸" : "▾";
      toggle.setAttribute("aria-expanded", String(!collapsed));
      toggle.setAttribute("aria-label", collapsed ? "展开" : "收起");
      toggle.onclick = (event) => {
        event.stopPropagation();
        const childUl = li.querySelector(":scope > ul");
        if (!childUl) return;
        const willCollapse = !childUl.hidden;
        childUl.hidden = willCollapse;
        toggle.textContent = willCollapse ? "▸" : "▾";
        toggle.setAttribute("aria-expanded", String(!willCollapse));
        toggle.setAttribute("aria-label", willCollapse ? "展开" : "收起");
        if (willCollapse) {
          state.collapsedNodeIds.add(node.node_id);
        } else {
          state.collapsedNodeIds.delete(node.node_id);
        }
      };
      row.appendChild(toggle);
    } else {
      const spacer = document.createElement("span");
      spacer.className = "tree-toggle-spacer";
      spacer.setAttribute("aria-hidden", "true");
      row.appendChild(spacer);
    }

    const btn = document.createElement("button");
    btn.className = "tree-node";
    btn.type = "button";
    btn.dataset.nodeId = node.node_id;
    btn.textContent = (node.needs_review ? "⚠ " : "") + node.title;
    btn.onclick = () => selectNode(node.node_id);
    row.appendChild(btn);
    li.appendChild(row);

    if (hasChildren) {
      const childUl = renderNodes(node.children, depth + 1);
      childUl.hidden = state.collapsedNodeIds.has(node.node_id);
      li.appendChild(childUl);
    }
    ul.appendChild(li);
  }
  return ul;
}

async function selectNode(nodeId, options = {}) {
  if (!options.preserveAssetFocus) {
    clearAssetHighlight();
  }
  state.selectedNodeId = nodeId;
  markTreeSelection(nodeId);
  const section = await api(`/api/sessions/${state.sessionId}/sections/${nodeId}`);
  state.currentSectionMarkdown = section.markdown;
  const markdown = rewriteAssetUrls(section.markdown, state.sessionId);
  const html = marked.parse(markdown, {
    mangle: false,
    headerIds: false,
  });
  document.getElementById("content-panel").innerHTML = html;
  const pathLabel =
    section.section_path?.length ? section.section_path.join(" › ") : section.title;
  document.getElementById("section-meta-text").textContent =
    `${pathLabel} · char: ${section.char_start}–${section.char_end} · needs_review: ${section.needs_review}`;
  document.getElementById("section-meta").hidden = false;
}

async function copySectionMarkdown() {
  const markdown = state.currentSectionMarkdown;
  if (!markdown) return;
  const button = document.getElementById("copy-markdown-btn");
  try {
    await navigator.clipboard.writeText(markdown);
    const originalText = button.textContent;
    button.textContent = "已复制";
    setTimeout(() => {
      button.textContent = originalText;
    }, 1500);
  } catch (err) {
    console.error(err);
    setProgress("复制失败，请检查浏览器剪贴板权限");
  }
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
    state.collapsedNodeIds = new Set();
    clearSectionView();
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
    state.collapsedNodeIds = new Set();
    clearSectionView();
    await refreshSessions();
    await loadOutline();
  } catch (err) {
    setProgress(err.message || "open workspace failed");
    console.error(err);
  }
});

document.getElementById("reextract-btn").addEventListener("click", async () => {
  if (!state.sessionId) {
    setProgress("请先选择会话");
    return;
  }
  if (!confirm("将删除当前工作区输出并重新提取，是否继续？")) {
    return;
  }
  try {
    const result = await api(`/api/sessions/${state.sessionId}/reextract`, { method: "POST" });
    state.selectedNodeId = null;
    state.collapsedNodeIds = new Set();
    clearSectionView();
    await refreshSessions();
    await pollJob(result.job_id);
  } catch (err) {
    setProgress(err.message || "re-extract failed");
    console.error(err);
  }
});

document.getElementById("session-select").addEventListener("change", async (event) => {
  state.sessionId = event.target.value || null;
  state.selectedNodeId = null;
  state.collapsedNodeIds = new Set();
  clearSectionView();
  try {
    await loadOutline();
  } catch (err) {
    setProgress(err.message || "load outline failed");
    console.error(err);
  }
});

document.getElementById("delete-session-btn").addEventListener("click", async () => {
  if (!state.sessionId) {
    setProgress("请先选择会话");
    return;
  }
  if (!confirm("将永久删除该会话、工作区与上传文件，是否继续？")) {
    return;
  }
  try {
    await api(`/api/sessions/${state.sessionId}`, { method: "DELETE" });
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
    state.sessionId = null;
    state.selectedNodeId = null;
    state.collapsedNodeIds = new Set();
    clearSectionView();
    document.getElementById("outline-meta").textContent = "";
    document.getElementById("outline-tree").innerHTML = "";
    document.getElementById("assets-list").textContent = "—";
    setProgress("", true);
    await refreshSessions();
  } catch (err) {
    setProgress(err.message || "删除会话失败");
    console.error(err);
  }
});

document.getElementById("copy-markdown-btn").addEventListener("click", () => {
  copySectionMarkdown().catch(console.error);
});

document.getElementById("close-image-preview").addEventListener("click", closeImagePreview);
document.getElementById("image-preview-backdrop").addEventListener("click", closeImagePreview);

async function bootstrapFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("session");
  const nodeId = params.get("node");
  await refreshSessions();
  if (sessionId) {
    state.sessionId = sessionId;
    const select = document.getElementById("session-select");
    if (select) {
      select.value = sessionId;
    }
    await loadOutline();
    if (nodeId) {
      state.selectedNodeId = nodeId;
      await selectNode(nodeId);
    }
  }
}

bootstrapFromUrl().catch(console.error);
