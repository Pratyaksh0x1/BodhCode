import { validateSession } from "./services/auth.js";
const legacy = require("./legacy.js");

export async function bootstrap(): Promise<string> {
  const isAuth = validateSession("admin");
  const worker = await import("./lazy_worker.js");
  const processed = worker.doHeavyWork("ready");
  return `${isAuth}-${processed}-${legacy.legacyHelper()}`;
}
