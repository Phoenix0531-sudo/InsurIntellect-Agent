/* Chat shell behavior adapted from trangiabach/chat-pdf components:
 * ChatPanel / ChatPdfPicker / ChatPdfViewer / ChatAIWindow / ChatAIInput / ChatMessages
 * Data: our /api/v1/corpus + POST /api/v1/queries/ask (not their Next API routes).
 * HTML injection uses escapeHtml for untrusted answer/source text.
 */
(function () {
  const pdfSelect = document.getElementById("pdfSelect");
  const pdfEmpty = document.getElementById("pdfEmpty");
  const pdfFrame = document.getElementById("pdfFrame");
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
  let selectedPdf = null;
  let isLoading = false;
  let abortController = null;

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setLoading(v) {
    isLoading = v;
    sendBtn.disabled = v || !String(input.value || "").trim();
    if (genPill) genPill.hidden = !v;
    if (stopBtn) stopBtn.hidden = !v;
    const lastIcon = messagesEl.querySelector(".message.is-assistant:last-child .message-icon");
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
    errPill.textContent = "Error: " + msg;
  }

  function selectPdf(url) {
    selectedPdf = pdfs.find(function (p) {
      return p.url === url;
    }) || null;
    if (selectedPdf && selectedPdf.url) {
      pdfEmpty.hidden = true;
      pdfFrame.hidden = false;
      pdfFrame.src = selectedPdf.url;
      pdfSelect.value = selectedPdf.url;
    } else {
      pdfFrame.hidden = true;
      pdfFrame.removeAttribute("src");
      pdfEmpty.hidden = false;
      pdfSelect.value = "";
    }
  }

  async function loadCorpus() {
    try {
      const res = await fetch("/api/v1/corpus");
      if (!res.ok) throw new Error("corpus " + res.status);
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
            chunk_count: d.chunk_count ?? d.chunks,
          };
        })
        .filter(function (p) {
          return !!p.url;
        });

      pdfSelect.innerHTML =
        '<option value="">Pick a PDF file...</option>' +
        pdfs
          .map(function (p) {
            return (
              '<option value="' +
              escapeHtml(p.url) +
              '">' +
              escapeHtml(p.name) +
              "</option>"
            );
          })
          .join("");

      const chunks = data.chunk_count != null ? data.chunk_count : "—";
      corpusMeta.textContent = pdfs.length + " PDFs · " + chunks + " chunks";

      if (pdfs.length) {
        selectPdf(pdfs[0].url);
      }
    } catch (err) {
      corpusMeta.textContent = "corpus error";
      showError(err.message || String(err));
    }
  }

  async function loadHealth() {
    try {
      const res = await fetch("/api/v1/health/");
      if (!res.ok) throw new Error("health " + res.status);
      const data = await res.json();
      const status = (data.status || "ok").toLowerCase();
      healthText.textContent = status;
    } catch (_e) {
      healthText.textContent = "offline";
    }
  }

  function formatAnswerHtml(text) {
    const escaped = escapeHtml(text);
    return escaped
      .replace(
        /^(【[^】]+】|[一二三四五六七八九十]+[、.．]|结论|条款依据|不确定[/／]?边界)([^\n]*)/gm,
        function (_m, head, rest) {
          return '<span class="sec-head">' + head + (rest || "") + "</span>";
        }
      )
      .replace(/\[(\d+)\]/g, '<a class="cite-ref" href="#cite-$1">[$1]</a>');
  }

  function citationsHtml(sources) {
    if (!sources || !sources.length) return "";
    const cards = sources
      .map(function (s, i) {
        const name = s.document_name || s.source || s.filename || "doc";
        const page = s.page_number ?? s.page ?? "—";
        const excerpt = String(s.content || s.excerpt || s.text || "").slice(0, 220);
        return (
          '<div class="cite-card" id="cite-' +
          (i + 1) +
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
          "</div></div>"
        );
      })
      .join("");
    return (
      '<div class="citations"><div class="citations-title">Sources · ' +
      sources.length +
      "</div>" +
      cards +
      "</div>"
    );
  }

  function ensureMessagesVisible() {
    emptyChat.hidden = true;
    messagesEl.hidden = false;
  }

  function appendMessage(role, html, extraClass) {
    ensureMessagesVisible();
    const div = document.createElement("div");
    div.className =
      "message is-" + role + (extraClass ? " " + extraClass : "");
    const icon =
      role === "user"
        ? '<svg class="message-icon" viewBox="0 0 24 24" width="20" height="20" fill="#1D9CFF"><path d="M12 12a5 5 0 1 0-5-5 5 5 0 0 0 5 5zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5z"/></svg>'
        : '<svg class="message-icon" viewBox="0 0 24 24" width="20" height="20" fill="#1D9CFF"><path d="M12 2l1.2 3.6L17 7l-3.8 1.2L12 12l-1.2-3.8L7 7l3.8-1.4L12 2zm6.5 9l.8 2.3 2.2.7-2.2.7-.8 2.3-.8-2.3-2.2-.7 2.2-.7.8-2.3z"/></svg>';
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

  function setAssistantBody(row, answerHtml, sources) {
    const body = row.querySelector(".message-body");
    if (!body) return;
    body.innerHTML = answerHtml + citationsHtml(sources || []);
    messagesEl.scrollTop = messagesEl.scrollHeight;
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
      throw new Error(data.detail || data.message || "ask failed " + res.status);
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
        errData.detail || errData.message || "stream failed " + res.status
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
          } else if (obj.answer || obj.retrieved_chunks || obj.type === "final") {
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
    if (!selectedPdf) {
      showError("Pick a PDF!");
      return;
    }
    showError("");
    setLoading(true);
    abortController = new AbortController();
    appendMessage("user", escapeHtml(q));
    const assistantRow = appendMessage("assistant", "…", "is-pending");

    try {
      if (streamToggle && streamToggle.checked) {
        await askStream(
          q,
          function (partial) {
            setAssistantBody(assistantRow, formatAnswerHtml(partial), []);
          },
          function (data) {
            setAssistantBody(
              assistantRow,
              formatAnswerHtml(data.answer || data.response || ""),
              normalizeSources(data)
            );
          }
        );
      } else {
        const data = await askOnce(q);
        setAssistantBody(
          assistantRow,
          formatAnswerHtml(data.answer || data.response || "(empty)"),
          normalizeSources(data)
        );
      }
    } catch (err) {
      if (err.name === "AbortError") {
        setAssistantBody(assistantRow, "Stopped.", []);
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
    input.value = "";
    sendBtn.disabled = true;
    input.focus();
  }

  // events
  pdfSelect.addEventListener("change", function () {
    selectPdf(pdfSelect.value);
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

  // Resizable handle (react-resizable-panels simplified port)
  (function setupResize() {
    let dragging = false;
    resizeHandle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      dragging = true;
      document.body.style.cursor = "col-resize";
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
      const isVertical = window.innerWidth <= 725;
      if (isVertical) {
        const y = e.clientY - rect.top;
        const ratio = Math.min(0.8, Math.max(0.2, y / rect.height));
        pdfPanel.style.flex = "0 0 " + ratio * 100 + "%";
        aiPanel.style.flex = "0 0 " + (1 - ratio) * 100 + "%";
      } else {
        const x = e.clientX - rect.left;
        const ratio = Math.min(0.8, Math.max(0.2, x / rect.width));
        pdfPanel.style.flex = "0 0 " + ratio * 100 + "%";
        aiPanel.style.flex = "1 1 " + (1 - ratio) * 100 + "%";
      }
    });
  })();

  loadCorpus();
  loadHealth();
  sendBtn.disabled = true;
})();
