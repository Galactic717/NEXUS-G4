import {
  preprocessQuery, extractKeywords, deduplicateSources,
  rerankSources, truncateAnswer, generateMarkdown, generateJSON
} from "./local-processor.js";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let state = {
  settings: { serverUrl: "http://127.0.0.1:8000", apiKey: "dev-secret-key", theme: "dark" },
  messages: [],
  sources: [],
  currentResearchId: null,
  thinking: false,
  depth: 0,
  searchOnly: false,
  fullAnswer: "",
};

function escHtml(str) {
  if (!str) return "";
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function renderMarkdown(md) {
  if (!md) return "";
  let html = escHtml(md);
  html = html.replace(/### (.+)/g, "<h3>$1</h3>");
  html = html.replace(/## (.+)/g, "<h2>$1</h2>");
  html = html.replace(/# (.+)/g, "<h1>$1</h1>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/\[(\d+)\]/g, '<sup class="cite-badge" data-idx="$1">[$1]</sup>');
  html = html.replace(/- (.+)/g, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

async function loadSettings() {
  try {
    state.settings = await window.api.settings.load();
  } catch (e) {
    console.warn("Settings load failed, using defaults");
  }
  if (state.settings.serverUrl) $("#server-url").value = state.settings.serverUrl;
}

async function saveSettings() {
  state.settings.serverUrl = $("#server-url").value.trim();
  try {
    await window.api.settings.save(state.settings);
  } catch (e) {
    console.error("Save settings failed:", e);
  }
}

async function checkServer() {
  try {
    const resp = await fetch(`${state.settings.serverUrl}/`, { signal: AbortSignal.timeout(3000) });
    const online = resp.status === 200;
    $("#server-status").textContent = online ? "ONLINE" : "OFFLINE";
    $("#server-status").className = "status-badge " + (online ? "online" : "offline");
    return online;
  } catch {
    $("#server-status").textContent = "OFFLINE";
    $("#server-status").className = "status-badge offline";
    return false;
  }
}

function addMessage(role, html, rawMd, researchId) {
  const div = document.createElement("div");
  div.className = `message message-${role}`;

  if (role === "user") {
    div.innerHTML = `<div class="msg-content">${escHtml(html)}</div>`;
  } else {
    div.innerHTML = `<div class="msg-content">${html}</div>`;
    if (researchId) {
      const actions = document.createElement("div");
      actions.className = "msg-actions";
      actions.innerHTML = `
        <button class="btn btn-sm btn-copy" data-raw="${escHtml(rawMd || "")}" title="Copy">Copy</button>
        <button class="btn btn-sm btn-export-md" title="Export Markdown">Export MD</button>
      `;
      div.appendChild(actions);
    }
  }

  $("#messages").appendChild(div);
  scrollBottom();
}

function scrollBottom() {
  requestAnimationFrame(() => {
    $("#messages").scrollTop = $("#messages").scrollHeight;
  });
}

function showThinking() {
  state.thinking = true;
  $("#thinking").classList.remove("hidden");
  $("#steps").innerHTML = "";
  $("#thinking .progress-fill").style.width = "0%";
  scrollBottom();
}

function hideThinking() {
  state.thinking = false;
  $("#thinking").classList.add("hidden");
}

function addStep(msg) {
  if (!state.thinking) return;
  const step = document.createElement("div");
  step.className = "step";
  step.textContent = msg;
  $("#steps").appendChild(step);
  scrollBottom();
}

function updateProgress(pct) {
  $("#thinking .progress-fill").style.width = Math.min(pct, 100) + "%";
}

function renderSources(sources) {
  const list = $("#source-list");
  list.innerHTML = "";
  $("#source-count").textContent = sources.length;
  if (!sources.length) {
    list.innerHTML = '<p class="empty">No sources</p>';
    return;
  }
  sources.forEach((s, i) => {
    const card = document.createElement("div");
    card.className = "source-card";
    card.innerHTML = `
      <div class="source-title">${escHtml(s.title || "Untitled")}</div>
      <div class="source-url">${escHtml((s.url || "").slice(0, 80))}</div>
      <div class="source-meta">Relevance: ${s.relevance_score || "N/A"} | Source: ${s.source || "web"}</div>
      ${s.snippet ? `<div class="source-snippet">${escHtml(s.snippet.slice(0, 200))}</div>` : ""}
    `;
    list.appendChild(card);
  });
}

async function loadNews() {
  try {
    const resp = await fetch(`${state.settings.serverUrl}/api/news?limit=10`, {
      headers: { "X-API-KEY": state.settings.apiKey },
      signal: AbortSignal.timeout(8000),
    });
    if (resp.status !== 200) return;
    const news = await resp.json();
    const list = $("#news-list");
    list.innerHTML = "";
    if (!news.length) {
      list.innerHTML = '<p class="empty">No news available</p>';
      return;
    }
    news.forEach((n) => {
      const card = document.createElement("div");
      card.className = "news-card";
      card.innerHTML = `
        <div class="news-title">${escHtml(n.title || "")}</div>
        <div class="news-source">${escHtml(n.source || "")} &middot; ${(n.date_added || "").slice(0, 10)}</div>
        <div class="news-url">${escHtml((n.url || "").slice(0, 80))}</div>
      `;
      list.appendChild(card);
    });
  } catch {
    // silently fail
  }
}

async function loadCacheList() {
  try {
    const entries = await window.api.cache.list();
    const list = $("#cache-list");
    list.innerHTML = "";
    $("#cache-count").textContent = entries.length;
    if (!entries.length) {
      list.innerHTML = '<p class="empty" style="padding:8px;font-size:12px">Empty</p>';
      return;
    }
    entries.slice(0, 30).forEach((e) => {
      const item = document.createElement("div");
      item.className = "cache-item";
      const shortQuery = (e.query || "").slice(0, 35);
      item.innerHTML = `
        <div class="cache-item-query">${escHtml(shortQuery)}</div>
        <div class="cache-item-meta">${new Date(e.cachedAt).toLocaleDateString()}</div>
      `;
      item.addEventListener("click", () => restoreFromCache(e.id));
      list.appendChild(item);
    });
  } catch {
    // silently fail
  }
}

async function restoreFromCache(id) {
  try {
    const entry = await window.api.cache.get(id);
    if (!entry) return;
    state.messages = [];
    state.sources = entry.sources || [];
    state.fullAnswer = entry.answer || "";
    state.currentResearchId = entry.serverId || null;

    $("#messages").innerHTML = "";
    addMessage("user", entry.query || "");
    addMessage("ai", renderMarkdown(state.fullAnswer), state.fullAnswer, entry.serverId);
    renderSources(state.sources);
    $("#chat-title").textContent = (entry.query || "").slice(0, 50);
  } catch (e) {
    console.error("Restore failed:", e);
  }
}

async function handleSearch() {
  const rawInput = $("#input").value.trim();
  if (!rawInput || state.thinking) return;

  $("#input").value = "";
  state.messages = [];
  state.sources = [];
  state.fullAnswer = "";
  state.currentResearchId = null;
  $("#messages").innerHTML = "";
  renderSources([]);
  $("#chat-title").textContent = rawInput.slice(0, 50);

  const processed = preprocessQuery(rawInput);
  const keywords = extractKeywords(processed);
  const searchOnly = $("#search-only").checked;

  addMessage("user", rawInput);
  showThinking();
  addStep(`Preprocessed query: ${processed !== rawInput ? processed : "no changes needed"}`);
  addStep(`Keywords: ${keywords.join(", ")}`);

  if (!await checkServer()) {
    addStep("Server is offline — aborting");
    hideThinking();
    addMessage("ai", '<div class="error-msg">Error: Server is offline. Please start the server and try again.</div>');
    return;
  }

  try {
    const resp = await fetch(`${state.settings.serverUrl}/api/research`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-KEY": state.settings.apiKey,
      },
      body: JSON.stringify({
        query: processed,
        loops: state.depth,
        search_only: searchOnly,
      }),
      signal: AbortSignal.timeout(180000),
    });

    if (resp.status !== 200) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      hideThinking();
      addMessage("ai", `<div class="error-msg">Error ${resp.status}: ${err.detail || "Unknown"}</div>`);
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const event = JSON.parse(line);
          switch (event.type) {
            case "token":
              state.fullAnswer += event.content || "";
              break;
            case "sources":
              state.sources = deduplicateSources(event.sources || []);
              state.sources = rerankSources(state.sources, keywords);
              renderSources(state.sources);
              break;
            case "context":
              const pct = event.remaining_percent || 0;
              updateProgress(100 - pct);
              break;
            case "warning":
              addStep(`Warning: ${event.message}`);
              break;
            case "step":
              addStep(event.message || event.content || "");
              break;
            case "done":
              state.currentResearchId = event.id || null;
              hideThinking();
              addMessage("ai", renderMarkdown(state.fullAnswer), state.fullAnswer, state.currentResearchId);
              addStep("Research complete");

              await window.api.cache.save({
                query: rawInput,
                answer: state.fullAnswer,
                sources: state.sources,
                serverId: state.currentResearchId,
                tags: keywords.slice(0, 5).join(","),
                depth: state.depth,
              });
              addStep("Saved to local cache");
              loadCacheList();

              if (state.fullAnswer) {
                window.api.notify("Research Complete", `Results for: ${rawInput.slice(0, 50)}`);
              }
              break;
            case "error":
              hideThinking();
              addMessage("ai", `<div class="error-msg">Error: ${event.message || "Unknown"}</div>`);
              addStep(`Error: ${event.message}`);
              break;
          }
        } catch (e) {
          // skip unparseable lines
        }
      }
    }

    if (state.thinking) {
      hideThinking();
      addMessage("ai", renderMarkdown(state.fullAnswer) || '<div class="error-msg">No answer received</div>');
      renderSources(state.sources);
    }
  } catch (e) {
    hideThinking();
    addMessage("ai", `<div class="error-msg">Connection error: ${e.message}</div>`);
  }
}

async function handleExportMd() {
  if (!state.fullAnswer) return;
  const md = generateMarkdown(
    $("#chat-title").textContent || "research",
    state.fullAnswer,
    state.sources
  );
  try {
    const result = await window.api.export.saveDialog("report.md");
    if (!result.canceled && result.filePath) {
      await window.api.export.writeFile(result.filePath, md);
    }
  } catch (e) {
    console.error("Export failed:", e);
  }
}

async function handleExportJson() {
  if (!state.fullAnswer) return;
  const json = generateJSON({
    query: $("#chat-title").textContent || "research",
    answer: state.fullAnswer,
    sources: state.sources,
  });
  try {
    const result = await window.api.export.saveDialog("report.json");
    if (!result.canceled && result.filePath) {
      await window.api.export.writeFile(result.filePath, json);
    }
  } catch (e) {
    console.error("Export failed:", e);
  }
}

async function handleSettings() {
  const url = prompt("Server URL:", state.settings.serverUrl);
  if (url && url.trim()) {
    state.settings.serverUrl = url.trim();
    $("#server-url").value = url.trim();
    await saveSettings();
    checkServer();
  }
}

function init() {
  loadSettings().then(() => {
    checkServer();
    loadNews();
    loadCacheList();
    setInterval(checkServer, 15000);
  });

  $("#btn-send").addEventListener("click", handleSearch);
  $("#input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSearch();
    }
  });

  $$("[data-depth]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("[data-depth]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.depth = parseInt(btn.dataset.depth);
    });
  });

  $$(".panel-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$(".panel-tab").forEach((t) => t.classList.remove("active"));
      $$(".tab-content").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      $(`#tab-${tab.dataset.tab}`).classList.add("active");
      if (tab.dataset.tab === "news") loadNews();
    });
  });

  $("#btn-refresh-news").addEventListener("click", loadNews);
  $("#btn-cache-clear").addEventListener("click", async () => {
    if (confirm("Clear entire local cache?")) {
      await window.api.cache.clear();
      loadCacheList();
    }
  });
  $("#btn-settings").addEventListener("click", handleSettings);

  $("#messages").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.classList.contains("btn-copy")) {
      const raw = btn.dataset.raw || "";
      try {
        await navigator.clipboard.writeText(raw);
        btn.textContent = "Copied!";
        setTimeout(() => { btn.textContent = "Copy"; }, 2000);
      } catch {
        // fallback
      }
    }
    if (btn.classList.contains("btn-export-md")) {
      await handleExportMd();
    }
  });

  window.api.onMenuExport(() => handleExportMd());
  window.api.onMenuSettings(() => handleSettings());

  $("#server-url").addEventListener("change", async () => {
    await saveSettings();
    checkServer();
  });

  setInterval(loadCacheList, 10000);
}

document.addEventListener("DOMContentLoaded", init);
