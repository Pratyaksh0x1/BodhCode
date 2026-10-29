const { app, BrowserWindow, shell, ipcMain } = require("electron");
const path = require("path");

const isDev = process.env.NODE_ENV !== "production" && !app.isPackaged;
const PORT = process.env.PORT || 5173;

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: "BodhCode Studio — Unified AI IDE",
    backgroundColor: "#0a0a0a",
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  // Open external links in user's default browser
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  const devUrl = `http://localhost:${PORT}`;

  if (isDev) {
    win.loadURL(devUrl).catch(() => {
      // If dev server hasn't started yet, retry after 1 second
      setTimeout(() => win.loadURL(devUrl), 1000);
    });
  } else {
    win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
