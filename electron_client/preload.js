const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  settings: {
    load: () => ipcRenderer.invoke("settings:load"),
    save: (s) => ipcRenderer.invoke("settings:save", s),
  },
  cache: {
    list: () => ipcRenderer.invoke("cache:list"),
    save: (e) => ipcRenderer.invoke("cache:save", e),
    get: (id) => ipcRenderer.invoke("cache:get", id),
    search: (q) => ipcRenderer.invoke("cache:search", q),
    delete: (id) => ipcRenderer.invoke("cache:delete", id),
    clear: () => ipcRenderer.invoke("cache:clear"),
    stats: () => ipcRenderer.invoke("cache:stats"),
  },
  export: {
    saveDialog: (name) => ipcRenderer.invoke("export:save-dialog", name),
    writeFile: (p, c) => ipcRenderer.invoke("export:write-file", p, c),
  },
  notify: (title, body) => ipcRenderer.invoke("notification:show", title, body),
  onMenuExport: (cb) => ipcRenderer.on("menu-export", cb),
  onMenuSettings: (cb) => ipcRenderer.on("menu-settings", cb),
});
