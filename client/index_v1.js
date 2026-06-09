/* client/index.js */

document.addEventListener("DOMContentLoaded", () => {
    // --- STATE MANAGEMENT ---
    let currentDepth = 0; // loops=0 by default
    let searchOnly = false;
    let selectedHistoryId = null;
    let rawReportMarkdown = "";

    // --- DOM ELEMENTS ---
    const searchInput = document.getElementById("search-input");
    const searchSubmit = document.getElementById("search-submit");
    const depthBtns = document.querySelectorAll(".depth-btn");
    const searchOnlyCheck = document.getElementById("search-only-check");
    const suggestTags = document.querySelectorAll(".suggest-tag");
    
    const landingSection = document.getElementById("landing-section");
    const statusSection = document.getElementById("status-section");
    const resultsSection = document.getElementById("results-section");
    
    const statusTitle = document.getElementById("status-title");
    const statusDesc = document.getElementById("status-desc");
    const statusProgress = document.getElementById("status-progress");
    
    const reportBody = document.getElementById("report-body");
    const reportDate = document.getElementById("report-date");
    const reportSourcesCount = document.getElementById("report-sources-count");
    const sourcesGrid = document.getElementById("sources-grid");
    
    const historyList = document.getElementById("history-list");
    const historyCount = document.getElementById("history-count");
    
    const btnCopy = document.getElementById("btn-copy");
    const btnDownload = document.getElementById("btn-download");

    // Initialize Lucide icons on load
    lucide.createIcons();
    fetchHistory();

    // --- TEXTAREA AUTO-RESIZE & KEYBOARD EVENTS ---
    searchInput.addEventListener("input", function () {
        this.style.height = "auto";
        this.style.height = (this.scrollHeight - 10) + "px";
    });

    searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            triggerSearch();
        }
    });

    searchSubmit.addEventListener("click", triggerSearch);

    // --- SEARCH CONTROLS ---
    depthBtns.forEach(btn => {
        btn.addEventListener("click", function() {
            depthBtns.forEach(b => b.classList.remove("active"));
            this.classList.add("active");
            currentDepth = parseInt(this.getAttribute("data-depth"));
        });
    });

    searchOnlyCheck.addEventListener("change", function() {
        searchOnly = this.checked;
        const depthContainer = document.querySelector(".toggle-container");
        if (searchOnly) {
            // Тільки пошук не потребує вибору глибини ШІ
            depthContainer.style.opacity = "0.4";
            depthContainer.style.pointerEvents = "none";
        } else {
            depthContainer.style.opacity = "1";
            depthContainer.style.pointerEvents = "auto";
        }
    });

    // Suggestion tags
    suggestTags.forEach(tag => {
        tag.addEventListener("click", () => {
            searchInput.value = tag.innerText;
            searchInput.dispatchEvent(new Event('input')); // resize textarea
            searchInput.focus();
        });
    });

    // --- ACTIONS ---
    btnCopy.addEventListener("click", () => {
        navigator.clipboard.writeText(rawReportMarkdown)
            .then(() => {
                const span = btnCopy.querySelector("span");
                const oldText = span.innerText;
                span.innerText = "Скопійовано!";
                btnCopy.style.borderColor = "var(--accent-cyan)";
                setTimeout(() => {
                    span.innerText = oldText;
                    btnCopy.style.borderColor = "var(--border-dark)";
                }, 2000);
            })
            .catch(err => console.error("Не вдалося скопіювати:", err));
    });

    btnDownload.addEventListener("click", () => {
        const querySafe = searchInput.value.trim().substring(0, 30).replace(/[^a-z0-9а-яієґ]/gi, '_');
        const blob = new Blob([rawReportMarkdown], { type: "text/markdown;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", `AI_Search_Report_${querySafe || "report"}.md`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    });

    // --- SEARCH LOGIC ---
    function triggerSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        // Reset UI views
        landingSection.classList.add("hidden");
        resultsSection.classList.add("hidden");
        statusSection.classList.remove("hidden");
        
        // Disable input
        searchInput.disabled = true;
        searchSubmit.disabled = true;

        // Animate Loader Statuses
        let progressVal = 10;
        statusProgress.style.width = `${progressVal}%`;
        statusTitle.innerText = "Ініціалізація дослідження...";
        statusDesc.innerText = "Очищення та аналіз запиту...";

        const progressInterval = setInterval(() => {
            if (progressVal < 90) {
                progressVal += Math.floor(Math.random() * 5) + 2;
                statusProgress.style.width = `${progressVal}%`;
                
                if (progressVal > 25 && progressVal < 45) {
                    statusTitle.innerText = "Пошук в Інтернеті...";
                    statusDesc.innerText = searchOnly 
                        ? "Сканування DuckDuckGo та Bing..." 
                        : "Визначення кращих джерел та завантаження повного контенту...";
                } else if (progressVal >= 45 && progressVal < 70) {
                    statusTitle.innerText = "Рейтингування джерел та очищення безпеки...";
                    statusDesc.innerText = "Фільтрація нерелевантного вмісту та видалення adult-доменів...";
                } else if (progressVal >= 70 && !searchOnly) {
                    statusTitle.innerText = "Генерація фінального звіту ШІ...";
                    statusDesc.innerText = `Локальна модель ${currentDepth > 0 ? "ітеративно аналізує прогалини" : "синтезує знайдений вміст"}...`;
                }
            }
        }, 1200);

        // API Request
        fetch("/api/research", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                query: query,
                loops: currentDepth,
                search_only: searchOnly
            })
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw new Error(err.detail || "Сталася помилка"); });
            }
            return response.json();
        })
        .then(data => {
            clearInterval(progressInterval);
            statusProgress.style.width = "100%";
            statusTitle.innerText = "Дослідження завершено!";
            statusDesc.innerText = "Форматування результатів...";

            setTimeout(() => {
                statusSection.classList.add("hidden");
                renderReport(data);
                fetchHistory(); // Refresh sidebar history
                
                // Re-enable input
                searchInput.disabled = false;
                searchSubmit.disabled = false;
            }, 600);
        })
        .catch(err => {
            clearInterval(progressInterval);
            statusSection.classList.add("hidden");
            alert("Помилка: " + err.message);
            
            // Re-enable input
            searchInput.disabled = false;
            searchSubmit.disabled = false;
            landingSection.classList.remove("hidden");
        });
    }

    // --- RENDERING RESULTS ---
    function renderReport(data) {
        selectedHistoryId = data.id;
        rawReportMarkdown = data.answer;
        
        // Highlight active sidebar item
        document.querySelectorAll(".history-item").forEach(item => {
            item.classList.remove("active");
            if (parseInt(item.getAttribute("data-id")) === data.id) {
                item.classList.add("active");
            }
        });

        // Set metadata
        reportDate.innerText = formatDate(data.created_at || new Date().toISOString());
        reportSourcesCount.innerText = `${data.sources.length} джерел(а) використано`;
        
        // Parse & Render Body (lightweight markdown parser)
        let htmlContent = "";
        
        if (data.ollama_warning) {
            htmlContent += `
            <div class="warning-box">
                <i data-lucide="alert-triangle"></i>
                <div>
                    <h4>Модель Ollama недоступна</h4>
                    <p>Бекенд не зміг з'єднатися з локальною Ollama сервером. Результати виведено в режимі Search-Only.</p>
                </div>
            </div>
            `;
        }

        htmlContent += parseMarkdown(data.answer);
        reportBody.innerHTML = htmlContent;

        // Render Sources Cards
        sourcesGrid.innerHTML = "";
        if (data.sources.length === 0) {
            sourcesGrid.innerHTML = `<div class="history-empty" style="grid-column: 1/-1"><p>Релевантних джерел не знайдено</p></div>`;
        } else {
            data.sources.forEach(src => {
                const card = document.createElement("div");
                card.className = "source-card";
                card.id = `card-${src.id}`;
                
                const score = src.relevance_score ? Math.round(src.relevance_score * 100) : 0;
                
                card.innerHTML = `
                    <div class="source-card-header">
                        <span class="source-badge">${src.id}</span>
                        <span class="source-score-ring">Релевантність: ${score}%</span>
                    </div>
                    <h4 class="source-card-title" title="${src.title}">${src.title}</h4>
                    <p class="source-card-snippet">${src.content || "Немає доступного фрагменту вмісту."}</p>
                    <div class="source-card-footer">
                        <a href="${src.url}" target="_blank" class="source-card-link">
                            <span>Перейти на сайт</span>
                            <i data-lucide="external-link"></i>
                        </a>
                        <span class="source-card-date">${src.fetched_at ? formatTime(src.fetched_at) : ""}</span>
                    </div>
                `;
                sourcesGrid.appendChild(card);
            });
        }

        // Reinitialize icons in rendered elements
        lucide.createIcons();
        
        // Bind event listeners to new neon citation badges
        document.querySelectorAll(".cite-badge").forEach(badge => {
            badge.addEventListener("click", function() {
                const targetId = this.getAttribute("data-target");
                const card = document.getElementById(`card-${targetId}`);
                if (card) {
                    card.scrollIntoView({ behavior: "smooth", block: "center" });
                    
                    // Flash highlight
                    card.classList.add("highlight");
                    setTimeout(() => {
                        card.classList.remove("highlight");
                    }, 2000);
                }
            });
        });

        resultsSection.classList.remove("hidden");
    }

    // --- MARKDOWN COMPILER ---
    function parseMarkdown(md) {
        if (!md) return "";
        let html = md;

        // Remove double slash comments if any
        html = html.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        // Headers
        html = html.replace(/^\s*###\s+(.*?)$/gm, '<h3>$1</h3>');
        html = html.replace(/^\s*##\s+(.*?)$/gm, '<h2>$1</h2>');
        html = html.replace(/^\s*#\s+(.*?)$/gm, '<h2>$1</h2>'); // Render H1 as H2 for sub-theme consistency

        // Bold & Italic
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

        // Horizontal line
        html = html.replace(/^\s*---\s*$/gm, '<hr class="divider">');

        // Lists
        // Simple list item conversion
        html = html.replace(/^\s*[-*]\s+(.*?)$/gm, '<li>$1</li>');
        // Wrap contiguous list items in ul
        html = html.replace(/(<li>.*?<\/li>)+/gs, '<ul>$&</ul>');

        // Source Citation Badges conversion
        // matches [S1], [S2] etc.
        html = html.replace(/\[(S\d+)\]/g, '<sup class="cite-badge" data-target="$1">$1</sup>');

        // Convert double linebreaks into paragraphs
        html = html.replace(/\n\n/g, '</p><p>');
        
        // Clean up unclosed paragraphs
        html = `<p>${html}</p>`;
        html = html.replace(/<p>\s*<\/p>/g, '');
        html = html.replace(/<p>\s*<h2>/g, '<h2>').replace(/<\/h2>\s*<\/p>/g, '</h2>');
        html = html.replace(/<p>\s*<h3>/g, '<h3>').replace(/<\/h3>\s*<\/p>/g, '</h3>');
        html = html.replace(/<p>\s*<ul>/g, '<ul>').replace(/<\/ul>\s*<\/p>/g, '</ul>');
        html = html.replace(/<p>\s*<hr/g, '<hr').replace(/<\/hr>\s*<\/p>/g, '</hr>');
        html = html.replace(/<p>\s*<div/g, '<div').replace(/<\/div>\s*<\/p>/g, '</div>');

        return html;
    }

    // --- HISTORY SIDEBAR LOGIC ---
    function fetchHistory() {
        fetch("/api/history")
            .then(res => res.json())
            .then(data => {
                historyCount.innerText = data.length;
                historyList.innerHTML = "";
                
                if (data.length === 0) {
                    historyList.innerHTML = `
                        <div class="history-empty">
                            <i data-lucide="history"></i>
                            <p>Історія запитів порожня</p>
                        </div>
                    `;
                    lucide.createIcons();
                    return;
                }

                data.forEach(item => {
                    const card = document.createElement("div");
                    card.className = `history-item ${selectedHistoryId === item.id ? "active" : ""}`;
                    card.setAttribute("data-id", item.id);
                    
                    card.innerHTML = `
                        <div class="history-item-content">
                            <div class="history-item-title" title="${item.query}">${item.query}</div>
                            <div class="history-item-date">${formatDate(item.created_at)}</div>
                        </div>
                        <button class="history-delete-btn" title="Видалити запис">
                            <i data-lucide="trash-2"></i>
                        </button>
                    `;

                    // Click item to load past research
                    card.querySelector(".history-item-content").addEventListener("click", () => {
                        loadHistoryDetails(item.id);
                    });

                    // Delete item trigger
                    card.querySelector(".history-delete-btn").addEventListener("click", (e) => {
                        e.stopPropagation(); // Stop loading details
                        if (confirm(`Ви дійсно бажаєте видалити цей запис із історії?`)) {
                            deleteHistoryItem(item.id, card);
                        }
                    });

                    historyList.appendChild(card);
                });
                
                lucide.createIcons();
            })
            .catch(err => console.error("Помилка отримання історії:", err));
    }

    function loadHistoryDetails(id) {
        landingSection.classList.add("hidden");
        statusSection.classList.remove("hidden");
        resultsSection.classList.add("hidden");
        
        statusProgress.style.width = "40%";
        statusTitle.innerText = "Завантаження звіту...";
        statusDesc.innerText = "Вилучення збережених даних з бази SQLite...";

        fetch(`/api/history/${id}`)
            .then(res => {
                if (!res.ok) throw new Error("Не вдалося завантажити деталі");
                return res.json();
            })
            .then(data => {
                statusProgress.style.width = "100%";
                setTimeout(() => {
                    statusSection.classList.add("hidden");
                    renderReport(data);
                    
                    // Fill search bar with loaded query
                    searchInput.value = data.query;
                    searchInput.dispatchEvent(new Event('input'));
                }, 300);
            })
            .catch(err => {
                statusSection.classList.add("hidden");
                alert(err.message);
                landingSection.classList.remove("hidden");
            });
    }

    function deleteHistoryItem(id, element) {
        fetch(`/api/history/${id}`, {
            method: "DELETE"
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                // Fade out animation
                element.style.transform = "scale(0.9)";
                element.style.opacity = "0";
                
                setTimeout(() => {
                    fetchHistory();
                    if (selectedHistoryId === id) {
                        resultsSection.classList.add("hidden");
                        landingSection.classList.remove("hidden");
                        searchInput.value = "";
                        searchInput.dispatchEvent(new Event('input'));
                    }
                }, 300);
            }
        })
        .catch(err => alert("Не вдалося видалити запис: " + err.message));
    }

    // --- HELPER FORMATTING FUNCTIONS ---
    function formatDate(isoString) {
        try {
            const date = new Date(isoString);
            return date.toLocaleDateString("uk-UA", {
                day: "numeric",
                month: "long",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit"
            });
        } catch (e) {
            return isoString;
        }
    }

    function formatTime(isoString) {
        try {
            const date = new Date(isoString);
            return date.toLocaleTimeString("uk-UA", {
                hour: "2-digit",
                minute: "2-digit"
            });
        } catch (e) {
            return "";
        }
    }
});
