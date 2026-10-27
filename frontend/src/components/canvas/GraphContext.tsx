import { createContext, useContext } from "react";
import type { GraphDoc } from "../../lib/repos";

export const GraphContext = createContext<GraphDoc | null>(null);

export function useGraphContext(): GraphDoc {
  const ctx = useContext(GraphContext);
  if (!ctx) {
    throw new Error("useGraphContext must be used within GraphContext.Provider");
  }
  return ctx;
}
