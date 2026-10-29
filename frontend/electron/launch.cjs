const { spawn } = require("child_process");
const path = require("path");
const electronPath = require("electron");

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const appPath = path.resolve(__dirname, "main.cjs");
console.log("Launching BodhCode Studio Desktop App via Electron...");

const child = spawn(electronPath, [appPath, ...process.argv.slice(2)], {
  env,
  stdio: "ignore",
  windowsHide: false,
  detached: true,
});

child.unref();
console.log("BodhCode Studio Desktop App is running in standalone window (PID:", child.pid, ").");
process.exit(0);
