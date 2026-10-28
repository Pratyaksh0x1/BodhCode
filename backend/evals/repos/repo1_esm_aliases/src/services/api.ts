import { add } from "@/utils/math.js";

export function calculateTotal(items: number[]): number {
  return items.reduce((acc, val) => add(acc, val), 0);
}
