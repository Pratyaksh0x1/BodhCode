import { calculateTotal } from "@/services/api.js";
import { capitalize } from "@utils/index.js";

export function run(): string {
  const total = calculateTotal([1, 2, 3]);
  return capitalize(`total is ${total}`);
}
