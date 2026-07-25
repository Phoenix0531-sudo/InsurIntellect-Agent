/* Citation-first clause RAG UI on chat-pdf dual-pane shell.
 * Product: ask → curated citations → left PDF + evidence strip.
 * Untrusted answer/source text always goes through escapeHtml before innerHTML.
 */
(function () {
  const pdfSelect = document.getElementById("pdfSelect");
  const pdfEmpty = document.getElementById("pdfEmpty");
  const pdfFrame = document.getElementById("pdfFrame");
  const pdfTitle = document.getElementById("pdfTitle");
  const pdfSubtitle = document.getElementById("pdfSubtitle");
  const pageBadge = document.getElementById("pageBadge");
  const evidenceStrip = document.getElementById("evidenceStrip");
  const evidenceCite = document.getElementById("evidenceCite");
  const evidenceExcerpt = document.getElementById("evidenceExcerpt");
  const corpusMeta = document.getElementById("corpusMeta");
  const messagesEl = document.getElementById("messages");
  const emptyChat = document.getElementById("emptyChat");
  const form = document.getElementById("askForm");
  const input = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");
  const resetBtn = document.getElementById("resetBtn");
  const stopBtn = document.getElementById("stopBtn");
  const streamToggle = document.getElementById("streamToggle");
  const genPill = document.getElementById("genPill");
  const errPill = document.getElementById("errPill");
  const healthText = document.getElementById("healthText");
  const panelGroup = document.getElementById("panelGroup");
  const pdfPanel = document.getElementById("pdfPanel");
  const aiPanel = document.getElementById("aiPanel");
  const resizeHandle = document.getElementById("resizeHandle");

  let pdfs = [];
  let activeSources = [];
  let currentView = { name: null, url: null, page: null, index: null };
  let isLoading = false;
  let abortController = null;
  let citeSeq = 0;

  const DISPLAY_FALLBACK = {
    "sample_term_life.pdf": "示例终身寿险条款",
    "sample_critical_illness.pdf": "示例重大疾病保险条款",
  };

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function basename(name) {
    const s = String(name || "");
    const parts = s.replace(/\\/g, "/").split("/");
    return parts[parts.length - 1] || s;
  }

  function displayNameFor(docName, extra) {
    extra = extra || {};
    if (extra.display_name) return extra.display_name;
    if (extra.metadata && extra.metadata.display_name) {
      return extra.metadata.display_name;
    }
    const bare = basename(docName);
    if (DISPLAY_FALLBACK[bare]) return DISPLAY_FALLBACK[bare];
    const hit = resolvePdfByName(docName);
    if (hit && hit.display_name) return hit.display_name;
    return bare || "未知文档";
  }

  function cleanExcerpt(text) {
    let t = String(text || "").replace(/\s+/g, " ").trim();
    // Drop leading pure metadata lines if mixed content later
    t = t
      .replace(/^(文档名称|产品名称|文档类型|生效日期|状态)[：:][^。；;\n]{0,40}[。；;\s]*/g, "")
      .trim();
    if (t.length > 180) t = t.slice(0, 180) + "…";
    return t;
  }

  function resolvePdfByName(docName) {
    if (!docName) return null;
    const bare = basename(docName).toLowerCase();
    return (
      pdfs.find(function (p) {
        return basename(p.name).toLowerCase() === bare;
      }) ||
      pdfs.find(function (p) {
        return (
          basename(p.name).toLowerCase().includes(bare) ||
          bare.includes(basename(p.name).toLowerCase())
        );
      }) ||
      null
    );
  }

  function setEvidence(source, index) {
    if (!evidenceStrip) return;
    if (!source) {
      evidenceStrip.hidden = true;
      if (evidenceCite) evidenceCite.textContent = "";
      if (evidenceExcerpt) evidenceExcerpt.textContent = "";
      return;
    }
    const name = displayNameFor(
      source.document_name || source.source || source.filename,
      source
    );
    const page = source.page_number ?? source.page;
    const excerpt = cleanExcerpt(
      source.content || source.excerpt || source.text || ""
    );
    evidenceStrip.hidden = false;
    evidenceCite.textContent =
      "[" +
      (index || "?") +
      "] " +
      name +
      (page != null && page !== "" ? " · p." + page : "");
    evidenceExcerpt.textContent = excerpt || "（无摘录）";
  }

  function openCitedPdf(docName, pageNumber, source, index, opts) {
    opts = opts || {};
    const hit = resolvePdfByName(docName);
    if (!hit || !hit.url) {
      if (opts.forceEmpty !== false) {
        pdfFrame.hidden = true;
        pdfFrame.removeAttribute("src");
        pdfEmpty.hidden = false;
        pdfSelect.hidden = true;
        pageBadge.hidden = true;
        pdfTitle.textContent = "引用原文";
        pdfSubtitle.textContent = "暂未匹配到可打开的条款 PDF";
        setEvidence(null);
      }
      return false;
    }

    const page =
      pageNumber != null && pageNumber !== "" && !Number.isNaN(Number(pageNumber))
        ? Number(pageNumber)
        : null;

    const hash = page && page > 0 ? "#page=" + page : "";
    const nextSrc = hit.url + hash;
    pdfEmpty.hidden = true;
    pdfFrame.hidden = false;
    if (pdfFrame.getAttribute("src") !== nextSrc) {
      pdfFrame.src = nextSrc;
    }

    currentView = {
      name: hit.name,
      url: hit.url,
      page: page,
      index: index || null,
    };
    const nice = hit.display_name || displayNameFor(hit.name, source || {});
    pdfTitle.textContent = nice;
    pdfSubtitle.textContent = page
      ? "定位到引用页 p." + page
      : "答案引用的条款原文";
    if (page) {
      pageBadge.hidden = false;
      pageBadge.textContent = "p." + page;
    } else {
      pageBadge.hidden = true;
      pageBadge.textContent = "";
    }

    if (pdfs.length) {
      pdfSelect.hidden = false;
      pdfSelect.innerHTML = pdfs
        .map(function (p) {
          const sel = p.url === hit.url ? " selected" : "";
          const label = p.display_name || displayNameFor(p.name, p);
          return (
            '<option value="' +
            escapeHtml(p.url) +
            '"' +
            sel +
            ">" +
            escapeHtml(label) +
            "</option>"
          );
        })
        .join("");
    }

    if (source) setEvidence(source, index);
    return true;
  }

  function firstAnswerCiteIndex(answerText) {
    const m = String(answerText || "").match(/\[(\d+)\]/);
    if (!m) return 1;
    const n = parseInt(m[1], 10);
    return n > 0 ? n : 1;
  }

  function followAnswerCitation(sources, answerText) {
    activeSources = Array.isArray(sources) ? sources : [];
    if (!activeSources.length) {
      pdfTitle.textContent = "引用原文";
      pdfSubtitle.textContent = "本次回答没有可用引用";
      setEvidence(null);
      return;
    }
    let idx = firstAnswerCiteIndex(answerText);
    if (idx > activeSources.length) idx = 1;
    const src = activeSources[idx - 1];
    openCitedPdf(
      src.document_name || src.source || src.filename,
      src.page_number ?? src.page,
      src,
      idx,
      {}
    );
  }

  function setLoading(v) {
    isLoading = v;
    sendBtn.disabled = v || !String(input.value || "").trim();
    if (genPill) genPill.hidden = !v;
    if (stopBtn) stopBtn.hidden = !v;
    const lastIcon = messagesEl.querySelector(
      ".message.is-assistant:last-child .message-icon"
    );
    if (lastIcon) lastIcon.classList.toggle("spin", v);
  }

  function showError(msg) {
    if (!errPill) return;
    if (!msg) {
      errPill.hidden = true;
      errPill.textContent = "";
      return;
    }
    errPill.hidden = false;
    errPill.textContent = "错误：" + msg;
  }

  async function loadCorpus() {
    try {
      const res = await fetch("/api/v1/corpus");
      if (!res.ok) throw new Error("语料接口 " + res.status);
      const data = await res.json();
      const docs = data.documents || [];
      pdfs = docs
        .map(function (d) {
          const name = d.name || d.document_name || d.filename || "document.pdf";
          let url = d.url;
          if (!url && name) url = "/samples/" + encodeURIComponent(name);
          return {
            name: name,
            url: url,
            pages: d.pages,
            display_name:
              d.display_name || DISPLAY_FALLBACK[basename(name)] || null,
          };
        })
        .filter(function (p) {
          return !!p.url;
        });

      const chunks = data.chunk_count != null ? data.chunk_count : "—";
      corpusMeta.textContent = pdfs.length + " 份文档 · " + chunks + " 片段";
    } catch (err) {
      corpusMeta.textContent = "语料加载失败";
      showError(err.message || String(err));
    }
  }

  async function loadHealth() {
    try {
      const res = await fetch("/api/v1/health/");
      if (!res.ok) throw new Error("health " + res.status);
      const data = await res.json();
      const st = (data.status || "ok").toLowerCase();
      healthText.textContent =
        st === "healthy" || st === "ok" ? "服务正常" : st;
    } catch (_e) {
      healthText.textContent = "离线";
    }
  }

  function linkCitations(escapedText) {
    return escapedText.replace(/\[(\d+)\]/g, function (_m, n) {
      return (
        '<button type="button" class="cite-ref" data-cite-index="' +
        n +
        '" title="打开引用 [' +
        n +
        ']">[' +
        n +
        "]</button>"
      );
    });
  }

  function formatAnswerHtml(text) {
    const raw = String(text || "");
    // Prefer structured sections when backend uses 【结论】【条款依据】【不确定/边界】
    const sectionRe =
      /【\s*(结论|条款依据|不确定[/／]?边界|边界)\s*】\s*([\s\S]*?)(?=【\s*(?:结论|条款依据|不确定[/／]?边界|边界)\s*】|$)/g;
    const parts = [];
    let m;
    while ((m = sectionRe.exec(raw)) !== null) {
      parts.push({ title: m[1], body: (m[2] || "").trim() });
    }
    if (parts.length >= 2) {
      const blocks = parts
        .map(function (p) {
          let kind = "is-evidence";
          let label = p.title;
          if (p.title.indexOf("结论") >= 0) {
            kind = "is-conclusion";
            label = "结论";
          } else if (p.title.indexOf("依据") >= 0) {
            kind = "is-evidence";
            label = "条款依据";
          } else {
            kind = "is-boundary";
            label = "不确定 / 边界";
          }
          return (
            '<section class="answer-section ' +
            kind +
            '"><div class="answer-section-label">' +
            escapeHtml(label) +
            '</div><div class="answer-section-body">' +
            linkCitations(escapeHtml(p.body)) +
            "</div></section>"
          );
        })
        .join("");
      return '<div class="answer-sections">' + blocks + "</div>";
    }

    // Fallback plain formatting
    return linkCitations(
      escapeHtml(raw).replace(
        /^(【[^】]+】|[一二三四五六七八九十]+[、.．]|结论|条款依据|不确定[/／]?边界)([^\n]*)/gm,
        function (_mm, head, rest) {
          return '<span class="sec-head">' + head + (rest || "") + "</span>";
        }
      )
    );
  }

  function citationsHtml(sources, groupId) {
    if (!sources || !sources.length) return "";
    const cards = sources
      .map(function (s, i) {
        const name = displayNameFor(
          s.document_name || s.source || s.filename || "doc",
          s
        );
        const page = s.page_number ?? s.page ?? "—";
        const excerpt = cleanExcerpt(s.content || s.excerpt || s.text || "");
        return (
          '<button type="button" class="cite-card" data-cite-index="' +
          (i + 1) +
          '" data-cite-group="' +
          groupId +
          '">' +
          '<div class="cite-card-top">' +
          '<span class="cite-idx">[' +
          (i + 1) +
          "]</span>" +
          '<span class="cite-doc">' +
          escapeHtml(name) +
          "</span>" +
          '<span class="cite-page">p.' +
          escapeHtml(String(page)) +
          "</span>" +
          "</div>" +
          '<div class="cite-excerpt">' +
          escapeHtml(excerpt) +
          "</div></button>"
        );
      })
      .join("");
    return (
      '<div class="citations" data-cite-group="' +
      groupId +
      '"><div class="citations-title">来源 · ' +
      sources.length +
      " · 点击打开左侧原文</div>" +
      cards +
      "</div>"
    );
  }

  function ensureMessagesVisible() {
    emptyChat.hidden = true;
    emptyChat.setAttribute("aria-hidden", "true");
    messagesEl.hidden = false;
  }

  function appendMessage(role, html, extraClass) {
    ensureMessagesVisible();
    const div = document.createElement("div");
    div.className =
      "message is-" + role + (extraClass ? " " + extraClass : "");
    const icon =
      role === "user"
        ? '<svg class="message-icon" viewBox="0 0 24 24" width="18" height="18" fill="#1D9CFF"><path d="M12 12a5 5 0 1 0-5-5 5 5 0 0 0 5 5zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5z"/></svg>'
        : '<svg class="message-icon" viewBox="0 0 24 24" width="18" height="18" fill="#1D9CFF"><path d="M12 2l1.2 3.6L17 7l-3.8 1.2L12 12l-1.2-3.8L7 7l3.8-1.4L12 2zm6.5 9l.8 2.3 2.2.7-2.2.7-.8 2.3-.8-2.3-2.2-.7 2.2-.7.8-2.3z"/></svg>';
    // Safe: fixed SVG icon + pre-escaped/composed html only.
    div.innerHTML =
      '<div class="message-row">' +
      icon +
      '<div class="message-body">' +
      html +
      "</div></div>";
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function setAssistantBody(row, answerText, sources) {
    const body = row.querySelector(".message-body");
    if (!body) return;
    citeSeq += 1;
    const groupId = "g" + citeSeq;
    row.dataset.citeGroup = groupId;
    row._sources = sources || [];
    row._answerText = answerText || "";
    body.innerHTML =
      formatAnswerHtml(answerText || "") +
      citationsHtml(sources || [], groupId);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    followAnswerCitation(sources || [], answerText || "");
    const idx = firstAnswerCiteIndex(answerText);
    highlightActiveCite(groupId, Math.min(idx, (sources || []).length || 1));
  }

  function highlightActiveCite(groupId, index) {
    document.querySelectorAll(".cite-card.is-active").forEach(function (el) {
      el.classList.remove("is-active");
    });
    if (!groupId || !index) return;
    const card = document.querySelector(
      '.cite-card[data-cite-group="' +
        groupId +
        '"][data-cite-index="' +
        index +
        '"]'
    );
    if (card) card.classList.add("is-active");
  }

  function activateCitation(index, sources, groupId) {
    const list = sources || activeSources || [];
    const i = Number(index) - 1;
    if (i < 0 || i >= list.length) return;
    const s = list[i];
    openCitedPdf(
      s.document_name || s.source || s.filename,
      s.page_number ?? s.page,
      s,
      Number(index),
      {}
    );
    highlightActiveCite(groupId, index);
  }

  function normalizeSources(data) {
    if (!data) return [];
    let list = [];
    if (Array.isArray(data.retrieved_chunks) && data.retrieved_chunks.length) {
      list = data.retrieved_chunks;
    } else if (Array.isArray(data.sources)) {
      list = data.sources;
    } else if (Array.isArray(data.citations)) {
      list = data.citations;
    }
    // UI safety: never show more than 4 even if backend regresses
    return list.slice(0, 4);
  }

  async function askOnce(question) {
    const res = await fetch("/api/v1/queries/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: question,
        stream: false,
        show_sources: true,
      }),
      signal: abortController ? abortController.signal : undefined,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok && !data.answer) {
      throw new Error(data.detail || data.message || "提问失败 " + res.status);
    }
    return data;
  }

  async function askStream(question, onDelta, onFinal) {
    const res = await fetch("/api/v1/queries/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: question,
        stream: true,
        show_sources: true,
      }),
      signal: abortController ? abortController.signal : undefined,
    });
    if (!res.ok) {
      const errData = await res.json().catch(function () {
        return {};
      });
      throw new Error(
        errData.detail || errData.message || "流式失败 " + res.status
      );
    }
    if (!res.body || !res.body.getReader) {
      onFinal(await res.json());
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
        let line = parts[i].trim();
        if (!line) continue;
        if (line.startsWith("data:")) line = line.slice(5).trim();
        if (!line || line === "[DONE]") continue;
        try {
          const obj = JSON.parse(line);
          if (obj.type === "token" || obj.delta || obj.token) {
            full += obj.token || obj.delta || obj.content || "";
            onDelta(full);
          } else if (
            obj.answer ||
            obj.retrieved_chunks ||
            obj.type === "final" ||
            obj.type === "end"
          ) {
            finalPayload = obj.data || obj;
            if (obj.answer) finalPayload = obj;
          }
        } catch (_e) {
          full += line;
          onDelta(full);
        }
      }
    }
    onFinal(finalPayload || { answer: full, retrieved_chunks: [] });
  }

  async function handleAsk(question) {
    const q = String(question || "").trim();
    if (!q || isLoading) return;
    showError("");
    setLoading(true);
    abortController = new AbortController();
    ensureMessagesVisible();
    appendMessage("user", escapeHtml(q));
    const assistantRow = appendMessage("assistant", "…", "is-pending");

    try {
      if (streamToggle && streamToggle.checked) {
        await askStream(
          q,
          function (partial) {
            const body = assistantRow.querySelector(".message-body");
            // During stream: plain text only; open PDF after final with citations
            if (body) body.innerHTML = formatAnswerHtml(partial);
          },
          function (data) {
            setAssistantBody(
              assistantRow,
              data.answer || data.response || "",
              normalizeSources(data)
            );
          }
        );
      } else {
        const data = await askOnce(q);
        setAssistantBody(
          assistantRow,
          data.answer || data.response || "（空响应）",
          normalizeSources(data)
        );
      }
    } catch (err) {
      if (err.name === "AbortError") {
        setAssistantBody(assistantRow, "已停止。", []);
      } else {
        showError(err.message || String(err));
        setAssistantBody(
          assistantRow,
          '<span style="color:#dc2626">' +
            escapeHtml(err.message || String(err)) +
            "</span>",
          []
        );
      }
    } finally {
      setLoading(false);
      abortController = null;
      input.value = "";
      input.focus();
      sendBtn.disabled = true;
    }
  }

  function resetChat() {
    if (abortController) abortController.abort();
    setLoading(false);
    showError("");
    messagesEl.innerHTML = "";
    messagesEl.hidden = true;
    emptyChat.hidden = false;
    emptyChat.removeAttribute("aria-hidden");
    activeSources = [];
    currentView = { name: null, url: null, page: null, index: null };
    pdfFrame.hidden = true;
    pdfFrame.removeAttribute("src");
    pdfEmpty.hidden = false;
    pdfSelect.hidden = true;
    pageBadge.hidden = true;
    pdfTitle.textContent = "引用原文";
    pdfSubtitle.textContent = "提问后自动打开答案引用的条款 PDF";
    setEvidence(null);
    input.value = "";
    sendBtn.disabled = true;
    input.focus();
  }

  messagesEl.addEventListener("click", function (e) {
    const ref = e.target.closest(".cite-ref, .cite-card");
    if (!ref) return;
    e.preventDefault();
    const idx = ref.getAttribute("data-cite-index");
    const groupId =
      ref.getAttribute("data-cite-group") ||
      (ref.closest(".message") && ref.closest(".message").dataset.citeGroup);
    const row = ref.closest(".message");
    const sources = (row && row._sources) || activeSources;
    activateCitation(idx, sources, groupId);
  });

  pdfSelect.addEventListener("change", function () {
    const url = pdfSelect.value;
    const hit = pdfs.find(function (p) {
      return p.url === url;
    });
    if (!hit) return;
    // Manual override: keep page if possible, evidence from active matching source
    const match =
      activeSources.find(function (s) {
        return basename(s.document_name || "").toLowerCase() === basename(hit.name).toLowerCase();
      }) || null;
    openCitedPdf(
      hit.name,
      (match && (match.page_number ?? match.page)) || currentView.page || null,
      match || { document_name: hit.name, content: "" },
      currentView.index || 1,
      {}
    );
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    handleAsk(input.value);
  });

  input.addEventListener("input", function () {
    sendBtn.disabled = isLoading || !String(input.value || "").trim();
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (String(input.value || "").trim()) handleAsk(input.value);
    }
  });

  resetBtn.addEventListener("click", function (e) {
    e.preventDefault();
    resetChat();
  });

  stopBtn.addEventListener("click", function (e) {
    e.preventDefault();
    if (abortController) abortController.abort();
  });

  document.querySelectorAll(".prompt-chip").forEach(function (btn) {
    btn.addEventListener("click", function () {
      handleAsk(btn.getAttribute("data-q") || btn.textContent);
    });
  });

  (function setupResize() {
    let dragging = false;
    resizeHandle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      dragging = true;
      document.body.style.cursor =
        window.innerWidth <= 860 ? "row-resize" : "col-resize";
      document.body.style.userSelect = "none";
    });
    window.addEventListener("mouseup", function () {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    });
    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      const rect = panelGroup.getBoundingClientRect();
      const isVertical = window.innerWidth <= 860;
      if (isVertical) {
        const y = e.clientY - rect.top;
        const ratio = Math.min(0.78, Math.max(0.22, y / rect.height));
        pdfPanel.style.flex = "0 0 " + ratio * 100 + "%";
        aiPanel.style.flex = "0 0 " + (1 - ratio) * 100 + "%";
      } else {
        const x = e.clientX - rect.left;
        const ratio = Math.min(0.72, Math.max(0.28, x / rect.width));
        pdfPanel.style.flex = "0 0 " + ratio * 100 + "%";
        aiPanel.style.flex = "1 1 " + (1 - ratio) * 100 + "%";
      }
    });
  })();

  loadCorpus();
  loadHealth();
  sendBtn.disabled = true;
})();
