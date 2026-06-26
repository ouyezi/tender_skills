/** Shared DOM builders for interpret / gen-catalog LLM call cards. */
(function () {
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
  }

  function buildLlmCallCard(call, { title, subtitle }) {
    const card = document.createElement("article");
    card.className = "result-card llm-call-card";
    let body = `<h3>${escapeHtml(title)}</h3>`;
    if (subtitle) {
      body += `<p class="card-path">${escapeHtml(subtitle)}</p>`;
    }
    if (call.timestamp) {
      body += `<p class="card-meta">${escapeHtml(call.timestamp)}</p>`;
    }
    if (call.token_estimate != null) {
      body += `<p><strong>token 估计：</strong>${call.token_estimate}</p>`;
    }
    if (call.messages?.length) {
      body += `<details><summary>Prompt（${call.messages.length} 条消息）</summary><pre class="llm-payload">${escapeHtml(
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
    return card;
  }

  window.LlmCallCard = { buildLlmCallCard, escapeHtml };
})();
