/* InsurIntellect UI — wired to clause RAG APIs.
 * Structure mirrors chat-pdf / chatpdf-yt / AnythingLLM patterns in static HTML/CSS.
 */
(function () {
  const thread = document.getElementById("thread");
  const emptyState = document.getElementById("emptyState");
  const form = document.getElementById("askForm");
  const input = document.getElementById("messageInput");
  const sendButton = document.getElementById("sendButton");
  const streamToggle = document.getElementById("streamToggle");
  const clearBtn = document.getElementById("clearBtn");
  const resetBtn = document.getElementById("resetBtn");
  const docList = document.getElementById("docList");
  const corpusCount = document.getElementById("corpusCount");
  const healthDot = document.getElementById("healthDot");
  const healthText = document.getElementById("healthText");

  let busy = false;
  let abortController = null;
  let emptyHTML = emptyState ? emptyState.outerHTML : "";
  let activeDoc = null;

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setBusy(v) {
    busy = v;
    sendButton.disabled = v;
    input.disabled = v;
    if (resetBtn) resetBtn.disabled = false;
  }

  function hideEmpty() {
    const el = document.getElementById("emptyState");
    if (el) el.remove();
  }

  function showEmpty() {
    thread.innerHTML = emptyHTML;
    bindPromptCards();
  }

  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(Math.max(input.scrollHeight, 100), 180) + "px";
  }

  function formatAnswerHtml(text) {
    const raw = String(text ?? "");
    const escaped = escapeHtml(raw);
    return escaped
      .replace(
        /^(【[^】]+】|[一二三四五六七八九十]+[、.．]|结论|条款依据|不确定[/／]?边界)([^\n]*)/gm,
        function (_m, head, rest) {
          return '<span class="sec-head">' + head + (rest || "") + "</span>";
        }
      )
      .replace(/\[(\d+)\]/g, '<a class="cite-ref" href="#cite-$1">[$1]</a>');
  }

  function createCitationsHtml(sources) {
    if (!sources || !sources.length) {
      return (
        '<div class="citations">' +
        '<div class="citations-head">' +
        '<span class="citations-title">Sources</span>' +
        '<span class="citations-note">0</span>' +
        "</div>" +
        '<div class="cite-grid">' +
        '<div class="cite-card is-empty">本次无可用引用片段（检索为空、低分拒答，或仅返回边界说明）。</div>' +
        "</div></div>"
      );
    }

    const pills = sources
      .slice(0, 3)
      .map(function (_s, i) {
        return (
          '<span class="cite-pill-dot" title="source ' +
          (i + 1) +
          '">' +
          (i + 1) +
          "</span>"
        );
      })
      .join("");

    const cards = sources
      .map(function (s, i) {
        const name = s.document_name || s.source || s.filename || "未知文档";
        const page = s.page_number ?? s.page ?? "—";
        const excerpt = String(s.content || s.excerpt || s.text || "").slice(0, 220);
        const score = s.similarity_score;
        const scoreText =
          typeof score === "number" && !Number.isNaN(score)
            ? "score " + score.toFixed(3)
            : "";
        return (
          '<article class="cite-card" id="cite-' +
          (i + 1) +
          '">' +
          '<div class="cite-top">' +
          '<span class="cite-idx">[' +
          (i + 1) +
          "]</span>" +
          '<span class="cite-doc" title="' +
          escapeHtml(name) +
          '">' +
          escapeHtml(name) +
          "</span>" +
          '<span class="cite-page">p.' +
          escapeHtml(String(page)) +
          "</span>" +
          "</div>" +
          '<div class="cite-excerpt">' +
          escapeHtml(excerpt) +
          "</div>" +
          (scoreText ? '<div class="cite-score">' + scoreText + "</div>" : "") +
          "</article>"
        );
      })
      .join("");

    return (
      '<div class="citations">' +
      '<div class="citations-head">' +
      '<span class="citations-title">Sources</span>' +
      '<span class="citations-note">' +
      sources.length +
      "</span>" +
      '<div class="cite-pills">' +
      pills +
      (sources.length > 3
        ? '<span class="citations-note">+ ' + (sources.length - 3) + "</span>"
        : "") +
      "</div>" +
      "</div>" +
      '<div class="cite-grid">' +
      cards +
      "</div></div>"
    );
  }

  function appendMessage(role, contentHtml, extraClass) {
    hideEmpty();
    const row = document.createElement("div");
    row.className =
      "msg-row is-" + role + (extraClass ? " " + extraClass : "");
    const avatar = role === "user" ? "●" : "✦";
    row.innerHTML =
      '<div class="msg-inner">' +
      '<div class="msg-avatar" aria-hidden="true">' +
      avatar +
      "</div>" +
      '<div class="msg-body">' +
      contentHtml +
      "</div>" +
      "</div>";
    thread.appendChild(row);
    thread.scrollTop = thread.scrollHeight;
    return row;
  }

  function setAssistantContent(row, answerHtml, sources) {
    const body = row.querySelector(".msg-body");
    if (!body) return;
    body.innerHTML = answerHtml + createCitationsHtml(sources || []);
    row.classList.remove("is-pending");
    thread.scrollTop = thread.scrollHeight;
  }

  function normalizeSources(data) {
    if (!data) return [];
    if (Array.isArray(data.retrieved_chunks) && data.retrieved_chunks.length) {
      return data.retrieved_chunks;
    }
    if (Array.isArray(data.sources)) return data.sources;
    if (Array.isArray(data.citations)) return data.citations;
    return [];
  }

  async function loadCorpus() {
    try {
      const res = await fetch("/api/v1/corpus");
      if (!res.ok) throw new Error("corpus " + res.status);
      const data = await res.json();
      const docs = data.documents || data.items || data.docs || [];
      const totalChunks = data.total_chunks ?? data.chunk_count ?? null;
      corpusCount.textContent =
        docs.length +
        " docs" +
        (totalChunks != null ? " · " + totalChunks + " chunks" : "");

      if (!docs.length) {
        docList.innerHTML =
          '<div class="doc-empty">暂无已索引文档。请运行 sample corpus + ingest。</div>';
        return;
      }

      docList.innerHTML = docs
        .map(function (d, idx) {
          const name =
            d.name || d.document_name || d.filename || d.title || "document";
          const chunks = d.chunk_count ?? d.chunks ?? d.n_chunks ?? "—";
          const id = d.id || d.document_id || name;
          const active = activeDoc === id || (activeDoc == null && idx === 0);
          if (activeDoc == null && idx === 0) activeDoc = id;
          return (
            '<button type="button" class="doc-item' +
            (active ? " is-active" : "") +
            '" data-id="' +
            escapeHtml(String(id)) +
            '" role="listitem">' +
            '<span class="doc-item-icon">PDF</span>' +
            '<span class="doc-item-body">' +
            '<span class="doc-item-name">' +
            escapeHtml(name) +
            "</span>" +
            '<span class="doc-item-meta">' +
            escapeHtml(String(chunks)) +
            " chunks</span>" +
            "</span></button>"
          );
        })
        .join("");

      docList.querySelectorAll(".doc-item").forEach(function (btn) {
        btn.addEventListener("click", function () {
          activeDoc = btn.getAttribute("data-id");
          docList.querySelectorAll(".doc-item").forEach(function (el) {
            el.classList.toggle("is-active", el === btn);
          });
        });
      });
    } catch (err) {
      docList.innerHTML =
        '<div class="doc-empty">无法加载语料：' +
        escapeHtml(err.message || String(err)) +
        "</div>";
      corpusCount.textContent = "error";
    }
  }

  async function loadHealth() {
    try {
      const res = await fetch("/api/v1/health/");
      if (!res.ok) throw new Error("health " + res.status);
      const data = await res.json();
      const status = (data.status || data.overall || "ok").toLowerCase();
      healthDot.classList.remove("ok", "warn", "err");
      if (status === "ok" || status === "healthy" || status === "up") {
        healthDot.classList.add("ok");
        healthText.textContent = "healthy";
      } else if (status === "degraded" || status === "warn") {
        healthDot.classList.add("warn");
        healthText.textContent = status;
      } else {
        healthDot.classList.add("err");
        healthText.textContent = status;
      }
      const llm = data.llm_status || (data.components && data.components.llm);
      if (llm && /unavail|down|error|missing/i.test(String(llm))) {
        healthDot.classList.remove("ok");
        healthDot.classList.add("warn");
        healthText.textContent = "llm " + llm;
      }
    } catch (err) {
      healthDot.classList.add("err");
      healthText.textContent = "offline";
    }
  }

  async function askOnce(question) {
    const res = await fetch("/api/v1/queries/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, stream: false, show_sources: true }),
      signal: abortController ? abortController.signal : undefined,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok && !data.answer) {
      throw new Error(data.detail || data.message || "ask failed " + res.status);
    }
    return data;
  }

  async function askStream(question, onDelta, onFinal) {
    const res = await fetch("/api/v1/queries/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, stream: true, show_sources: true }),
      signal: abortController ? abortController.signal : undefined,
    });
    if (!res.ok) {
      const errData = await res.json().catch(function () {
        return {};
      });
      throw new Error(errData.detail || errData.message || "stream failed " + res.status);
    }
    if (!res.body || !res.body.getReader) {
      const data = await res.json();
      onFinal(data);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let full = "";
    let finalPayload = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n");
      buffer = parts.pop() || "";
      for (let i = 0; i < parts.length; i++) {
        const line = parts[i].trim();
        if (!line) continue;
        let payload = line;
        if (payload.startsWith("data:")) payload = payload.slice(5).trim();
        if (!payload || payload === "[DONE]") continue;
        try {
          const obj = JSON.parse(payload);
          if (obj.type === "token" || obj.delta || obj.token) {
            const t = obj.token || obj.delta || obj.content || "";
            full += t;
            onDelta(full);
          } else if (obj.type === "final" || obj.answer || obj.retrieved_chunks) {
            finalPayload = obj.data || obj;
            if (obj.answer) finalPayload = obj;
          } else if (obj.answer) {
            finalPayload = obj;
          }
        } catch (_e) {
          full += payload;
          onDelta(full);
        }
      }
    }

    if (finalPayload) {
      onFinal(finalPayload);
    } else {
      onFinal({ answer: full, retrieved_chunks: [] });
    }
  }

  async function handleAsk(question) {
    const q = String(question || "").trim();
    if (!q || busy) return;

    setBusy(true);
    abortController = new AbortController();
    appendMessage("user", escapeHtml(q));
    const assistantRow = appendMessage(
      "assistant",
      "正在检索条款并生成带引用答案…",
      "is-pending"
    );

    try {
      if (streamToggle && streamToggle.checked) {
        await askStream(
          q,
          function (partial) {
            setAssistantContent(assistantRow, formatAnswerHtml(partial), []);
            assistantRow.classList.add("is-pending");
          },
          function (data) {
            const answer = data.answer || data.response || "";
            setAssistantContent(
              assistantRow,
              formatAnswerHtml(answer),
              normalizeSources(data)
            );
          }
        );
      } else {
        const data = await askOnce(q);
        const answer = data.answer || data.response || "(空响应)";
        setAssistantContent(
          assistantRow,
          formatAnswerHtml(answer),
          normalizeSources(data)
        );
      }
    } catch (err) {
      if (err.name === "AbortError") {
        setAssistantContent(assistantRow, "已取消。", []);
      } else {
        setAssistantContent(
          assistantRow,
          '<span style="color:#991b1b">请求失败：' +
            escapeHtml(err.message || String(err)) +
            "</span>",
          []
        );
      }
    } finally {
      setBusy(false);
      abortController = null;
      input.value = "";
      autoGrow();
      input.focus();
    }
  }

  function bindPromptCards() {
    document.querySelectorAll(".prompt-card").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const q = btn.getAttribute("data-q") || btn.textContent;
        handleAsk(q);
      });
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    handleAsk(input.value);
  });

  input.addEventListener("input", autoGrow);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk(input.value);
    }
  });

  function resetChat() {
    if (abortController) abortController.abort();
    setBusy(false);
    showEmpty();
    input.value = "";
    autoGrow();
    input.focus();
  }

  if (clearBtn) clearBtn.addEventListener("click", resetChat);
  if (resetBtn) resetBtn.addEventListener("click", resetChat);

  bindPromptCards();
  loadCorpus();
  loadHealth();
  autoGrow();
})();
