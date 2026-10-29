import { create } from "zustand";

export interface RateLimitState {
  active: boolean;
  secondsRemaining: number;
  message: string;
  triggerRateLimit: (retryAfterSeconds: number, message?: string) => void;
  tick: () => void;
  dismiss: () => void;
}

export const useRateLimitStore = create<RateLimitState>((set) => ({
  active: false,
  secondsRemaining: 0,
  message: "You're sending requests a bit too quickly. Please slow down.",
  triggerRateLimit: (retryAfterSeconds: number, message?: string) =>
    set({
      active: true,
      secondsRemaining: Math.max(1, retryAfterSeconds),
      message: message || "You're sending requests a bit too quickly. Please slow down.",
    }),
  tick: () =>
    set((state) => {
      const next = state.secondsRemaining - 1;
      return next <= 0
        ? { active: false, secondsRemaining: 0 }
        : { secondsRemaining: next };
    }),
  dismiss: () => set({ active: false, secondsRemaining: 0 }),
}));
