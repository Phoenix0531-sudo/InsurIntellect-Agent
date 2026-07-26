/* Citation-first clause RAG UI on chat-pdf dual-pane shell.
 * Product: ask → curated citations → left PDF + evidence strip.
 * P1: stream end-only PDF/citations; refuse card styles.
 * P2: PDF.js highlight, chip docs, chunk debug.
 * P3: multi-turn left-pane stickiness.
 * Untrusted answer/source text always goes through escapeHtml before innerHTML.
 */
(function () {
  const pdfSelect = document.getElementById("pdfSelect");
  const pdfEmpty = document.getElementById("pdfEmpty");
  const pdfFrame = document.getElementById("pdfFrame");
  const pdfJsView = document.getElementById("pdfJsView");
  const pdfCanvas = document.getElementById("pdfCanvas");
  const pdfTextLayer = document.getElementById("pdfTextLayer");
  const pdfHighlightLayer = document.getElementById("pdfHighlightLayer");
  const pdfTitle = document.getElementById("pdfTitle");
  const pdfSubtitle = document.getElementById("pdfSubtitle");
  const pageBadge = document.getElementById("pageBadge");
  const evidenceStrip = document.getElementById("evidenceStrip");
  const evidenceCite = document.getElementById("evidenceCite");
  const evidenceExcerpt = document.getElementById("evidenceExcerpt");
  const corpusMeta = document.getElementById("corpusMeta");
  const embedMeta = document.getElementById("embedMeta");
  const messagesEl = document.getElementById("messages");
  const emptyChat = document.getElementById("emptyChat");
  const form = document.getElementById("askForm");
  const input = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");
  const resetBtn = document.getElementById("resetBtn");
  const stopBtn = document.getElementById("stopBtn");
  const debugToggle = document.getElementById("debugToggle");
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
  let lastStickyView = null;
  const sessionId = (function () {
    try {
      const k = "insur_session_id";
      let v = localStorage.getItem(k);
      if (!v) {
        v = "s_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
        localStorage.setItem(k, v);
      }
      return v;
    } catch (e) {
      return "s_" + String(Date.now());
    }
  })();
 // P3: keep last citation across follow-ups
  let currentView = { name: null, url: null, page: null, index: null, excerpt: "" };
  let isLoading = false;
  let abortController = null;
  let citeSeq = 0;
  let debugMode = false;
  let lastEmbeddingProvider = null;
  let pdfDocCache = { url: null, doc: null, renderToken: 0 };

  const DISPLAY_FALLBACK = {
    "sample_term_life.pdf": "示例终身寿险条款",
    "sample_critical_illness.pdf": "示例重大疾病保险条款",
  };

  // Configure PDF.js worker if available
  try {
    if (window.pdfjsLib) {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc =
        "/static/vendor/pdfjs/pdf.worker.min.js";
    }
  } catch (_e) {}

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
    let t = String(text || "")
      .replace(/\s+/g, " ")
      .trim();
    t = t
      .replace(
        /^(文档名称|产品名称|文档类型|生效日期|状态)[：:][^。；;\n]{0,40}[。；;\s]*/g,
        ""
      )
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

  function hidePdfViews() {
    if (pdfFrame) {
      pdfFrame.hidden = true;
      pdfFrame.removeAttribute("src");
    }
    if (pdfJsView) pdfJsView.hidden = true;
    if (pdfEmpty) pdfEmpty.hidden = false;
  }

  function pickHighlightNeedle(excerpt) {
    const t = String(excerpt || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!t) return "";
    // Prefer a mid-length continuous clause fragment
    const parts = t.split(/[。；;！!？?\n]/).map(function (s) {
      return s.trim();
    });
    let best = "";
    parts.forEach(function (p) {
      if (p.length >= 8 && p.length <= 48 && p.length > best.length) best = p;
    });
    if (best) return best;
    return t.slice(0, Math.min(36, t.length));
  }

  async function renderPdfJs(url, pageNumber, excerpt) {
    if (!window.pdfjsLib || !pdfCanvas || !pdfJsView) {
      return false;
    }
    const page =
      pageNumber != null && pageNumber !== "" && !Number.isNaN(Number(pageNumber))
        ? Math.max(1, Number(pageNumber))
        : 1;
    const token = ++pdfDocCache.renderToken;
    try {
      if (pdfDocCache.url !== url || !pdfDocCache.doc) {
        const loadingTask = window.pdfjsLib.getDocument({ url: url });
        const doc = await loadingTask.promise;
        if (token !== pdfDocCache.renderToken) return false;
        pdfDocCache = { url: url, doc: doc, renderToken: token };
      }
      const doc = pdfDocCache.doc;
      const pdfPage = await doc.getPage(Math.min(page, doc.numPages || page));
      if (token !== pdfDocCache.renderToken) return false;

      const wrap = document.getElementById("pdfViewerWrap");
      const wrapW = (wrap && wrap.clientWidth) || 640;
      const unscaled = pdfPage.getViewport({ scale: 1 });
      const scale = Math.min(2.2, Math.max(1.0, (wrapW - 8) / unscaled.width));
      const viewport = pdfPage.getViewport({ scale: scale });

      const canvas = pdfCanvas;
      const ctx = canvas.getContext("2d");
      const outputScale = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = Math.floor(viewport.width) + "px";
      canvas.style.height = Math.floor(viewport.height) + "px";
      const transform =
        outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null;

      if (pdfTextLayer) {
        pdfTextLayer.innerHTML = "";
        pdfTextLayer.style.width = canvas.style.width;
        pdfTextLayer.style.height = canvas.style.height;
      }
      if (pdfHighlightLayer) {
        pdfHighlightLayer.innerHTML = "";
        pdfHighlightLayer.style.width = canvas.style.width;
        pdfHighlightLayer.style.height = canvas.style.height;
      }

      await pdfPage.render({
        canvasContext: ctx,
        viewport: viewport,
        transform: transform,
      }).promise;
      if (token !== pdfDocCache.renderToken) return false;

      // Text layer for selection + highlight targeting
      const textContent = await pdfPage.getTextContent();
      if (token !== pdfDocCache.renderToken) return false;
      if (pdfTextLayer && window.pdfjsLib.TextLayer) {
        // Prefer modern TextLayer API if present
        try {
          const textLayer = new window.pdfjsLib.TextLayer({
            textContentSource: textContent,
            container: pdfTextLayer,
            viewport: viewport,
          });
          await textLayer.render();
        } catch (_tl) {
          // Fallback: manual span placement
          textContent.items.forEach(function (item) {
            if (!item.str) return;
            const tx = window.pdfjsLib.Util.transform(
              viewport.transform,
              item.transform
            );
            const span = document.createElement("span");
            span.textContent = item.str;
            span.style.left = tx[4] + "px";
            span.style.top = tx[5] - item.height * scale + "px";
            span.style.fontSize = Math.max(6, item.height * scale) + "px";
            span.style.position = "absolute";
            span.style.whiteSpace = "pre";
            span.style.color = "transparent";
            span.style.transformOrigin = "0% 0%";
            pdfTextLayer.appendChild(span);
          });
        }
      } else if (pdfTextLayer) {
        textContent.items.forEach(function (item) {
          if (!item.str) return;
          const tx = window.pdfjsLib.Util.transform(
            viewport.transform,
            item.transform
          );
          const span = document.createElement("span");
          span.textContent = item.str;
          span.style.left = tx[4] + "px";
          span.style.top = tx[5] - (item.height || 10) * scale + "px";
          span.style.fontSize =
            Math.max(6, (item.height || 10) * scale) + "px";
          span.style.position = "absolute";
          span.style.whiteSpace = "pre";
          span.style.color = "transparent";
          pdfTextLayer.appendChild(span);
        });
      }

      // Highlight excerpt spans if found
      const needle = pickHighlightNeedle(excerpt);
      if (needle && pdfTextLayer && pdfHighlightLayer) {
        const spans = Array.from(pdfTextLayer.querySelectorAll("span"));
        const joined = spans
          .map(function (s) {
            return s.textContent || "";
          })
          .join("");
        const idx = joined.indexOf(needle);
        // Also try shorter needle
        let useNeedle = needle;
        let useIdx = idx;
        if (useIdx < 0 && needle.length > 12) {
          useNeedle = needle.slice(0, 12);
          useIdx = joined.indexOf(useNeedle);
        }
        if (useIdx >= 0) {
          let cursor = 0;
          spans.forEach(function (span) {
            const t = span.textContent || "";
            const start = cursor;
            const end = cursor + t.length;
            cursor = end;
            if (end <= useIdx || start >= useIdx + useNeedle.length) return;
            const rect = span.getBoundingClientRect();
            const parent = pdfJsView.getBoundingClientRect();
            const mark = document.createElement("div");
            mark.className = "pdf-highlight-mark";
            mark.style.left = rect.left - parent.left + pdfJsView.scrollLeft + "px";
            mark.style.top = rect.top - parent.top + pdfJsView.scrollTop + "px";
            mark.style.width = Math.max(4, rect.width) + "px";
            mark.style.height = Math.max(10, rect.height) + "px";
            pdfHighlightLayer.appendChild(mark);
            span.classList.add("is-hit");
          });
        } else {
          // Portfolio-honest fallback: soft page banner when text not located
          const banner = document.createElement("div");
          banner.className = "pdf-highlight-fallback";
          banner.textContent = "摘录定位：本页 · 未精确匹配文本层（仍显示页码证据）";
          pdfHighlightLayer.appendChild(banner);
          if (typeof showToast === "function") {
            showToast("无法高亮摘录，已打开原页");
          }
        }
      }

      pdfEmpty.hidden = true;
      pdfFrame.hidden = true;
      pdfJsView.hidden = false;
      return true;
    } catch (err) {
      console.warn("PDF.js render failed, falling back to iframe", err);
      if (typeof showToast === "function") {
        showToast("无法高亮摘录，已打开原页");
      }
      return false;
    }
  }

  async function openCitedPdf(docName, pageNumber, source, index, opts) {
    opts = opts || {};
    const hit = resolvePdfByName(docName);
    if (!hit || !hit.url) {
      if (opts.forceEmpty !== false && !lastStickyView) {
        hidePdfViews();
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
    const excerpt = cleanExcerpt(
      (source && (source.content || source.excerpt || source.text)) || ""
    );

    currentView = {
      name: hit.name,
      url: hit.url,
      page: page,
      index: index || null,
      excerpt: excerpt,
    };
    lastStickyView = Object.assign({}, currentView, {
      source: source || null,
      display: hit.display_name || displayNameFor(hit.name, source || {}),
    });

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

    const ok = await renderPdfJs(hit.url, page || 1, excerpt);
    if (!ok) {
      // iframe fallback
      const hash = page && page > 0 ? "#page=" + page : "";
      const nextSrc = hit.url + hash;
      pdfEmpty.hidden = true;
      if (pdfJsView) pdfJsView.hidden = true;
      pdfFrame.hidden = false;
      if (pdfFrame.getAttribute("src") !== nextSrc) {
        pdfFrame.src = nextSrc;
      }
    }
    return true;
  }

  function firstAnswerCiteIndex(answerText) {
    const m = String(answerText || "").match(/\[(\d+)\]/);
    if (!m) return 1;
    const n = parseInt(m[1], 10);
    return n > 0 ? n : 1;
  }

  function followAnswerCitation(sources, answerText, opts) {
    opts = opts || {};
    activeSources = Array.isArray(sources) ? sources : [];
    if (!activeSources.length) {
      // P3 stickiness: keep last citation unless forced clear
      if (lastStickyView && !opts.forceClear) {
        pdfTitle.textContent = lastStickyView.display || "引用原文";
        pdfSubtitle.textContent = "沿用上一轮引用（本轮无新引用）";
        return;
      }
      pdfTitle.textContent = "引用原文";
      pdfSubtitle.textContent = "本次回答没有可用引用";
      setEvidence(null);
      return;
    }
    let idx = firstAnswerCiteIndex(answerText);
    if (idx > activeSources.length) idx = 1;

    // P3: if same first cite as current, keep view (avoid flicker)
    const src = activeSources[idx - 1];
    const nextName = basename(src.document_name || src.source || src.filename || "");
    const nextPage = src.page_number ?? src.page;
    if (
      lastStickyView &&
      basename(lastStickyView.name || "") === nextName &&
      Number(lastStickyView.page) === Number(nextPage) &&
      !opts.force
    ) {
      setEvidence(src, idx);
      return;
    }
    openCitedPdf(
      src.document_name || src.source || src.filename,
      src.page_number ?? src.page,
      src,
      idx,
      {}
    );
  }

  function setLoading(v, stage) {
    isLoading = v;
    sendBtn.disabled = v || !String(input.value || "").trim();
    if (genPill) {
      genPill.hidden = !v;
      if (v) setStatus(stage || "generate");
    }
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

  function showToast(msg, ms) {
    ms = ms || 3200;
    let el = document.getElementById("uiToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "uiToast";
      el.className = "ui-toast";
      el.hidden = true;
      document.body.appendChild(el);
    }
    if (!msg) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () {
      el.hidden = true;
    }, ms);
  }

  function setStatus(stage) {
    if (!genPill) return;
    const map = {
      retrieve: "检索中",
      generate: "生成中",
      done: "完成",
      idle: "生成中",
    };
    const texts = genPill.querySelectorAll("span");
    if (texts && texts.length) texts[0].textContent = map[stage] || "生成中";
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

    return linkCitations(
      escapeHtml(raw).replace(
        /^(【[^】]+】|[一二三四五六七八九十]+[、.．]|结论|条款依据|不确定[/／]?边界)([^\n]*)/gm,
        function (_mm, head, rest) {
          return '<span class="sec-head">' + head + (rest || "") + "</span>";
        }
      )
    );
  }

  function debugPanelHtml(sources, meta) {
    if (!debugMode) return "";
    meta = meta || {};
    const rows = (sources || [])
      .map(function (s, i) {
        return (
          "<tr><td>" +
          (i + 1) +
          "</td><td>" +
          escapeHtml(String(s.chunk_id != null ? s.chunk_id : "—")) +
          "</td><td>" +
          escapeHtml(
            String(
              s.similarity_score != null
                ? Number(s.similarity_score).toFixed(4)
                : "—"
            )
          ) +
          "</td><td>" +
          escapeHtml(basename(s.document_name || "")) +
          "</td><td>p." +
          escapeHtml(String(s.page_number ?? s.page ?? "—")) +
          "</td></tr>"
        );
      })
      .join("");
    return (
      '<details class="debug-panel"><summary>调试 · chunk_id / 分数' +
      (meta.embedding_provider
        ? " · " + escapeHtml(meta.embedding_provider)
        : lastEmbeddingProvider
          ? " · " + escapeHtml(lastEmbeddingProvider)
          : "") +
      (meta.answer_kind ? " · kind=" + escapeHtml(meta.answer_kind) : "") +
      "</summary><table class=\"debug-table\"><thead><tr><th>#</th><th>chunk_id</th><th>score</th><th>doc</th><th>page</th></tr></thead><tbody>" +
      (rows || "<tr><td colspan=5>无片段</td></tr>") +
      "</tbody></table></details>"
    );
  }

  function citationsHtml(sources, groupId) {
    if (!sources || !sources.length) return "";
    const visible = sources.filter(function (s) {
      if (s == null) return false;
      if (s.similarity_score == null || s.similarity_score === "") return true;
      const n = Number(s.similarity_score);
      return !(Number.isFinite(n) && n <= 0);
    });
    if (!visible.length) return "";
    const cards = visible
      .map(function (s, i) {
        const name = displayNameFor(
          s.document_name || s.source || s.filename || "doc",
          s
        );
        const page = s.page_number ?? s.page ?? "—";
        const excerpt = cleanExcerpt(s.content || s.excerpt || s.text || "");
        let score = "";
        if (s.similarity_score != null && s.similarity_score !== "") {
          const n = Number(s.similarity_score);
          if (Number.isFinite(n) && n > 0) score = n.toFixed(3);
        }
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
          (debugMode && score
            ? '<span class="cite-score">' + escapeHtml(score) + "</span>"
            : "") +
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
      visible.length +
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

  function kindClass(kind) {
    const k = String(kind || "answer").toLowerCase();
    if (k === "refusal" || k === "insufficient_evidence") return "is-refusal";
    if (k === "advice") return "is-advice";
    if (k === "llm_unavailable") return "is-llm-unavailable";
    if (k === "degraded") return "is-degraded";
    return "is-answer";
  }

  function kindBadge(kind) {
    const k = String(kind || "answer").toLowerCase();
    const map = {
      refusal: "拒答 / 无充分依据",
      insufficient_evidence: "拒答 / 无充分依据",
      advice: "边界 / 不构成建议",
      llm_unavailable: "LLM 不可用 · 仅检索",
      degraded: "降级响应",
      answer: "",
    };
    const label = map[k] || "";
    if (!label) return "";
    return (
      '<div class="kind-badge">' + escapeHtml(label) + "</div>"
    );
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

  function setAssistantBody(row, answerText, sources, meta) {
    meta = meta || {};
    const body = row.querySelector(".message-body");
    if (!body) return;
    citeSeq += 1;
    const groupId = "g" + citeSeq;
    row.dataset.citeGroup = groupId;
    row._sources = sources || [];
    row._answerText = answerText || "";
    row._meta = meta;

    const kind = meta.answer_kind || "answer";
    row.classList.remove(
      "is-pending",
      "is-refusal",
      "is-advice",
      "is-llm-unavailable",
      "is-degraded",
      "is-answer"
    );
    row.classList.add(kindClass(kind));

    // During stream we may pass preformatted; for final always rebuild
    body.innerHTML =
      kindBadge(kind) +
      formatAnswerHtml(answerText || "") +
      citationsHtml(sources || [], groupId) +
      debugPanelHtml(sources || [], meta);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    // P1: only open PDF/evidence after final setAssistantBody (never mid-stream)
    if (sources && sources.length) {
      followAnswerCitation(sources, answerText || {}, { force: false });
      const idx = firstAnswerCiteIndex(answerText);
      highlightActiveCite(groupId, Math.min(idx, sources.length || 1));
    } else {
      followAnswerCitation([], answerText || "", { forceClear: false });
    }

    if (meta.embedding_provider) {
      lastEmbeddingProvider = meta.embedding_provider;
      if (embedMeta) {
        embedMeta.textContent = "embed:" + meta.embedding_provider;
      }
    }
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
    if (card) {
      card.classList.add("is-active");
      try {
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (e) {}
    }
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
    return list.slice(0, 4);
  }

  function responseMeta(data) {
    data = data || {};
    return {
      answer_kind: data.answer_kind || "answer",
      embedding_provider: data.embedding_provider || lastEmbeddingProvider,
      confidence_score: data.confidence_score,
    };
  }

  async function askOnce(question) {
    const res = await fetch("/api/v1/queries/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: question,
        stream: false,
        show_sources: true,
        session_id: sessionId,
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
        session_id: sessionId,
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
    // P1: ignore mid-stream context/chunks — only use end/final for citations+PDF
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
          } else if (obj.type === "context") {
            // intentionally ignore mid-stream chunks (prevent left-pane flash)
          } else if (
            obj.type === "end" ||
            obj.type === "final" ||
            obj.answer ||
            (obj.retrieved_chunks && obj.type !== "context")
          ) {
            finalPayload = obj.data || obj;
            if (obj.answer || obj.type === "end") finalPayload = obj;
            if (obj.answer && !full) full = obj.answer;
          }
        } catch (_e) {
          // non-json lines: treat as token only if look like plain text
          if (line[0] !== "{" && line[0] !== "[") {
            full += line;
            onDelta(full);
          }
        }
      }
    }
    if (finalPayload && !finalPayload.answer && full) {
      finalPayload.answer = full;
    }
    onFinal(finalPayload || { answer: full, retrieved_chunks: [] });
  }

  async function handleAsk(question) {
    const q = String(question || "").trim();
    if (!q || isLoading) return;
    showError("");
    setLoading(true, "retrieve");
    abortController = new AbortController();
    ensureMessagesVisible();
    appendMessage("user", escapeHtml(q));
    const assistantRow = appendMessage("assistant", "…", "is-pending");
    setStatus("generate");

    try {
      if (streamToggle && streamToggle.checked) {
        await askStream(
          q,
          function (partial) {
            setStatus("generate");
            const body = assistantRow.querySelector(".message-body");
            // P1: mid-stream tokens only — no citations, no PDF open
            if (body) body.innerHTML = formatAnswerHtml(partial);
          },
          function (data) {
            setAssistantBody(
              assistantRow,
              data.answer || data.response || "",
              normalizeSources(data),
              responseMeta(data)
            );
          }
        );
      } else {
        const data = await askOnce(q);
        setAssistantBody(
          assistantRow,
          data.answer || data.response || "（空响应）",
          normalizeSources(data),
          responseMeta(data)
        );
      }
    } catch (err) {
      if (err.name === "AbortError") {
        setAssistantBody(assistantRow, "已停止。", [], { answer_kind: "degraded" });
      } else {
        showError(err.message || String(err));
        setAssistantBody(
          assistantRow,
          "请求失败：" + (err.message || String(err)),
          [],
          { answer_kind: "degraded" }
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
    lastStickyView = null;
    currentView = { name: null, url: null, page: null, index: null, excerpt: "" };
    hidePdfViews();
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
    const match =
      activeSources.find(function (s) {
        return (
          basename(s.document_name || "").toLowerCase() ===
          basename(hit.name).toLowerCase()
        );
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

  if (debugToggle) {
    debugToggle.addEventListener("click", function (e) {
      e.preventDefault();
      debugMode = !debugMode;
      debugToggle.classList.toggle("is-active", debugMode);
      debugToggle.textContent = debugMode ? "调试开" : "调试";
      // Re-render last assistant bodies if any
      document.querySelectorAll(".message.is-assistant").forEach(function (row) {
        if (row._answerText != null) {
          setAssistantBody(row, row._answerText, row._sources || [], row._meta || {});
        }
      });
    });
  }

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
