const { app, BrowserWindow, ipcMain, dialog, Menu, Notification } = require("electron");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");

const CACHE_DIR = path.join(app.getPath("userData"), "cache");
const CACHE_FILE = path.join(CACHE_DIR, "cache.json");
const SETTINGS_FILE = path.join(app.getPath("userData"), "settings.json");

function ensureCacheDir() {
  if (!fs.existsSync(CACHE_DIR)) {
    fs.mkdirSync(CACHE_DIR, { recursive: true });
  }
}

function readCache() {
  ensureCacheDir();
  try {
    if (fs.existsSync(CACHE_FILE)) {
      return JSON.parse(fs.readFileSync(CACHE_FILE, "utf-8"));
    }
  } catch (e) {
    console.error("Cache read error:", e);
  }
  return { entries: [] };
}

function writeCache(data) {
  ensureCacheDir();
  fs.writeFileSync(CACHE_FILE, JSON.stringify(data, null, 2), "utf-8");
}

function readSettings() {
  try {
    if (fs.existsSync(SETTINGS_FILE)) {
      return JSON.parse(fs.readFileSync(SETTINGS_FILE, "utf-8"));
    }
  } catch (e) {
    console.error("Settings read error:", e);
  }
  return {
    serverUrl: "http://127.0.0.1:8000",
    apiKey: "dev-secret-key",
    theme: "dark",
  };
}

function writeSettings(settings) {
  fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2), "utf-8");
}

let mainWindow = null;

let SERVER_URL = readSettings().serverUrl || "http://127.0.0.1:8000";
const MAX_RETRIES = 20;   // 20 спроб × 500мс = 10 секунд очікування
const RETRY_MS   = 500;

function waitForServer(url, retriesLeft) {
  const net = require("net");
  return new Promise((resolve) => {
    const client = net.createConnection({ host: "127.0.0.1", port: 8000 }, () => {
      client.destroy();
      resolve(true);
    });
    client.on("error", () => {
      client.destroy();
      if (retriesLeft > 0) {
        setTimeout(() => waitForServer(url, retriesLeft - 1).then(resolve), RETRY_MS);
      } else {
        resolve(false);
      }
    });
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: "AI OSINT Deep Research — Desktop",
    icon: path.join(__dirname, "assets", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      // Дозволяємо завантаження локального сервера
      webSecurity: true,
    },
    show: false,
    backgroundColor: "#0f0f0f",
  });

  const menu = Menu.buildFromTemplate([
    {
      label: "Файл",
      submenu: [
        { label: "Оновити", accelerator: "F5", click: () => mainWindow.webContents.reload() },
        { type: "separator" },
        { label: "Відкрити в браузері", click: () => { const { shell } = require("electron"); shell.openExternal(SERVER_URL); } },
        { type: "separator" },
        { role: "quit", label: "Вийти" },
      ],
    },
    {
      label: "Правка",
      submenu: [
        { role: "undo", label: "Скасувати" },
        { role: "redo", label: "Повторити" },
        { type: "separator" },
        { role: "cut", label: "Вирізати" },
        { role: "copy", label: "Копіювати" },
        { role: "paste", label: "Вставити" },
        { role: "selectAll", label: "Вибрати все" },
      ],
    },
    {
      label: "Вигляд",
      submenu: [
        { role: "reload", label: "Перезавантажити" },
        { role: "forceReload", label: "Примусово перезавантажити" },
        { role: "toggleDevTools", label: "Інструменти розробника" },
        { type: "separator" },
        { role: "resetZoom", label: "Стандартний масштаб" },
        { role: "zoomIn", label: "Збільшити" },
        { role: "zoomOut", label: "Зменшити" },
        { type: "separator" },
        { role: "togglefullscreen", label: "Повноекранний режим" },
      ],
    },
  ]);
  Menu.setApplicationMenu(menu);

  // Спочатку показуємо заглушку поки сервер стартує
  mainWindow.loadURL(`data:text/html;charset=utf-8,
    <html>
    <head><meta charset="utf-8"><style>
      body { margin:0; background:#0f0f0f; display:flex; align-items:center;
             justify-content:center; height:100vh; font-family:system-ui,sans-serif; }
      .box { text-align:center; color:#e0e0e0; }
      h2   { font-size:1.4rem; margin-bottom:.5rem; color:#a78bfa; }
      p    { color:#666; font-size:.9rem; margin:0; }
      .dot { display:inline-block; width:8px; height:8px; border-radius:50%;
             background:#a78bfa; margin:0 3px; animation:pulse 1.2s infinite; }
      .dot:nth-child(2){ animation-delay:.2s; }
      .dot:nth-child(3){ animation-delay:.4s; }
      @keyframes pulse{ 0%,80%,100%{opacity:.3} 40%{opacity:1} }
    </style></head>
    <body><div class="box">
      <h2>AI OSINT Deep Research</h2>
      <p>Підключення до сервера<span class="dot"></span><span class="dot"></span><span class="dot"></span></p>
    </div></body></html>`);

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    // Чекаємо поки FastAPI-сервер підніметься, потім завантажуємо UI
    waitForServer(SERVER_URL, MAX_RETRIES).then((ok) => {
      if (ok) {
        mainWindow.loadURL(SERVER_URL);
      } else {
        mainWindow.loadURL(`data:text/html;charset=utf-8,
          <html><head><meta charset="utf-8"><style>
            body{margin:0;background:#0f0f0f;display:flex;align-items:center;
                 justify-content:center;height:100vh;font-family:system-ui,sans-serif;}
            .box{text-align:center;color:#e0e0e0;}
            h2{color:#f87171;margin-bottom:.5rem;}
            p{color:#888;font-size:.9rem;}
            button{margin-top:1rem;padding:.5rem 1.2rem;background:#a78bfa;color:#fff;
                   border:none;border-radius:6px;cursor:pointer;font-size:.9rem;}
            button:hover{background:#7c3aed;}
          </style></head><body><div class="box">
            <h2>⚠ Сервер недоступний</h2>
            <p>Не вдалося підключитися до сервера:</p>
            <p style="color:#a78bfa; font-weight:bold; margin-top:5px; margin-bottom:15px;">${SERVER_URL}</p>
            <p style="font-size:0.85rem;">(Переконайтесь, що сервер запущено, або змініть адресу у налаштуваннях)</p>
            <button onclick="location.reload()">Спробувати знову</button>
          </div></body></html>`);
      }
    });
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

ipcMain.handle("settings:load", () => readSettings());
ipcMain.handle("settings:save", (_e, settings) => {
  writeSettings(settings);
  return true;
});

ipcMain.handle("cache:list", () => {
  const data = readCache();
  return data.entries.sort((a, b) => b.cachedAt - a.cachedAt);
});

ipcMain.handle("cache:save", (_e, entry) => {
  const data = readCache();
  entry.id = crypto.randomUUID();
  entry.cachedAt = Date.now();
  data.entries.push(entry);
  writeCache(data);
  return entry.id;
});

ipcMain.handle("cache:get", (_e, id) => {
  const data = readCache();
  return data.entries.find((e) => e.id === id) || null;
});

ipcMain.handle("cache:search", (_e, query) => {
  const data = readCache();
  const q = query.toLowerCase();
  return data.entries.filter((e) => {
    return (
      e.query.toLowerCase().includes(q) ||
      (e.answer || "").toLowerCase().includes(q) ||
      (e.tags || "").toLowerCase().includes(q)
    );
  }).sort((a, b) => b.cachedAt - a.cachedAt);
});

ipcMain.handle("cache:delete", (_e, id) => {
  const data = readCache();
  data.entries = data.entries.filter((e) => e.id !== id);
  writeCache(data);
  return true;
});

ipcMain.handle("cache:clear", () => {
  writeCache({ entries: [] });
  return true;
});

ipcMain.handle("cache:stats", () => {
  const data = readCache();
  const entries = data.entries;
  const totalChars = entries.reduce((s, e) => s + (e.answer || "").length, 0);
  const oldest = entries.length ? new Date(Math.min(...entries.map((e) => e.cachedAt))) : null;
  const newest = entries.length ? new Date(Math.max(...entries.map((e) => e.cachedAt))) : null;
  return {
    totalEntries: entries.length,
    totalChars,
    oldest: oldest ? oldest.toISOString() : null,
    newest: newest ? newest.toISOString() : null,
  };
});

ipcMain.handle("export:save-dialog", async (_e, defaultName) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    title: "Export Research Report",
    defaultPath: path.join(app.getPath("documents"), defaultName || "report.md"),
    filters: [
      { name: "Markdown", extensions: ["md"] },
      { name: "JSON", extensions: ["json"] },
      { name: "Text", extensions: ["txt"] },
      { name: "All Files", extensions: ["*"] },
    ],
  });
  return result;
});

ipcMain.handle("export:write-file", async (_e, filePath, content) => {
  try {
    fs.writeFileSync(filePath, content, "utf-8");
    if (mainWindow) {
      const n = new Notification({
        title: "Export Complete",
        body: `Report saved to ${path.basename(filePath)}`,
      });
      n.show();
    }
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle("notification:show", (_e, title, body) => {
  const n = new Notification({ title, body });
  n.show();
  return true;
});
