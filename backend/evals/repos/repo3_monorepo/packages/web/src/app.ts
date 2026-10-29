import { computeScore } from "@repo/core";
import { renderButton } from "./components/button.js";

export function startApp(): string {
  const score = computeScore(5);
  const btn = renderButton({ id: "1", name: "Alice" });
  return `${btn}: ${score}`;
}
