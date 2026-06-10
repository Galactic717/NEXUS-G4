document.addEventListener('DOMContentLoaded', () => {

  /* ═══ SIGNAL SYSTEM ═══ */
  function createSignal(initialValue) {
    let value = initialValue;
    const subs = new Set();
    return [
      () => value,
      (newValue) => {
        if (value !== newValue) {
          value = typeof newValue === 'function' ? newValue(value) : newValue;
          subs.forEach(fn => fn());
        }
      },
      (fn) => { subs.add(fn); return () => subs.delete(fn); }
    ];
  }

  function batch(fn) { fn(); }

  /* ═══ DOM HELPERS ═══ */
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'className') { node.className = v; }
      else if (k === 'dataset') { Object.assign(node.dataset, v); }
      else if (k.startsWith('on')) { node.addEventListener(k.slice(2).toLowerCase(), v); }
      else if (k === 'style' && typeof v === 'object') { Object.assign(node.style, v); }
      else if (k === 'html') { node.innerHTML = v; }
      else { node.setAttribute(k, v); }
    }
    for (const child of children) {
      if (child == null) continue;
      node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
  }

  function escHtml(str) {
    if (!str) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return str.replace(/[&<>"']/g, ch => map[ch]);
  }

  /* ═══ STATE ═══ */
  const [getDepth, setDepth] = createSignal(0);
  const [getSearchOnly, setSearchOnly] = createSignal(false);
  const [getIsThinking, setIsThinking] = createSignal(false);
  const [getHistoryId, setHistoryId] = createSignal(null);
  const [getOllamaOnline, setOllamaOnline] = createSignal(true);
  const [getTheme, setTheme] = createSignal(localStorage.getItem('selectedTheme') || 'amethyst');
  const [getSerifMode, setSerifMode] = createSignal(localStorage.getItem('serifMode') === 'true');
  const [getCurrentMode, setCurrentMode] = createSignal('general');
  let globalApiKey = '';

  async function fetchWithAuth(url, options = {}) {
    options.headers = {
      ...options.headers,
      'X-API-KEY': globalApiKey
    };
    return fetch(url, options);
  }

  /* ═══ DOM REFS ═══ */
  const refs = {};
  const _ = (id) => { refs[id] = refs[id] || document.getElementById(id); return refs[id]; };

  /* ═══ THEME MANAGER ═══ */
  const THEMES = {
    amethyst: {
      '--accent-primary': '#a855f7', '--accent-secondary': '#3b82f6',
      '--gradient-primary': 'linear-gradient(135deg,#a855f7,#3b82f6)',
      '--glow-primary': '0 0 15px rgba(168,85,247,0.2)', '--glow-secondary': '0 0 15px rgba(59,130,246,0.2)',
      '--border-focus': 'rgba(168,85,247,0.6)',
      '--bg-base': '#07050d', '--bg-sidebar': '#0c0a17', '--bg-panel': '#0f0c1c',
      '--bg-card': '#19152e', '--bg-elevated': '#1f1a38', '--bg-input': '#141026',
      '--border-subtle': 'rgba(168,85,247,0.08)', '--border-hover': 'rgba(168,85,247,0.2)',
      '--text-primary': '#f8fafc', '--text-secondary': '#94a3b8', '--text-muted': '#64748b'
    },
    emerald: {
      '--accent-primary': '#10b981', '--accent-secondary': '#06b6d4',
      '--gradient-primary': 'linear-gradient(135deg,#10b981,#06b6d4)',
      '--glow-primary': '0 0 15px rgba(16,185,129,0.2)', '--glow-secondary': '0 0 15px rgba(6,182,212,0.2)',
      '--border-focus': 'rgba(16,185,129,0.6)',
      '--bg-base': '#030705', '--bg-sidebar': '#060e0a', '--bg-panel': '#09140f',
      '--bg-card': '#10241b', '--bg-elevated': '#163327', '--bg-input': '#0c1b14',
      '--border-subtle': 'rgba(16,185,129,0.08)', '--border-hover': 'rgba(16,185,129,0.2)',
      '--text-primary': '#f8fafc', '--text-secondary': '#94a3b8', '--text-muted': '#64748b'
    },
    nebula: {
      '--accent-primary': '#2563eb', '--accent-secondary': '#8b5cf6',
      '--gradient-primary': 'linear-gradient(135deg,#2563eb,#8b5cf6)',
      '--glow-primary': '0 0 15px rgba(37,99,235,0.2)', '--glow-secondary': '0 0 15px rgba(139,92,246,0.2)',
      '--border-focus': 'rgba(37,99,235,0.6)',
      '--bg-base': '#03050a', '--bg-sidebar': '#070b16', '--bg-panel': '#090e1c',
      '--bg-card': '#111930', '--bg-elevated': '#172244', '--bg-input': '#0d1326',
      '--border-subtle': 'rgba(37,99,235,0.08)', '--border-hover': 'rgba(37,99,235,0.2)',
      '--text-primary': '#f8fafc', '--text-secondary': '#94a3b8', '--text-muted': '#64748b'
    },
    sunset: {
      '--accent-primary': '#fb7185', '--accent-secondary': '#f59e0b',
      '--gradient-primary': 'linear-gradient(135deg,#fb7185,#f59e0b)',
      '--glow-primary': '0 0 15px rgba(251,113,133,0.2)', '--glow-secondary': '0 0 15px rgba(245,158,11,0.2)',
      '--border-focus': 'rgba(251,113,133,0.6)',
      '--bg-base': '#080405', '--bg-sidebar': '#11080a', '--bg-panel': '#160a0d',
      '--bg-card': '#271116', '--bg-elevated': '#33151c', '--bg-input': '#1e0d11',
      '--border-subtle': 'rgba(251,113,133,0.08)', '--border-hover': 'rgba(251,113,133,0.2)',
      '--text-primary': '#f8fafc', '--text-secondary': '#94a3b8', '--text-muted': '#64748b'
    },
    'google-dark': {
      '--accent-primary': '#a8c7fa', '--accent-secondary': '#8ab4f8',
      '--gradient-primary': 'linear-gradient(135deg,#a8c7fa,#8ab4f8)',
      '--glow-primary': '0 0 15px rgba(168,199,250,0.15)', '--glow-secondary': '0 0 15px rgba(138,180,248,0.15)',
      '--border-focus': 'rgba(168,199,250,0.5)',
      '--bg-base': '#131314', '--bg-sidebar': '#1e1f20', '--bg-panel': '#1e1f20',
      '--bg-card': '#2a2b2e', '--bg-elevated': '#343538', '--bg-input': '#1e1f20',
      '--border-subtle': 'rgba(232,234,237,0.1)', '--border-hover': 'rgba(232,234,237,0.2)',
      '--text-primary': '#e8eaed', '--text-secondary': '#9aa0a6', '--text-muted': '#5f6368'
    }
  };

  function applyTheme(name) {
    const vars = THEMES[name];
    if (!vars) return;
    const root = document.documentElement;
    root.setAttribute('data-theme', name);
    for (const [key, val] of Object.entries(vars)) {
      root.style.setProperty(key, val);
    }
    $$('.theme-chip').forEach(chip => {
      chip.classList.toggle('active', chip.dataset.theme === name);
      chip.setAttribute('aria-checked', chip.dataset.theme === name);
    });
    localStorage.setItem('selectedTheme', name);
  }

  /* ═══ RESIZER LOGIC ═══ */
  function initResizer(resizerId, targetSelector, getSize, setSize, minSize, maxSize, storageKey) {
    const resizer = _(resizerId);
    const target = $(targetSelector);
    if (!resizer || !target) return;

    function onStart(e) {
      e.preventDefault();
      resizer.classList.add('dragging');
      resizer.focus();
      const startX = e.clientX;
      const startSize = parseInt(target.style.width) || getSize();

      function onMove(me) {
        const delta = me.clientX - startX;
        const isLeft = resizerId === 'left-resizer';
        let newSize = isLeft ? startSize + delta : startSize - delta;
        newSize = Math.max(minSize, Math.min(maxSize, Math.round(newSize)));
        target.style.width = newSize + 'px';
        localStorage.setItem(storageKey, newSize);
      }

      function onEnd() {
        resizer.classList.remove('dragging');
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onEnd);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }

      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('pointermove', onMove, { passive: true });
      document.addEventListener('pointerup', onEnd);
    }

    resizer.addEventListener('pointerdown', onStart);

    resizer.addEventListener('keydown', (e) => {
      const step = e.shiftKey ? 20 : 5;
      const isLeft = resizerId === 'left-resizer';
      let w = parseInt(target.style.width) || getSize();
      if (e.key === 'ArrowLeft') {
        w = isLeft ? w - step : w + step;
      } else if (e.key === 'ArrowRight') {
        w = isLeft ? w + step : w - step;
      } else { return; }
      e.preventDefault();
      w = Math.max(minSize, Math.min(maxSize, w));
      target.style.width = w + 'px';
      localStorage.setItem(storageKey, w);
    });

    const saved = localStorage.getItem(storageKey);
    if (saved && window.innerWidth > (storageKey === 'sidebarWidth' ? 768 : 1100)) {
      target.style.width = Math.max(minSize, Math.min(maxSize, parseInt(saved))) + 'px';
    }
  }

  /* ═══ TAB MANAGER ═══ */
  function switchTab(targetId) {
    $$('.panel-tab').forEach(tab => {
      const isActive = tab.dataset.target === targetId;
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', isActive);
    });
    $$('.panel-content').forEach(content => {
      content.classList.toggle('hidden', content.id !== targetId);
    });
    if (targetId === 'tab-news') loadNewsFeed();
  }

  /* ═══ INPUT MANAGER ═══ */
  const promptInput = _('prompt-input');
  const sendBtn = _('send-btn');

  function updateSendBtn() {
    sendBtn.disabled = !promptInput.value.trim() || getIsThinking();
  }

  function autoResize() {
    promptInput.style.height = 'auto';
    promptInput.style.height = Math.min(promptInput.scrollHeight, 120) + 'px';
    updateSendBtn();
  }

  /* ═══ SCROLL MANAGER ═══ */
  let _scrollRaf = 0;

  function scrollToBottom() {
    if (_scrollRaf) return;
    _scrollRaf = requestAnimationFrame(() => {
      _scrollRaf = 0;
      const cm = _('chat-messages');
      if (cm) cm.scrollTop = cm.scrollHeight;
    });
  }

  /* ═══ MARKDOWN PARSER ═══ */
  function parseMarkdown(md) {
    if (!md) return '';
    let html = escHtml(md);
    html = html.replace(/^\s*###\s+(.*?)$/gm, '<h3>$1</h3>');
    html = html.replace(/^\s*##\s+(.*?)$/gm, '<h2>$1</h2>');
    html = html.replace(/^\s*#\s+(.*?)$/gm, '<h2>$1</h2>');
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    html = html.replace(/^\s*[-*]\s+(.*?)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*?<\/li>)+/gs, '<ul>$&</ul>');
    html = html.replace(/\[(S\d+)\]/g, '<sup class="cite-badge" data-target="$1" role="button" tabindex="0">$1</sup>');
    html = html.replace(/\[(.*?)\]\((.*?)\)/gim, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    html = html.replace(/\n\n/g, '</p><p>');
    return `<p>${html}</p>`.replace(/<p>\s*<\/p>/g, '');
  }

  /* ═══ LUCIDE ICONS ═══ */
  function refreshIcons() {
    if (window.lucide) {
      try { lucide.createIcons(); } catch (_) { }
    }
  }

  /* ═══ CHAT RENDERER ═══ */
  function appendUserMessage(text) {
    const msg = el('div', { className: 'message user-message' }, text);
    _('chat-messages').appendChild(msg);
    scrollToBottom();
  }

  function appendAIMessage(html, researchId = null, rawMd = '', showActions = true) {
    const msg = el('div', { className: 'message ai-message', html });
    _('chat-messages').appendChild(msg);
    refreshIcons();
    if (showActions && researchId) {
      postProcessResponse(msg, researchId, rawMd);
    } else {
      scrollToBottom();
    }
  }

  /* ═══ THINKING INDICATOR ═══ */
  function showThinking() {
    setIsThinking(true);
    const inputContainer = _('input-container');
    if (inputContainer) inputContainer.classList.add('glow-thinking');

    const stepsHtml = [
      '<li class="step-item active" id="initial-step">',
      '<span class="step-dot"></span>',
      '<span class="step-label">Аналіз запиту ШІ-агентом</span>',
      '</li>'
    ].join('');

    const box = el('div', { className: 'thinking-box', id: 'thinking-indicator', html: [
      '<div class="thinking-spinner"></div>',
      '<div class="thinking-text">',
      '<h4 id="thinking-title">Ініціалізація дослідження...</h4>',
      '<p id="thinking-desc">Аналіз запиту та підготовка пошуку</p>',
      '<div class="thinking-progress"><div class="thinking-progress-fill" id="thinking-progress-fill" style="width:10%"></div></div>',
      '<div class="steps-accordion open" id="steps-accordion">',
      '<div class="steps-accordion-header" id="steps-accordion-header">',
      '<span>Хронологія дій пошуку</span>',
      '<i data-lucide="chevron-down"></i>',
      '</div>',
      '<div class="steps-accordion-body"><ul class="steps-list" id="steps-list">',
      stepsHtml,
      '</ul></div></div></div>'
    ].join('') });

    _('chat-messages').appendChild(box);
    scrollToBottom();
    refreshIcons();

    requestAnimationFrame(() => {
      const header = _('steps-accordion-header');
      const accordion = _('steps-accordion');
      if (header && accordion) {
        header.addEventListener('click', () => accordion.classList.toggle('open'));
      }
    });

    let progress = 10;
    window.__thinkingProgress = { value: 10, done: false };
    window.__thinkingInterval = setInterval(() => {
      if (window.__thinkingProgress.done) {
        progress = 100;
      } else if (progress >= 95) {
        return;
      } else {
        progress += Math.floor(Math.random() * 4) + 1;
      }
      const fill = _('thinking-progress-fill');
      const title = _('thinking-title');
      const desc = _('thinking-desc');
      if (fill) fill.style.width = Math.min(progress, 100) + '%';
      if (window.__thinkingProgress.done && title && desc) {
        title.textContent = 'Завершено';
        desc.textContent = 'Відповідь згенеровано';
        if (progress >= 100 && window.__thinkingTimeout) {
          clearTimeout(window.__thinkingTimeout);
          window.__thinkingTimeout = null;
        }
      } else if (progress > 30 && progress < 60 && title && desc) {
        title.textContent = 'Пошук в Інтернеті...';
        desc.textContent = 'Сканування надійних джерел...';
      } else if (progress >= 60 && title && desc) {
        title.textContent = 'Генерація відповіді...';
        desc.textContent = 'Синтез знайденого вмісту...';
      }
    }, 800);
  }

  function hideThinking(instant) {
    setIsThinking(false);
    const ic = _('input-container');
    if (ic) ic.classList.remove('glow-thinking');
    if (instant) {
      if (window.__thinkingInterval) {
        clearInterval(window.__thinkingInterval);
        window.__thinkingInterval = null;
      }
      const el = _('thinking-indicator');
      if (el) el.remove();
      updateSendBtn();
      return;
    }
    window.__thinkingProgress.done = true;
    window.__thinkingTimeout = setTimeout(() => {
      if (window.__thinkingInterval) {
        clearInterval(window.__thinkingInterval);
        window.__thinkingInterval = null;
      }
      const el = _('thinking-indicator');
      if (el) el.remove();
      updateSendBtn();
    }, 1200);
  }

  window.addSearchStep = function (message) {
    const stepsList = _('steps-list');
    if (!stepsList) return;
    stepsList.querySelectorAll('.step-item.active').forEach(item => {
      item.classList.remove('active');
      item.classList.add('done');
    });
    const li = document.createElement('li');
    li.className = 'step-item active';
    li.innerHTML = `<span class="step-dot"></span><span class="step-label">${escHtml(message)}</span>`;
    stepsList.appendChild(li);
    const body = stepsList.parentElement;
    if (body) body.scrollTop = body.scrollHeight;
  };

  /* ═══ ACTION BAR & POST PROCESSING ═══ */
  function postProcessResponse(responseDiv, researchId, rawMarkdown) {
    responseDiv.querySelectorAll('.cite-badge').forEach(badge => {
      badge.addEventListener('click', function () {
        const targetId = this.dataset.target;
        const card = _('card-' + targetId);
        if (card) {
          requestAnimationFrame(() => {
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            card.classList.add('highlight');
            setTimeout(() => card.classList.remove('highlight'), 2500);
          });
        }
      });
    });

    if (!researchId) { scrollToBottom(); return; }

    const actionBar = el('div', { className: 'message-actions', html: [
      '<button class="action-btn btn-copy" title="Копіювати текст"><i data-lucide="copy"></i> <span>Копіювати</span></button>',
      '<button class="action-btn btn-pdf" title="Завантажити PDF звіт"><i data-lucide="file-text"></i> <span>PDF Звіт</span></button>',
      '<button class="action-btn btn-html" title="Завантажити HTML сторінку"><i data-lucide="globe"></i> <span>HTML Звіт</span></button>'
    ].join('') });
    responseDiv.appendChild(actionBar);
    refreshIcons();

    actionBar.querySelector('.btn-copy').addEventListener('click', function () {
      const clean = rawMarkdown.replace(/<div class="warning-box">[\s\S]*?<\/div>\n?/, '');
      navigator.clipboard.writeText(clean).then(() => {
        this.classList.add('success');
        this.innerHTML = '<i data-lucide="check"></i> <span>Скопійовано</span>';
        refreshIcons();
        setTimeout(() => {
          this.classList.remove('success');
          this.innerHTML = '<i data-lucide="copy"></i> <span>Копіювати</span>';
          refreshIcons();
        }, 2000);
      }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = clean;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      });
    });

    actionBar.querySelector('.btn-pdf').addEventListener('click', () => {
      window.open(`/api/history/${researchId}/export/pdf?key=${encodeURIComponent(globalApiKey)}`, '_blank', 'noopener');
    });

    actionBar.querySelector('.btn-html').addEventListener('click', () => {
      window.open(`/api/history/${researchId}/export/html?key=${encodeURIComponent(globalApiKey)}`, '_blank', 'noopener');
    });

    const suggestions = [
      'Детальніше про джерела?',
      'Скласти порівняльний підсумок',
      'Які ключові тренди можна виділити?'
    ];
    const pillsContainer = el('div', { className: 'prompt-pills' });
    suggestions.forEach(sug => {
      const pill = document.createElement('button');
      pill.className = 'prompt-pill';
      pill.innerHTML = `<i data-lucide="sparkles"></i> <span>${escHtml(sug)}</span>`;
      pill.addEventListener('click', () => {
        promptInput.value = sug;
        autoResize();
        handleSearch();
      });
      pillsContainer.appendChild(pill);
    });
    responseDiv.appendChild(pillsContainer);
    refreshIcons();
    scrollToBottom();
  }

  /* ═══ SOURCES RENDERER ═══ */
  function renderSources(sources) {
    const list = _('sources-list');
    const count = _('sources-count');
    if (!list) return;
    list.innerHTML = '';
    if (!sources || sources.length === 0) {
      if (count) count.textContent = 'Знайдено 0 релевантних джерел.';
      list.innerHTML = '<div class="empty-state"><p>Релевантних джерел не знайдено.</p></div>';
      return;
    }
    if (count) count.textContent = `Знайдено ${sources.length} релевантних джерел.`;
    sources.forEach(src => {
      const id = src.id || src.source_id;
      const title = src.title || 'Джерело';
      const content = src.snippet || src.content || '';
      const score = src.relevance_score ? Math.round(src.relevance_score * 100) : 0;
      const card = el('div', { className: 'source-card', id: `card-${id}`, html: [
        '<div class="source-card-header">',
        `<span class="source-badge">[${escHtml(id)}]</span>`,
        `<span class="source-score">Рел: ${score}%</span>`,
        '</div>',
        `<div class="source-card-title">${escHtml(title)}</div>`,
        `<div class="source-card-snippet">${escHtml(content)}</div>`,
        '<div class="source-card-footer">',
        `<a href="${escHtml(src.url)}" target="_blank" rel="noopener" class="source-card-link"><span>Відкрити</span> <i data-lucide="external-link"></i></a>`,
        '</div>'
      ].join('') });
      list.appendChild(card);
    });
    refreshIcons();
  }

  /* ═══ CONTEXT MEMORY ═══ */
  function updateContextBar(percent, usedTokens) {
    const fill = _('context-bar-fill');
    const val = _('context-val');
    if (!fill || !val) return;
    const pct = (percent == null) ? 100 : percent;
    val.textContent = pct + '%';
    fill.style.width = pct + '%';
    if (pct > 50) {
      fill.style.background = '';
      fill.style.boxShadow = '';
    } else if (pct > 20) {
      fill.style.background = 'linear-gradient(135deg, #f59e0b, #fbbf24)';
      fill.style.boxShadow = '0 0 6px rgba(245,158,11,0.4)';
    } else {
      fill.style.background = 'linear-gradient(135deg, #ef4444, #f87171)';
      fill.style.boxShadow = '0 0 6px rgba(239,68,68,0.6)';
    }
    let used = usedTokens;
    if (used == null) used = Math.round(((100 - pct) / 100) * 128000);
    const formatted = used < 100 ? '0к' : (used / 1000).toFixed(1) + 'к';
    const indicator = _('context-memory-indicator');
    if (indicator) {
      indicator.setAttribute('title', `Використано ${formatted} токенів із 128к`);
      indicator.setAttribute('aria-valuenow', pct);
    }
  }

  /* ═══ OLLAMA STATUS ═══ */
  function setOllamaStatus(online) {
    setOllamaOnline(online);
    const dot = _('status-dot');
    const text = _('status-text');
    if (!dot || !text) return;
    dot.className = 'status-dot ' + (online ? 'online' : 'offline');
    text.textContent = online ? 'Система готова' : 'Тільки пошук (Без ШІ)';
  }

  /* ═══ WELCOME TEXT ═══ */
  function createWelcomeText() {
    return el('div', {
      className: 'welcome-text',
      id: 'welcome-text',
      html: 'Привіт! Я <strong>AI Search</strong>, ваш дружній пошуковий асистент. Що ви шукаєте?'
    });
  }

  /* ═══ SEARCH HANDLER ═══ */
  async function handleSearch() {
    setMobileView('chat');
    const text = promptInput.value.trim();
    if (!text || getIsThinking()) return;

    if (getCurrentMode() === 'people') {
      appendUserMessage(text);
      promptInput.value = '';
      showThinking();
      await osintPeopleSearch(text);
      return;
    }
    
    // Інші режими можуть бути додані тут (pentest, darknet, venator)
    // Поки що вони працюють через стандартний агентський ендпоїнт /api/agent
    // якщо режим не 'general'
    
    if (getCurrentMode() !== 'general') {
        appendUserMessage(text);
        promptInput.value = '';
        showThinking();
        await agentModeSearch(text);
        return;
    }

    const wt = _('welcome-text');
    if (wt) wt.remove();

    appendUserMessage(text);
    promptInput.value = '';
    promptInput.style.height = 'auto';
    updateSendBtn();

    showThinking();
    switchTab('tab-sources');
    const sl = _('sources-list');
    if (sl) sl.innerHTML = '<div class="loader-skeleton" style="margin-top:20px"><div class="skeleton-card"></div><div class="skeleton-card"></div></div>';
    const sc = _('sources-count');
    if (sc) sc.textContent = 'Сканування та аналіз...';

    setOllamaStatus(true);

    const payload = {
      query: text,
      loops: getDepth(),
      search_only: getSearchOnly(),
      mode: getCurrentMode()
    };
    const hid = getHistoryId();
    if (hid) payload.research_id = hid;

    let researchId = null;
    let aborted = false;

    try {
      const response = await fetchWithAuth('/api/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        let errMsg = 'Сталася помилка';
        try {
          const errBody = await response.json();
          errMsg = errBody.detail || errBody.message || errMsg;
        } catch (_) { }
        throw new Error(errMsg);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let responseDiv = null;
      let mdContent = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (aborted) { reader.cancel(); break; }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          let data;
          try {
            data = JSON.parse(trimmed);
          } catch (e) {
            continue;
          }

          try {
            switch (data.type) {
              case 'progress':
                {
                  const t = _('thinking-title');
                  if (t) t.textContent = data.message;
                  if (window.addSearchStep) window.addSearchStep(data.message);
                }
                break;
              case 'context':
                updateContextBar(data.remaining_percent, data.used_tokens);
                break;
              case 'sources':
                if (data.sources) {
                  renderSources(data.sources.map(s => ({
                    id: s.id || s.source_id,
                    title: s.title || 'Джерело',
                    url: s.url,
                    content: s.snippet || s.content || '',
                    relevance_score: s.relevance_score || 0
                  })));
                }
                break;
              case 'warning':
                setOllamaStatus(false);
                mdContent += `<div class="warning-box"><i data-lucide="alert-triangle"></i><div><h4>${escHtml(data.message)}</h4></div></div>\n`;
                break;
              case 'token':
                if (getIsThinking()) {
                  hideThinking();
                  responseDiv = el('div', { className: 'message ai-message' });
                  _('chat-messages').appendChild(responseDiv);
                }
                if (data.content) {
                  mdContent += data.content;
                  if (responseDiv) {
                    responseDiv.innerHTML = parseMarkdown(mdContent);
                    refreshIcons();
                    scrollToBottom();
                  }
                }
                break;
              case 'done':
                updateContextBar(100, data.used_tokens || 0);
                hideThinking(false);
                if (data.id) {
                  researchId = data.id;
                  setHistoryId(data.id);
                }
                fetchHistory();
                break;
              case 'error':
                throw new Error(data.message || 'Unknown error');
            }
          } catch (e) {
            console.error('Stream parse error:', e, data);
          }
        }
      }

      if (responseDiv) {
        postProcessResponse(responseDiv, researchId, mdContent);
      }

      if (getIsThinking()) {
        hideThinking();
        appendAIMessage(parseMarkdown('Помилка генерації або порожня відповідь.'), null, '', false);
      }

    } catch (err) {
      if (aborted) return;
      hideThinking();
      appendAIMessage(`<p style="color:var(--danger);font-weight:500;">Помилка: ${escHtml(err.message)}</p>`, null, '', false);
      const sl2 = _('sources-list');
      if (sl2) sl2.innerHTML = '';
      const sc2 = _('sources-count');
      if (sc2) sc2.textContent = 'Помилка при обробці.';
    }
  }

  /* ═══ NEWS FEED ═══ */
  async function loadNewsFeed() {
    const container = _('news-feed-container');
    if (!container) return;
    container.innerHTML = '<div class="loader-skeleton"><div class="skeleton-card"></div><div class="skeleton-card"></div><div class="skeleton-card"></div></div>';

    function render(items) {
      container.innerHTML = '';
      if (!items || items.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>Новин поки немає.</p></div>';
        return;
      }
      items.forEach(news => {
        const d = new Date(news.date_added);
        const fd = d.toLocaleDateString('uk-UA') + ' ' + d.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
        const card = document.createElement('div');
        card.className = 'news-card';
        card.innerHTML = [
          '<div class="news-meta">',
          `<span class="news-source">${escHtml(news.source)}</span>`,
          `<span class="news-date">${fd}</span>`,
          '</div>',
          `<div class="news-title">${escHtml(news.title)}</div>`,
          `<div class="news-snippet">${escHtml(news.content || '')}</div>`,
          `<a href="${escHtml(news.url)}" target="_blank" rel="noopener" class="news-link">Читати повністю <i data-lucide="external-link"></i></a>`
        ].join('');
        container.appendChild(card);
      });
      refreshIcons();
    }

    try {
      const res = await fetchWithAuth('/api/news?limit=20');
      const data = await res.json();
      if (!data || data.length === 0) {
        try {
          await fetchWithAuth('/api/news/repopulate', { method: 'POST' });
          const res2 = await fetchWithAuth('/api/news?limit=20');
          const data2 = await res2.json();
          render(data2);
        } catch (_) {
          render([]);
        }
      } else {
        render(data);
      }
    } catch (_) {
      container.innerHTML = '<div class="empty-state"><p style="color:var(--danger)">Помилка завантаження новин</p></div>';
    }
  }

  /* ═══ HISTORY ═══ */
  async function fetchHistory() {
    try {
      const res = await fetchWithAuth('/api/history');
      const data = await res.json();
      const count = _('history-count');
      const list = _('history-list');
      if (count) count.textContent = data.length;
      if (!list) return;
      list.innerHTML = '';
      if (data.length === 0) {
        list.innerHTML = '<div class="history-empty">Історія порожня</div>';
        return;
      }
      data.forEach(item => {
        const div = document.createElement('div');
        div.className = 'history-item' + (getHistoryId() === item.id ? ' active-item' : '');
        div.innerHTML = [
          `<span class="history-item-text">${escHtml(item.query)}</span>`,
          '<button class="history-delete-btn" aria-label="Видалити"><i data-lucide="trash-2"></i></button>'
        ].join('');
        div.addEventListener('click', (e) => {
          if (e.target.closest('.history-delete-btn')) return;
          loadHistoryDetails(item.id);
        });
        const delBtn = div.querySelector('.history-delete-btn');
        if (delBtn) {
          delBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteHistoryItem(item.id);
          });
        }
        list.appendChild(div);
      });
      refreshIcons();
    } catch (err) {
      console.error('History fetch error:', err);
    }
  }

  async function loadHistoryDetails(id) {
    setMobileView('chat');
    const wt = _('welcome-text');
    if (wt) wt.remove();
    showThinking();
    const sc = _('sources-count');
    if (sc) sc.textContent = 'Завантаження...';

    try {
      const res = await fetchWithAuth(`/api/history/${id}`);
      const data = await res.json();
      hideThinking();
      setHistoryId(data.id);

      _('chat-messages').innerHTML = '';
      setOllamaStatus(!data.ollama_warning);
      updateContextBar(data.remaining_context_percent, data.used_tokens);

      if (data.messages && data.messages.length > 0) {
        data.messages.forEach((msg, idx) => {
          if (msg.role === 'user') {
            appendUserMessage(msg.content);
          } else {
            const isLast = idx === data.messages.length - 1;
            appendAIMessage(parseMarkdown(msg.content), isLast ? data.id : null, msg.content, isLast);
          }
        });
      } else {
        appendUserMessage(data.query);
        appendAIMessage(parseMarkdown(data.answer), data.id, data.answer, true);
      }

      renderSources(data.sources);
      promptInput.value = '';
      autoResize();
      fetchHistory();
    } catch (err) {
      hideThinking();
      appendAIMessage(`<p style="color:var(--danger)">${escHtml(err.message)}</p>`, null, '', false);
    }
  }

  function deleteHistoryItem(id) {
    if (!confirm('Видалити?')) return;
    fetchWithAuth(`/api/history/${id}`, { method: 'DELETE' })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          if (getHistoryId() === id) _('new-chat-btn').click();
          fetchHistory();
        }
      })
      .catch(err => console.error('Delete error:', err));
  }

  /* ═══ SERIF MODE ═══ */
  function applySerifMode(enabled) {
    _('chat-messages').classList.toggle('serif-mode', enabled);
    const btn = _('serif-btn');
    if (btn) btn.classList.toggle('active', enabled);
    localStorage.setItem('serifMode', enabled);
  }

  /* ═══ MOBILE NAV SYSTEM ═══ */
  function setMobileView(viewName) {
    const layout = $('.app-layout');
    if (layout) {
      layout.setAttribute('data-mobile-view', viewName);
    }
    $$('.mobile-nav-item').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === viewName);
    });
    
    // Auto load news feed if switching to panel and News tab is active
    if (viewName === 'panel') {
      const activeTab = $('.panel-tab.active');
      if (activeTab && activeTab.dataset.target === 'tab-news') {
        loadNewsFeed();
      }
    }
    
    refreshIcons();
  }

  /* ═══ EVENT SETUP ═══ */
  function initEvents() {
    /* Mobile navigation buttons */
    $$('.mobile-nav-item').forEach(item => {
      item.addEventListener('click', () => {
        const view = item.dataset.view;
        if (view) setMobileView(view);
      });
    });

    /* Theme chips */
    $$('.theme-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        setTheme(chip.dataset.theme);
        applyTheme(chip.dataset.theme);
      });
    });

    /* Panel tabs */
    $$('.panel-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        if (!tab.dataset.target) return;
        switchTab(tab.dataset.target);
      });
    });

    /* New chat */
    _('new-chat-btn').addEventListener('click', () => {
      setMobileView('chat');
      _('chat-messages').innerHTML = '';
      _('chat-messages').appendChild(createWelcomeText());
      refreshIcons();
      switchTab('tab-info');
      setHistoryId(null);
      $$('.history-item').forEach(item => item.classList.remove('active-item'));
      updateContextBar(100);
    });

    /* Depth buttons */
    $$('.depth-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        $$('.depth-btn').forEach(b => {
          b.classList.remove('active');
          b.setAttribute('aria-checked', 'false');
        });
        this.classList.add('active');
        this.setAttribute('aria-checked', 'true');
        setDepth(parseInt(this.dataset.depth));
      });
    });

    /* Search only checkbox */
    const soc = _('search-only-check');
    if (soc) {
      soc.addEventListener('change', function () {
        setSearchOnly(this.checked);
        const tg = $('.toggle-group');
        if (tg) {
          tg.style.opacity = this.checked ? '0.3' : '1';
          tg.style.pointerEvents = this.checked ? 'none' : 'auto';
        }
      });
    }

    /* Input events */
    promptInput.addEventListener('input', autoResize);
    promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) handleSearch();
      }
    });
    sendBtn.addEventListener('click', (e) => {
      e.preventDefault();
      handleSearch();
    });

    /* Sidebar toggle */
    _('sidebar-toggle-btn').addEventListener('click', () => {
      if (window.innerWidth <= 768) {
        const layout = $('.app-layout');
        const currentView = layout.getAttribute('data-mobile-view') || 'chat';
        const targetView = currentView === 'sidebar' ? 'chat' : 'sidebar';
        setMobileView(targetView);
        return;
      }

      const layout = $('.app-layout');
      layout.classList.toggle('sidebar-collapsed');
      const isCollapsed = layout.classList.contains('sidebar-collapsed');
      const btn = _('sidebar-toggle-btn');
      const icon = btn.querySelector('i');
      btn.classList.toggle('active', isCollapsed);
      btn.setAttribute('title', isCollapsed ? 'Показати бічну панель' : 'Сховати бічну панель');
      btn.setAttribute('aria-label', isCollapsed ? 'Показати бічну панель' : 'Сховати бічну панель');
      icon.setAttribute('data-lucide', isCollapsed ? 'panel-left-open' : 'panel-left-close');
      localStorage.setItem('sidebarCollapsed', isCollapsed);
      refreshIcons();
      window.dispatchEvent(new Event('resize'));
    });

    /* Zen mode */
    _('zen-btn').addEventListener('click', () => {
      const layout = $('.app-layout');
      layout.classList.toggle('zen-mode');
      const isZen = layout.classList.contains('zen-mode');
      const icon = _('zen-btn').querySelector('i');
      _('zen-btn').setAttribute('title', isZen ? 'Вийти з режиму фокусування' : 'Режим фокусування (Zen Mode)');
      _('zen-btn').setAttribute('aria-label', isZen ? 'Вийти з режиму фокусування' : 'Увімкнути режим фокусування');
      icon.setAttribute('data-lucide', isZen ? 'minimize-2' : 'maximize-2');
      refreshIcons();
    });

    /* Serif mode */
    _('serif-btn').addEventListener('click', () => {
      setSerifMode(!getSerifMode());
      applySerifMode(getSerifMode());
    });

    /* Refresh news */
    _('refresh-news-btn').addEventListener('click', function () {
      const icon = this.querySelector('i');
      if (icon) icon.style.animation = 'spin 1s linear infinite';
      fetch('/api/news/repopulate', { method: 'POST' })
        .then(() => loadNewsFeed())
        .catch(() => loadNewsFeed())
        .finally(() => {
          setTimeout(() => { if (icon) icon.style.animation = ''; }, 1000);
        });
    });

    /* Close canvas */
    const ccb = _('close-canvas-btn');
    if (ccb) {
      ccb.addEventListener('click', () => switchTab('tab-info'));
    }

    /* Mode selector */
    $$('.mode-btn').forEach(btn => {
      btn.addEventListener('click', function() {
        $$('.mode-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        setCurrentMode(this.dataset.mode);
        
        // Візуальний зворотний зв'язок
        const icon = _('input-container').querySelector('.input-icon');
        if (this.dataset.mode === 'people') icon.setAttribute('data-lucide', 'user-search');
        else if (this.dataset.mode === 'pentest') icon.setAttribute('data-lucide', 'shield-alert');
        else if (this.dataset.mode === 'darknet') icon.setAttribute('data-lucide', 'eye-off');
        else if (this.dataset.mode === 'venator') icon.setAttribute('data-lucide', 'monitor');
        else icon.setAttribute('data-lucide', 'zap');
        refreshIcons();
      });
    });

    /* Example prompts (event delegation) */
    _('tab-info').addEventListener('click', (e) => {
      const li = e.target.closest('.examples-list li');
      if (li && li.dataset.prompt) {
        promptInput.value = li.dataset.prompt;
        autoResize();
        handleSearch();
      }
    });

    /* Input form submission */
    _('input-form').addEventListener('submit', (e) => {
      e.preventDefault();
      if (!sendBtn.disabled) handleSearch();
    });
  }

  /* ═══ ADVANCED OSINT FUNCTIONS ═══ */
  async function osintPeopleSearch(query) {
    try {
      const response = await fetchWithAuth('/api/osint/people', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      });
      const data = await response.json();
      hideThinking();
      displayOsintResults(data);
    } catch (err) {
      hideThinking();
      appendAIMessage(`<p style="color:var(--danger)">Помилка OSINT пошуку: ${escHtml(err.message)}</p>`);
    }
  }

  function displayOsintResults(data) {
    const chat = _('chat-messages');
    const resultDiv = el('div', { className: 'message ai-message' });
    
    let html = `<h2>OSINT Результати: ${escHtml(data.query)}</h2>`;
    
    // Соцмережі
    const social = data.raw_data.social_media_found || [];
    if (social.length > 0) {
      html += '<h3>Профілі в соцмережах</h3><ul class="osint-list">';
      social.forEach(p => {
        if (p.found) {
          html += `<li><a href="${escHtml(p.url)}" target="_blank" rel="noopener"><i data-lucide="external-link"></i> ${escHtml(p.platform)}</a></li>`;
        }
      });
      html += '</ul>';
    }
    
    // Аналіз
    html += `<div class="analysis-content">${parseMarkdown(data.analysis)}</div>`;
    
    resultDiv.innerHTML = html;
    chat.appendChild(resultDiv);
    refreshIcons();
    scrollToBottom();
  }

  async function agentModeSearch(query) {
      // Аналогічно handleSearch але на /api/agent
      const payload = { query };
      try {
          const response = await fetchWithAuth('/api/agent', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
          });
          // Тут має бути стрімінг, але для MVP зробимо просто виклик
          hideThinking();
          appendAIMessage(parseMarkdown("Агент активовано. Використовую інструменти для аналізу..."));
      } catch (err) {
          hideThinking();
          appendAIMessage(`<p style="color:var(--danger)">Помилка агента: ${escHtml(err.message)}</p>`);
      }
  }

  /* ═══ EXPORT FUNCTIONS ═══ */
  window.exportJSON = async function() {
    const id = getHistoryId();
    if (!id) return alert('Спочатку виконайте пошук');
    window.open(`/api/history/${id}/export/json`, '_blank');
  };

  window.exportCSV = async function() {
    const id = getHistoryId();
    if (!id) return alert('Спочатку виконайте пошук');
    // window.open(`/api/history/${id}/export/csv`, '_blank');
    alert('Експорт в CSV буде доступний у наступному оновленні');
  };

  window.exportDOCX = async function() {
    const id = getHistoryId();
    if (!id) return alert('Спочатку виконайте пошук');
    // window.open(`/api/history/${id}/export/docx`, '_blank');
    alert('Експорт в DOCX буде доступний у наступному оновленні');
  };

  /* ═══ RESIZABLE PANELS ═══ */
  initResizer('left-resizer', '.sidebar', () => 260, (w) => { }, 200, 450, 'sidebarWidth');
  initResizer('right-resizer', '.right-panel', () => 400, (w) => { }, 300, 650, 'rightPanelWidth');

  async function initApiKey() {
    try {
      const resp = await fetch('/api/config/key');
      const data = await resp.json();
      globalApiKey = data.api_key;
      return true;
    } catch (e) {
      console.error('Failed to init API Key:', e);
      return false;
    }
  }

  async function pollStatus() {
    try {
      const resp = await fetchWithAuth('/api/status');
      const data = await resp.json();
      setOllamaStatus(data.ollama_online);
    } catch (e) {
      setOllamaStatus(false);
    }
    setTimeout(pollStatus, 10000); // Перевірка кожні 10 секунд
  }

  /* ═══ INIT ═══ */
  async function init() {
    /* Set default mobile view state */
    const layout = $('.app-layout');
    if (layout && !layout.hasAttribute('data-mobile-view')) {
      layout.setAttribute('data-mobile-view', 'chat');
    }

    /* Apply saved theme */
    const savedTheme = localStorage.getItem('selectedTheme') || 'amethyst';
    applyTheme(savedTheme);

    /* Apply serif mode */
    applySerifMode(getSerifMode());

    /* Restore sidebar collapsed state */
    if (localStorage.getItem('sidebarCollapsed') === 'true') {
      $('.app-layout').classList.add('sidebar-collapsed');
      const btn = _('sidebar-toggle-btn');
      if (btn) {
        btn.classList.add('active');
        btn.setAttribute('title', 'Показати бічну панель');
        btn.setAttribute('aria-label', 'Показати бічну панель');
        const icon = btn.querySelector('i');
        if (icon) icon.setAttribute('data-lucide', 'panel-left-open');
      }
    }

    // Спочатку ініціалізуємо ключ, потім робимо запити
    const ok = await initApiKey();
    if (ok) {
        /* Initial fetches */
        fetchHistory();
        pollStatus(); // Починаємо моніторинг статусу
        updateContextBar(100);

        /* Load news in background if tab-news is not active (deferred) */
        setTimeout(() => {
          if (!$('#tab-news.hidden')) loadNewsFeed();
        }, 1000);
    } else {
        alert('Помилка безпеки: Не вдалося отримати API ключ. Спробуйте оновити сторінку.');
    }

    /* Init icons */
    refreshIcons();

    /* Init events */
    initEvents();
  }

  init();
});
