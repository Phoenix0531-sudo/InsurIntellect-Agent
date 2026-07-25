/* InsurIntellect clause RAG UI — single main JS path */
(function () {
  const chat = document.getElementById("chatMessages");
  const welcome = document.getElementById("welcome");
  const form = document.getElementById("askForm");
  const input = document.getElementById("messageInput");
  const sendButton = document.getElementById("sendButton");
  const streamToggle = document.getElementById("streamToggle");
  const docList = document.getElementById("docList");
  const corpusMeta = document.getElementById("corpusMeta");
  const healthPill = document.getElementById("healthPill");

  let busy = false;
  let abortController = null;

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

  function hideWelcome() {
    if (welcome) welcome.style.display = "none";
  }

  function addMessage(role, content, sources) {
    hideWelcome();
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    const roleLabel = role === "user" ? "问题" : "回答";
    el.innerHTML = `
      <div class="role">${roleLabel}</div>
      <div class="body">${escapeHtml(content || "")}</div>
      ${role === "assistant" ? createSourcesSection(sources) : ""}
    `;
    chat.appendChild(el);
    chat.scrollTop = chat.scrollHeight;
    return el;
  }

  function createSourcesSection(sources) {
    if (!sources || !sources.length) {
      return `<div class="sources"><div class="sources-title">引用</div><div class="muted small">本次无可用引用片段</div></div>`;
    }
    const cards = sources.map((s, i) => {
      const name = s.document_name || s.source || s.filename || "未知文档";
      const page = s.page_number ?? s.page ?? "—";
      const excerpt = (s.content || s.excerpt || s.text || "").slice(0, 280);
      const score = s.similarity_score;
      const scoreText =
        typeof score === "number" && !Number.isNaN(score)
          ? ` · score ${score.toFixed(3)}`
          : "";
      return `
        <div class="source-card">
          <div class="head">
            <span class="idx">[${i + 1}]</span>
            <span class="doc">${escapeHtml(name)}</span>
            <span class="page">p.${escapeHtml(page)}${scoreText}</span>
          </div>
          <div class="excerpt">${escapeHtml(excerpt)}</div>
        </div>`;
    });
    return `
      <div class="sources">
        <div class="sources-title">引用（retrieved_chunks）</div>
        ${cards.join("")}
      </div>`;
  }

  function normalizeSources(data) {
    if (!data) return [];
    if (Array.isArray(data.retrieved_chunks)) return data.retrieved_chunks;
    if (Array.isArray(data.sources)) return data.sources;
    return [];
  }

  async function loadCorpus() {
    try {
      const res = await fetch("/api/v1/corpus");
      if (!res.ok) throw new Error("corpus " + res.status);
      const data = await res.json();
      const docs = data.documents || [];
      if (!docs.length) {
        docList.innerHTML = `<li class="muted">暂无文档。请运行 scripts/generate_sample_corpus.py 与 simple_ingest.py</li>`;
      } else {
        docList.innerHTML = docs
          .map(
            (d) => `<li>
              <div class="name">${escapeHtml(d.name || d.filename || "document")}</div>
              <div class="meta">${escapeHtml(
                d.pages != null ? d.pages + " pages" : d.path || ""
              )}</div>
            </li>`
          )
          .join("");
      }
      corpusMeta.textContent = data.chunk_count
        ? `${docs.length} docs · ${data.chunk_count} chunks`
        : `${docs.length} docs`;
    } catch (e) {
      docList.innerHTML = `<li class="muted">无法加载 corpus（${escapeHtml(
        e.message || e
      )}）</li>`;
    }
  }

  async function loadHealth() {
    try {
      const res = await fetch("/api/v1/health/");
      const data = await res.json();
      const ok = data.status === "healthy";
      healthPill.textContent = ok ? "healthy" : data.status || "degraded";
      healthPill.className = "pill " + (ok ? "ok" : "bad");
    } catch (e) {
      healthPill.textContent = "offline";
      healthPill.className = "pill bad";
    }
  }

  async function ask(question) {
    const q = (question || "").trim();
    if (!q || busy) return;
    addMessage("user", q);
    input.value = "";
    setBusy(true);

    const useStream = !!(streamToggle && streamToggle.checked);
    try {
      if (useStream) {
        await askStream(q);
      } else {
        await askOnce(q);
      }
    } catch (e) {
      addMessage("assistant", `请求失败：${e.message || e}`, []);
    } finally {
      setBusy(false);
    }
  }

  async function askOnce(question) {
    const res = await fetch("/api/v1/queries/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        stream: false,
        show_sources: true,
        query_type: "general",
      }),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`${res.status} ${t.slice(0, 200)}`);
    }
    const data = await res.json();
    addMessage("assistant", data.answer || "(空回答)", normalizeSources(data));
  }

  async function askStream(question) {
    abortController = new AbortController();
    const res = await fetch("/api/v1/queries/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        stream: true,
        show_sources: true,
        query_type: "general",
      }),
      signal: abortController.signal,
    });
    if (!res.ok || !res.body) {
      // fallback non-stream
      return askOnce(question);
    }

    const assistantEl = addMessage("assistant", "", []);
    const bodyEl = assistantEl.querySelector(".body");
    let buffer = "";
    let sources = [];
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    let eventType = "message";
    let dataLines = [];

    const flushEvent = () => {
      const raw = dataLines.join("\n");
      dataLines = [];
      if (!raw) return;
      try {
        const payload = JSON.parse(raw);
        if (payload.type === "token" || payload.text) {
          buffer += payload.text || payload.token || "";
          bodyEl.textContent = buffer;
        }
        if (payload.type === "context" || payload.retrieved_chunks) {
          sources = normalizeSources(payload);
        }
        if (payload.type === "final" || payload.answer) {
          if (payload.answer) {
            buffer = payload.answer;
            bodyEl.textContent = buffer;
          }
          sources = normalizeSources(payload).length
            ? normalizeSources(payload)
            : sources;
        }
      } catch (_) {
        // plain text token
        buffer += raw;
        bodyEl.textContent = buffer;
      }
      chat.scrollTop = chat.scrollHeight;
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const lines = pending.split(/\r?\n/);
      pending = lines.pop();
      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        } else if (line === "") {
          flushEvent();
          eventType = "message";
        }
      }
    }
    if (dataLines.length) flushEvent();

    // replace sources section
    const oldSources = assistantEl.querySelector(".sources");
    if (oldSources) oldSources.remove();
    assistantEl.insertAdjacentHTML("beforeend", createSourcesSection(sources));
    if (!buffer) bodyEl.textContent = "(流式无内容，可关闭流式重试)";
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    ask(input.value);
  });

  document.querySelectorAll(".example-btn").forEach((btn) => {
    btn.addEventListener("click", () => ask(btn.dataset.q || btn.textContent));
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(input.value);
    }
  });

  loadCorpus();
  loadHealth();
})();
