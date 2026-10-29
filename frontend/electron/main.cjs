const { app, BrowserWindow, shell, ipcMain } = require("electron");
const path = require("path");

const PORT = process.env.PORT || 5173;
const devUrl = `http://localhost:${PORT}`;

let mainWindow = null;

// Register deep link protocol
if (process.defaultApp) {
  if (process.argv.length >= 2) {
    app.setAsDefaultProtocolClient("bodhcode", process.execPath, [path.resolve(process.argv[1])]);
  }
} else {
  app.setAsDefaultProtocolClient("bodhcode");
}

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

  // Open external links and authentication flows in user's default browser (e.g. Chrome)
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  // Intercept in-window navigation for auth endpoints and redirect to Chrome
  mainWindow.webContents.on("will-navigate", (event, url) => {
    const isAuthRoute =
      url.includes("/auth/github/login") ||
      url.includes("/auth/chatgpt/login") ||
      url.includes("github.com/login") ||
      url.includes("auth.openai.com") ||
      url.includes("chatgpt.com");

    if (isAuthRoute) {
      event.preventDefault();
      console.log("[Electron] Redirecting auth flow to external browser (Chrome):", url);
      shell.openExternal(url);
    }
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

// Single instance lock
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on("second-instance", (_event, commandLine) => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

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
