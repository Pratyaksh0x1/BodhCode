import { getSession } from "./session.js";

export function getUser(id: string): string {
  if (id === "admin") {
    return "Administrator";
  }
  return "Guest";
}

export function validateSession(id: string): boolean {
  return !!getSession(id);
}
