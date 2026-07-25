/* InsurIntellect clause RAG UI — document-evidence workspace (single main path) */
(function () {
  const thread = document.getElementById("thread");
  const emptyState = document.getElementById("emptyState");
  const form = document.getElementById("askForm");
  const input = document.getElementById("messageInput");
  const sendButton = document.getElementById("sendButton");
  const streamToggle = document.getElementById("streamToggle");
  const clearBtn = document.getElementById("clearBtn");
  const docList = document.getElementById("docList");
  const corpusCount = document.getElementById("corpusCount");
  const healthDot = document.getElementById("healthDot");
  const healthText = document.getElementById("healthText");

  let busy = false;
  let abortController = null;
  let emptyHTML = emptyState ? emptyState.outerHTML : "";

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
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  }

  /** Format answer: section headers + [n] cite chips (Perplexity rhythm) */
  function formatAnswerHtml(text) {
    const raw = String(text ?? "");
    const escaped = escapeHtml(raw);
    return escaped
      .replace(
        /^(【[^】]+】|[一二三四五六七八九十]+[、.．]|结论|条款依据|不确定[/／]?边界)([^\n]*)/gm,
        function (_m, head, rest) {
          return (
            '<span class="sec-head">' +
            head +
            (rest || "") +
            "</span>"
          );
        }
      )
      .replace(/\[(\d+)\]/g, '<span class="cite-ref">[$1]</span>');
  }

  function createCitationsHtml(sources) {
    if (!sources || !sources.length) {
      return (
        '<div class="citations">' +
        '<div class="citations-head">' +
        '<span class="citations-title">来源</span>' +
        '<span class="citations-note">0</span>' +
        "</div>" +
        '<div class="cite-grid">' +
        '<div class="cite-card is-empty">本次无可用引用片段（检索为空、低分拒答，或仅返回边界说明）。</div>' +
        "</div></div>"
      );
    }

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
          escapeHtml(page) +
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
      '<span class="citations-title">来源</span>' +
      '<span class="citations-note">' +
      sources.length +
      " chunks</span>" +
      "</div>" +
      '<div class="cite-grid">' +
      cards +
      "</div></div>"
    );
  }

  function normalizeSources(data) {
    if (!data) return [];
    if (Array.isArray(data.retrieved_chunks)) return data.retrieved_chunks;
    if (Array.isArray(data.sources)) return data.sources;
    return [];
  }

  function addTurn(question, answer, sources, opts) {
    hideEmpty();
    opts = opts || {};
    const el = document.createElement("article");
    el.className =
      "turn" +
      (opts.pending ? " is-pending" : "") +
      (opts.error ? " is-error" : "");
    el.innerHTML =
      '<div class="q-block">' +
      '<div class="turn-label">问</div>' +
      '<div class="q-text">' +
      escapeHtml(question) +
      "</div>" +
      "</div>" +
      '<div class="a-block">' +
      '<div class="turn-label">答</div>' +
      "<div>" +
      '<div class="a-text">' +
      (opts.pending
        ? escapeHtml(answer || "检索中…")
        : formatAnswerHtml(answer || "")) +
      "</div>" +
      (opts.pending ? "" : createCitationsHtml(sources)) +
      "</div></div>";
    thread.appendChild(el);
    thread.scrollTop = thread.scrollHeight;
    return el;
  }

  function finalizeTurn(el, answer, sources, isError) {
    el.classList.remove("is-pending");
    if (isError) el.classList.add("is-error");
    const aText = el.querySelector(".a-text");
    if (aText) {
      if (isError) aText.textContent = answer || "请求失败";
      else aText.innerHTML = formatAnswerHtml(answer || "(空回答)");
    }
    const old = el.querySelector(".citations");
    if (old) old.remove();
    const host = el.querySelector(".a-block > div:last-child");
    if (host) host.insertAdjacentHTML("beforeend", createCitationsHtml(sources || []));
    thread.scrollTop = thread.scrollHeight;
  }

  async function loadCorpus() {
    try {
      const res = await fetch("/api/v1/corpus");
      if (!res.ok) throw new Error("corpus " + res.status);
      const data = await res.json();
      const docs = data.documents || [];
      if (!docs.length) {
        docList.innerHTML =
          '<div class="source-empty">暂无来源。请运行 generate_sample_corpus.py 与 simple_ingest.py</div>';
        corpusCount.textContent = "0";
        return;
      }
      docList.innerHTML = docs
        .map(function (d) {
          const name = d.name || d.filename || "document";
          const pages = d.pages != null ? d.pages + " p" : "PDF";
          return (
            '<div class="source-item" role="listitem" title="' +
            escapeHtml(name) +
            '">' +
            '<div class="source-icon">PDF</div>' +
            '<div class="source-body">' +
            '<div class="source-name">' +
            escapeHtml(name) +
            "</div>" +
            '<div class="source-meta">' +
            escapeHtml(pages) +
            "</div>" +
            "</div></div>"
          );
        })
        .join("");
      corpusCount.textContent =
        docs.length + " · " + (data.chunk_count || 0) + " chunks";
    } catch (e) {
      docList.innerHTML =
        '<div class="source-empty">无法加载来源（' +
        escapeHtml(e.message || e) +
        "）</div>";
      corpusCount.textContent = "err";
    }
  }

  async function loadHealth() {
    try {
      const res = await fetch("/api/v1/health/");
      const data = await res.json();
      const ok = data.status === "healthy";
      healthText.textContent = ok ? "healthy" : data.status || "degraded";
      healthDot.className = "dot " + (ok ? "ok" : "bad");
    } catch (_e) {
      healthText.textContent = "offline";
      healthDot.className = "dot bad";
    }
  }

  async function ask(question) {
    const q = (question || "").trim();
    if (!q || busy) return;
    input.value = "";
    autoGrow();
    setBusy(true);

    const useStream = !!(streamToggle && streamToggle.checked);
    const turn = addTurn(q, "检索中…", [], { pending: true });

    try {
      if (useStream) {
        await askStream(q, turn);
      } else {
        await askOnce(q, turn);
      }
    } catch (e) {
      finalizeTurn(turn, "请求失败：" + (e.message || e), [], true);
    } finally {
      setBusy(false);
    }
  }

  async function askOnce(question, turn) {
    const res = await fetch("/api/v1/queries/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: question,
        stream: false,
        show_sources: true,
        query_type: "general",
      }),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(res.status + " " + t.slice(0, 200));
    }
    const data = await res.json();
    finalizeTurn(turn, data.answer || "(空回答)", normalizeSources(data), false);
  }

  async function askStream(question, turn) {
    abortController = new AbortController();
    const res = await fetch("/api/v1/queries/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: question,
        stream: true,
        show_sources: true,
        query_type: "general",
      }),
      signal: abortController.signal,
    });
    if (!res.ok || !res.body) {
      return askOnce(question, turn);
    }

    const aText = turn.querySelector(".a-text");
    turn.classList.remove("is-pending");
    let buffer = "";
    let sources = [];
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    let dataLines = [];

    const flushEvent = function () {
      const raw = dataLines.join("\n");
      dataLines = [];
      if (!raw) return;
      try {
        const payload = JSON.parse(raw);
        if (payload.type === "token" || payload.text) {
          buffer += payload.text || payload.token || "";
          if (aText) aText.textContent = buffer;
        }
        if (payload.type === "context" || payload.retrieved_chunks) {
          sources = normalizeSources(payload);
        }
        if (payload.type === "final" || payload.answer) {
          if (payload.answer) {
            buffer = payload.answer;
            if (aText) aText.textContent = buffer;
          }
          const n = normalizeSources(payload);
          if (n.length) sources = n;
        }
      } catch (_e) {
        buffer += raw;
        if (aText) aText.textContent = buffer;
      }
      thread.scrollTop = thread.scrollHeight;
    };

    while (true) {
      const result = await reader.read();
      if (result.done) break;
      pending += decoder.decode(result.value, { stream: true });
      const lines = pending.split(/\r?\n/);
      pending = lines.pop();
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        } else if (line === "") {
          flushEvent();
        }
      }
    }
    if (dataLines.length) flushEvent();

    finalizeTurn(
      turn,
      buffer || "(流式无内容，可关闭流式重试)",
      sources,
      false
    );
  }

  function bindPromptCards() {
    document.querySelectorAll(".prompt-card").forEach(function (btn) {
      btn.addEventListener("click", function () {
        ask(btn.dataset.q || btn.textContent);
      });
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    ask(input.value);
  });

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      if (busy) return;
      showEmpty();
    });
  }

  input.addEventListener("input", autoGrow);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(input.value);
    }
  });

  bindPromptCards();
  loadCorpus();
  loadHealth();
})();
