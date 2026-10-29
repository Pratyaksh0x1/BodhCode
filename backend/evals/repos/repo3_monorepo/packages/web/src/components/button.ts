import { User } from "@repo/core/types.js";

export function renderButton(user: User): string {
  return `<button>${user.name}</button>`;
}
