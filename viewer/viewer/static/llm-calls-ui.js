/** Incremental LLM call list updates — preserve expanded <details> while polling. */
(function () {
  function llmCallKey(call) {
    return `${call.call_type || "call"}:${call.segment_id || call.timestamp || "unknown"}`;
  }

  function llmCallSignature(call) {
    return JSON.stringify({
      t: call.timestamp,
      r: Boolean(call.response),
      a: call.attempts?.length ?? 0,
      m: call.messages?.length ?? 0,
      rc: call.response?.length ?? 0,
    });
  }

  function captureDetailsOpenState(root) {
    const byKey = new Map();
    if (!root) {
      return byKey;
    }
    root.querySelectorAll("[data-call-key]").forEach((card) => {
      const key = card.dataset.callKey;
      const open = [];
      card.querySelectorAll("details").forEach((detail, index) => {
        if (detail.open) {
          const label = detail.querySelector("summary")?.textContent?.trim() || String(index);
          open.push(label);
        }
      });
      if (open.length) {
        byKey.set(key, open);
      }
    });
    return byKey;
  }

  function restoreDetailsOpenState(card, openLabels) {
    if (!openLabels?.length) {
      return;
    }
    const labels = new Set(openLabels);
    card.querySelectorAll("details").forEach((detail, index) => {
      const label = detail.querySelector("summary")?.textContent?.trim() || String(index);
      if (labels.has(label)) {
        detail.open = true;
      }
    });
  }

  function syncLlmCallCards(container, calls, { renderCard, emptyHint = "暂无记录" }) {
    if (!container) {
      return;
    }

    const openState = captureDetailsOpenState(container);
    const existing = new Map();
    container.querySelectorAll("[data-call-key]").forEach((el) => {
      existing.set(el.dataset.callKey, el);
    });

    if (!calls?.length) {
      if (existing.size === 0 && !container.querySelector(".llm-calls-empty")) {
        container.innerHTML = `<p class="empty-tab llm-calls-empty">${emptyHint}</p>`;
      }
      return;
    }

    const emptyEl = container.querySelector(".llm-calls-empty");
    if (emptyEl) {
      emptyEl.remove();
    }

    const seen = new Set();
    for (const call of calls) {
      const key = llmCallKey(call);
      const sig = llmCallSignature(call);
      seen.add(key);
      const prev = existing.get(key);
      if (prev && prev.dataset.callSig === sig) {
        continue;
      }
      const card = renderCard(call);
      card.dataset.callKey = key;
      card.dataset.callSig = sig;
      restoreDetailsOpenState(card, openState.get(key));
      if (prev) {
        prev.replaceWith(card);
      } else {
        container.appendChild(card);
      }
    }

    for (const [key, el] of existing) {
      if (!seen.has(key)) {
        el.remove();
      }
    }
  }

  window.LlmCallsUi = {
    llmCallKey,
    llmCallSignature,
    captureDetailsOpenState,
    restoreDetailsOpenState,
    syncLlmCallCards,
  };
})();
