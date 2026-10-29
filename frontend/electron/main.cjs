console.log("ELECTRON MAIN PROCESS STARTED! Ver:", process.versions.electron);

const { app, BrowserWindow, shell, ipcMain } = require("electron");
const path = require("path");

const PORT = process.env.PORT || 5173;
const devUrl = `http://localhost:${PORT}`;

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: "BodhCode Studio — Unified AI IDE",
    backgroundColor: "#09090b",
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  // Handle external URLs in default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  // Load local server URL
  const loadDev = () => {
    mainWindow.loadURL(devUrl).catch(() => {
      setTimeout(loadDev, 1000);
    });
  };

  loadDev();

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

if (app) {
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
}
