import { getUser } from "./auth.js";

export function getSession(id: string): { user: string } {
  return { user: getUser(id) };
}
